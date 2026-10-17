#!/usr/bin/env python3
"""Page « Connexion PISTE » : affichage, contrôles, vérification, redirection."""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "scripts"))
sys.path.insert(0, str(ROOT))

import httpx2  # noqa: E402
from mcp.server.auth.provider import AuthorizationParams  # noqa: E402
from mcp.shared.auth import OAuthClientInformationFull  # noqa: E402
from pydantic import AnyUrl  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Route  # noqa: E402

from mcp_server.connexion import ConnexionPage, PisteRejected, PisteUnavailable  # noqa: E402
from mcp_server.piste_oauth import PisteAuthProvider  # noqa: E402
from mcp_server.sealed import Sealer  # noqa: E402

PUBLIC = "https://pandecte.example.org"
CLAUDE = "https://claude.ai/api/mcp/auth_callback"
SECRET = "secret-piste-tres-confidentiel"


class ConnexionTests(unittest.TestCase):
    def setUp(self):
        self.sealer = Sealer(bytes(range(32)))
        self.provider = PisteAuthProvider(self.sealer, public_url=PUBLIC, resource=PUBLIC + "/mcp")
        self.verified: list = []
        self.outcome: Exception | None = None

        def verify(credentials):
            self.verified.append(credentials)
            if self.outcome is not None:
                raise self.outcome

        page = ConnexionPage(self.provider, public_url=PUBLIC, verify=verify)
        self.app = Starlette(routes=[Route("/connexion", page.handle, methods=["GET", "POST"])])

    def demande(self, redirect=CLAUDE, name="Claude"):
        client = OAuthClientInformationFull(
            client_id="pse1.client-de-test", redirect_uris=[AnyUrl(redirect)],
            client_name=name, token_endpoint_auth_method="none")
        params = AuthorizationParams(
            state="etat-1", scopes=[], code_challenge="defi", redirect_uri=AnyUrl(redirect),
            redirect_uri_provided_explicitly=True)
        url = asyncio.run(self.provider.authorize(client, params))
        return parse_qs(urlsplit(url).query)["demande"][0]

    def request(self, method, *, params=None, data=None, headers=None):
        async def go():
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.app),
                                          base_url=PUBLIC) as client:
                return await client.request(method, "/connexion", params=params, data=data,
                                            headers=headers or {})
        return asyncio.run(go())

    def post(self, fields, headers=None):
        base = {"origin": PUBLIC, "sec-fetch-site": "same-origin"}
        base.update(headers or {})
        return self.request("POST", data=fields, headers=base)

    def valid_fields(self, **overrides):
        fields = {"demande": self.demande(), "client_id": "identifiant-piste",
                  "client_secret": SECRET, "consentement": "oui", "action": "autoriser"}
        fields.update(overrides)
        return fields

    def test_form_shows_client_and_destination_with_strict_headers(self):
        response = self.request("GET", params={"demande": self.demande()})
        self.assertEqual(200, response.status_code)
        self.assertIn("Claude", response.text)
        self.assertIn("claude.ai", response.text)
        self.assertNotIn("Attention", response.text)
        csp = response.headers["content-security-policy"]
        self.assertIn("form-action 'self' https://claude.ai;", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual("no-store", response.headers["cache-control"])

    def test_unknown_destination_is_flagged(self):
        sealed = self.demande(redirect="https://attaquant.example/cb", name="Claude")
        response = self.request("GET", params={"demande": sealed})
        self.assertIn("Attention", response.text)
        self.assertIn("attaquant.example", response.text)

    def test_expired_or_forged_request_is_refused(self):
        self.assertEqual(400, self.request("GET", params={"demande": "pse1.faux"}).status_code)
        self.assertEqual(400, self.request("GET").status_code)
        self.assertEqual(400, self.post(self.valid_fields(demande="pse1.faux")).status_code)
        self.assertEqual([], self.verified)

    def test_success_redirects_to_the_client_with_a_sealed_code(self):
        response = self.post(self.valid_fields())
        self.assertEqual(303, response.status_code)
        location = urlsplit(response.headers["location"])
        self.assertEqual("claude.ai", location.hostname)
        query = parse_qs(location.query)
        self.assertEqual("etat-1", query["state"][0])
        self.assertTrue(query["code"][0].startswith("pse1."))
        self.assertNotIn(SECRET, response.headers["location"])
        self.assertEqual(SECRET, self.verified[0].client_secret)

    def test_cross_site_submission_is_refused(self):
        for headers in ({"origin": "https://attaquant.example"}, {"sec-fetch-site": "cross-site"}):
            self.assertEqual(403, self.post(self.valid_fields(), headers=headers).status_code)
        self.assertEqual([], self.verified)

    def test_consent_is_required(self):
        response = self.post(self.valid_fields(consentement=""))
        self.assertEqual(400, response.status_code)
        self.assertIn("Cochez la case", response.text)
        self.assertEqual([], self.verified)

    def test_rejected_keys_are_not_echoed(self):
        self.outcome = PisteRejected()
        response = self.post(self.valid_fields())
        self.assertEqual(400, response.status_code)
        self.assertIn("PISTE refuse", response.text)
        self.assertNotIn(SECRET, response.text)
        self.assertNotIn("identifiant-piste", response.text)

    def test_piste_outage_is_reported_as_such(self):
        self.outcome = PisteUnavailable()
        response = self.post(self.valid_fields())
        self.assertEqual(503, response.status_code)
        self.assertIn("ne répond pas", response.text)

    def test_cancel_returns_access_denied(self):
        response = self.post({"demande": self.demande(), "action": "annuler"})
        self.assertEqual(303, response.status_code)
        query = parse_qs(urlsplit(response.headers["location"]).query)
        self.assertEqual("access_denied", query["error"][0])
        self.assertEqual("etat-1", query["state"][0])

    def test_malformed_credentials_are_refused_before_piste(self):
        response = self.post(self.valid_fields(client_secret="a b"))
        self.assertEqual(400, response.status_code)
        self.assertEqual([], self.verified)

    def test_secrets_never_reach_the_log(self):
        with self.assertLogs("pandecte.mcp.connexion", level="INFO") as journal:
            self.post(self.valid_fields())
        rendu = " ".join(journal.output)
        self.assertIn("outcome=success", rendu)
        self.assertNotIn(SECRET, rendu)


if __name__ == "__main__":
    unittest.main()
