#!/usr/bin/env python3
"""Serveur d'autorisation sans stockage : enregistrement, code, jetons, refus."""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "scripts"))
sys.path.insert(0, str(ROOT))

from mcp.server.auth.handlers.register import RegistrationHandler  # noqa: E402
from mcp.server.auth.provider import AuthorizationParams, AuthorizeError, TokenError  # noqa: E402
from mcp.server.auth.settings import ClientRegistrationOptions  # noqa: E402
from pydantic import AnyUrl  # noqa: E402

from pandecte.credentials import PisteCredentials  # noqa: E402
from mcp_server.access import encode_personal_key  # noqa: E402
from mcp_server.piste_oauth import (  # noqa: E402
    ACCESS_TTL,
    REFRESH_TTL,
    PisteAuthProvider,
)
from mcp_server.sealed import Sealer  # noqa: E402

PUBLIC = "https://pandecte.example.org"
RESOURCE = PUBLIC + "/mcp"
REDIRECT = "https://claude.ai/api/mcp/auth_callback"
PISTE = PisteCredentials("identifiant-piste-1234", "secret-piste-tres-confidentiel")


class Clock:
    def __init__(self) -> None:
        self.now = 1_792_000_000.0

    def __call__(self) -> float:
        return self.now


class FakeRequest:
    def __init__(self, body: dict) -> None:
        self._body = json.dumps(body).encode()

    async def body(self) -> bytes:
        return self._body


def run(coro):
    return asyncio.run(coro)


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.sealer = Sealer(bytes(range(32)), clock=self.clock)
        self.provider = PisteAuthProvider(
            self.sealer, public_url=PUBLIC, resource=RESOURCE, clock=self.clock
        )

    def register(self, **overrides) -> dict:
        body = {"redirect_uris": [REDIRECT], "client_name": "Claude",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"], "token_endpoint_auth_method": "none"}
        body.update(overrides)
        handler = RegistrationHandler(self.provider, ClientRegistrationOptions(enabled=True))
        response = run(handler.handle(FakeRequest(body)))
        self.assertEqual(201, response.status_code, response.body)
        return json.loads(response.body)

    def client(self, registered: dict):
        client = run(self.provider.get_client(registered["client_id"]))
        self.assertIsNotNone(client)
        return client

    def code_for(self, client, verifier_challenge="defi-pkce", resource=None):
        params = AuthorizationParams(
            state="etat-123", scopes=[], code_challenge=verifier_challenge,
            redirect_uri=AnyUrl(REDIRECT), redirect_uri_provided_explicitly=True,
            resource=resource,
        )
        login_url = run(self.provider.authorize(client, params))
        self.assertTrue(login_url.startswith(PUBLIC + "/connexion?demande=pse1."))
        sealed = parse_qs(urlsplit(login_url).query)["demande"][0]
        request = self.provider.read_request(sealed)
        back = urlsplit(self.provider.issue_code(request, PISTE))
        query = parse_qs(back.query)
        self.assertEqual("etat-123", query["state"][0])
        self.assertEqual(REDIRECT, f"{back.scheme}://{back.netloc}{back.path}")
        return query["code"][0]

    def test_registration_returns_a_sealed_client_id(self):
        registered = self.register()
        self.assertTrue(registered["client_id"].startswith("pse1."))
        self.assertIsNone(registered.get("client_secret"))
        client = self.client(registered)
        self.assertEqual([AnyUrl(REDIRECT)], client.redirect_uris)
        self.assertEqual("Claude", client.client_name)

    def test_confidential_client_gets_a_secret_kept_in_its_id(self):
        registered = self.register(token_endpoint_auth_method="client_secret_post")
        self.assertTrue(registered["client_secret"])
        self.assertEqual(registered["client_secret"], self.client(registered).client_secret)
        self.assertNotIn(registered["client_secret"], registered["client_id"])

    def test_unknown_or_forged_client_is_none(self):
        self.assertIsNone(run(self.provider.get_client("client-inconnu")))
        other = PisteAuthProvider(Sealer(bytes(range(1, 33))), public_url=PUBLIC, resource=RESOURCE)
        forged = RegistrationHandler(other, ClientRegistrationOptions(enabled=True))
        body = {"redirect_uris": ["https://attaquant.example/cb"], "token_endpoint_auth_method": "none"}
        foreign = json.loads(run(forged.handle(FakeRequest(body))).body)["client_id"]
        self.assertIsNone(run(self.provider.get_client(foreign)))

    def test_full_flow_issues_tokens_carrying_the_user_keys(self):
        client = self.client(self.register())
        code = self.code_for(client)
        self.assertNotIn(PISTE.client_secret, code)
        loaded = run(self.provider.load_authorization_code(client, code))
        self.assertEqual("defi-pkce", loaded.code_challenge)
        self.assertEqual(RESOURCE, loaded.resource)
        tokens = run(self.provider.exchange_authorization_code(client, loaded))
        self.assertEqual(ACCESS_TTL, tokens.expires_in)
        for value in (tokens.access_token, tokens.refresh_token):
            self.assertNotIn(PISTE.client_secret, value)
            self.assertNotIn(PISTE.client_id, value)
        grant = run(self.provider.load_access_token(tokens.access_token))
        self.assertEqual("keys", grant.mode)
        self.assertEqual(PISTE.client_secret, grant.credentials.client_secret)
        self.assertEqual(RESOURCE, grant.resource)
        self.assertNotIn(PISTE.client_secret, repr(grant))

    def test_code_is_single_use(self):
        client = self.client(self.register())
        loaded = run(self.provider.load_authorization_code(client, self.code_for(client)))
        run(self.provider.exchange_authorization_code(client, loaded))
        with self.assertRaises(TokenError):
            run(self.provider.exchange_authorization_code(client, loaded))

    def test_code_belongs_to_its_client(self):
        first = self.client(self.register())
        second = self.client(self.register(client_name="Autre"))
        code = self.code_for(first)
        self.assertIsNone(run(self.provider.load_authorization_code(second, code)))

    def test_code_and_access_token_expire(self):
        client = self.client(self.register())
        code = self.code_for(client)
        tokens = run(self.provider.exchange_authorization_code(
            client, run(self.provider.load_authorization_code(client, code))))
        self.clock.now += ACCESS_TTL
        self.assertIsNone(run(self.provider.load_access_token(tokens.access_token)))
        self.assertIsNone(run(self.provider.load_authorization_code(client, self.code_for(client) + "x")))

    def test_refresh_is_silent_and_sliding(self):
        client = self.client(self.register())
        tokens = run(self.provider.exchange_authorization_code(
            client, run(self.provider.load_authorization_code(client, self.code_for(client)))))
        # Un utilisateur qui revient tous les 80 jours ne ressaisit jamais ses clés.
        for _ in range(3):
            self.clock.now += 80 * 24 * 3600
            refresh = run(self.provider.load_refresh_token(client, tokens.refresh_token))
            self.assertIsNotNone(refresh)
            tokens = run(self.provider.exchange_refresh_token(client, refresh, []))
        grant = run(self.provider.load_access_token(tokens.access_token))
        self.assertEqual(PISTE.client_secret, grant.credentials.client_secret)
        self.clock.now += REFRESH_TTL
        self.assertIsNone(run(self.provider.load_refresh_token(client, tokens.refresh_token)))

    def test_refresh_token_belongs_to_its_client(self):
        first = self.client(self.register())
        second = self.client(self.register(client_name="Autre"))
        tokens = run(self.provider.exchange_authorization_code(
            first, run(self.provider.load_authorization_code(first, self.code_for(first)))))
        self.assertIsNone(run(self.provider.load_refresh_token(second, tokens.refresh_token)))

    def test_tokens_are_not_interchangeable(self):
        client = self.client(self.register())
        tokens = run(self.provider.exchange_authorization_code(
            client, run(self.provider.load_authorization_code(client, self.code_for(client)))))
        self.assertIsNone(run(self.provider.load_access_token(tokens.refresh_token)))
        self.assertIsNone(run(self.provider.load_refresh_token(client, tokens.access_token)))

    def test_foreign_resource_is_refused(self):
        client = self.client(self.register())
        params = AuthorizationParams(
            state=None, scopes=[], code_challenge="x", redirect_uri=AnyUrl(REDIRECT),
            redirect_uri_provided_explicitly=True, resource="https://autre.example/mcp")
        with self.assertRaises(AuthorizeError):
            run(self.provider.authorize(client, params))

    def test_expired_login_request_is_refused(self):
        client = self.client(self.register())
        params = AuthorizationParams(
            state=None, scopes=[], code_challenge="x", redirect_uri=AnyUrl(REDIRECT),
            redirect_uri_provided_explicitly=True)
        url = run(self.provider.authorize(client, params))
        sealed = parse_qs(urlsplit(url).query)["demande"][0]
        self.clock.now += 16 * 60
        self.assertIsNone(self.provider.read_request(sealed))

    def test_personal_key_still_works_and_can_be_disabled(self):
        key = encode_personal_key(PISTE)
        grant = run(self.provider.load_access_token(key))
        self.assertEqual(PISTE.client_id, grant.credentials.client_id)
        closed = PisteAuthProvider(self.sealer, public_url=PUBLIC, resource=RESOURCE,
                                   personal_keys_enabled=False)
        self.assertIsNone(run(closed.load_access_token(key)))

    def test_garbage_access_token_is_refused(self):
        for value in ("", "x" * 5000, "pse1.abc", "eyJhbGciOi.faux.jwt"):
            self.assertIsNone(run(self.provider.load_access_token(value)))


if __name__ == "__main__":
    unittest.main()
