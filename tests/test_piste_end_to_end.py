#!/usr/bin/env python3
"""Mode piste, de bout en bout : le parcours d'un client OAuth comme claude.ai.

Découverte → enregistrement → /authorize → page de connexion → code → jeton
→ appel d'outil avec les identifiants de l'utilisateur → renouvellement.
Les identifiants du titulaire, présents dans l'environnement au démarrage,
doivent être retirés et jamais utilisés.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib
import json
import os
import secrets
import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "scripts"))
sys.path.insert(0, str(ROOT))

import httpx2  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

from mcp_server import server as mcp_app  # noqa: E402
from mcp_server.sealed import new_key_text  # noqa: E402
from pandecte.credentials import active_credentials  # noqa: E402

PUBLIC = "https://exemple.test"
RESOURCE = PUBLIC + "/mcp"
CLAUDE = "https://claude.ai/api/mcp/auth_callback"
TRANSPORT_HOST = "127.0.0.1:8000"
TRANSPORT_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[TRANSPORT_HOST],
    allowed_origins=[f"http://{TRANSPORT_HOST}"],
)
USER_ID, USER_SECRET = "identifiant-utilisateur", "secret-utilisateur-confidentiel"
OWNER_ID, OWNER_SECRET = "identifiant-titulaire", "secret-titulaire-confidentiel"
ARTICLE = {"id": "LEGIARTI000032041571", "title": "Article 1240", "text": "Tout fait…",
           "metadata": {"source": "Légifrance API"}}


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class PisteEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._env = mock.patch.dict(os.environ, {
            "MCP_ENV": "test",
            "MCP_AUTH_MODE": "piste",
            "MCP_PUBLIC_URL": PUBLIC,
            "PANDECTE_SEAL_KEY": new_key_text(),
            "LEGIFRANCE_CLIENT_ID": OWNER_ID,
            "LEGIFRANCE_CLIENT_SECRET": OWNER_SECRET,
            # Sans cache : chaque appel doit atteindre l'outil et révéler les
            # identifiants effectivement posés.
            "PANDECTE_CACHE_TEXT_TTL": "0",
        }, clear=False)
        cls._env.start()
        importlib.reload(mcp_app)

    @classmethod
    def tearDownClass(cls):
        cls._env.stop()
        for name in ("LEGIFRANCE_CLIENT_ID", "LEGIFRANCE_CLIENT_SECRET"):
            os.environ.pop(name, None)
        importlib.reload(mcp_app)

    def setUp(self):
        self.verified = []
        mcp_app.CONNEXION_PAGE._verify = self.verified.append
        self.seen_credentials = []

        def get_article(id, date=None):  # noqa: A002 — signature de l'outil
            self.seen_credentials.append(active_credentials())
            return dict(ARTICLE, id=id)

        patcher = mock.patch.object(mcp_app.legal_tools, "get_article", get_article)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def scenario(self, steps):
        app = mcp_app.build_http_app(transport_security=TRANSPORT_SECURITY)
        inner = app.inner
        async with inner.router.lifespan_context(inner):
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app), base_url=f"http://{TRANSPORT_HOST}"
            ) as client:
                return await steps(client)

    async def connect(self, client) -> dict:
        """Parcours complet d'un client OAuth ; rend la réponse de /token."""
        prm = (await client.get("/.well-known/oauth-protected-resource/mcp")).json()
        self.assertEqual([PUBLIC], [s.rstrip("/") for s in prm["authorization_servers"]])
        meta = (await client.get("/.well-known/oauth-authorization-server")).json()
        self.assertIn("registration_endpoint", meta)
        self.assertIn("S256", meta["code_challenge_methods_supported"])

        registered = (await client.post("/register", json={
            "redirect_uris": [CLAUDE], "client_name": "Claude",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"], "token_endpoint_auth_method": "none",
        })).json()
        client_id = registered["client_id"]

        verifier, challenge = pkce()
        authorize = await client.get("/authorize", params={
            "response_type": "code", "client_id": client_id, "redirect_uri": CLAUDE,
            "code_challenge": challenge, "code_challenge_method": "S256",
            "state": "etat-claude", "resource": RESOURCE,
        })
        self.assertIn(authorize.status_code, (302, 307))
        login = urlsplit(authorize.headers["location"])
        self.assertEqual((PUBLIC + "/connexion"), f"{login.scheme}://{login.netloc}{login.path}")
        demande = parse_qs(login.query)["demande"][0]

        page = await client.get("/connexion", params={"demande": demande})
        self.assertEqual(200, page.status_code)
        self.assertIn("Claude", page.text)

        submitted = await client.post("/connexion", data={
            "demande": demande, "client_id": USER_ID, "client_secret": USER_SECRET,
            "consentement": "oui", "action": "autoriser",
        }, headers={"origin": PUBLIC, "sec-fetch-site": "same-origin"})
        self.assertEqual(303, submitted.status_code, submitted.text[:300])
        back = parse_qs(urlsplit(submitted.headers["location"]).query)
        self.assertEqual("etat-claude", back["state"][0])

        token = await client.post("/token", data={
            "grant_type": "authorization_code", "code": back["code"][0],
            "redirect_uri": CLAUDE, "client_id": client_id, "code_verifier": verifier,
            "resource": RESOURCE,
        })
        self.assertEqual(200, token.status_code, token.text)
        return dict(token.json(), client_id=client_id)

    async def call_tool(self, client, access_token: str):
        headers = {"Authorization": f"Bearer {access_token}",
                   "Accept": "application/json, text/event-stream"}
        init = await client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "test", "version": "1"}}})
        if init.status_code != 200:
            return init.status_code, None
        session = init.headers.get("mcp-session-id")
        if session:
            headers["mcp-session-id"] = session
        await client.post("/mcp", headers=headers,
                          json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        response = await client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "get_article", "arguments": {"id": "LEGIARTI000032041571"}}})
        data = [line[5:] for line in response.text.splitlines() if line.startswith("data:")]
        return response.status_code, json.loads(data[-1]) if data else response.json()

    def test_owner_credentials_are_removed_at_startup(self):
        self.assertNotIn("LEGIFRANCE_CLIENT_ID", os.environ)
        self.assertNotIn("LEGIFRANCE_CLIENT_SECRET", os.environ)
        self.assertFalse(mcp_app.SETTINGS.shared_mode)

    def test_full_oauth_flow_uses_only_the_user_keys(self):
        async def steps(client):
            tokens = await self.connect(client)
            for value in (tokens["access_token"], tokens["refresh_token"], tokens["client_id"]):
                self.assertNotIn(USER_SECRET, value)
            status, message = await self.call_tool(client, tokens["access_token"])
            self.assertEqual(200, status)
            self.assertFalse(message["result"].get("isError"), message)
            return tokens

        asyncio.run(self.scenario(steps))
        self.assertEqual(USER_SECRET, self.verified[0].client_secret)
        self.assertEqual(1, len(self.seen_credentials))
        used = self.seen_credentials[0]
        self.assertEqual((USER_ID, USER_SECRET), (used.client_id, used.client_secret))

    def test_refresh_keeps_the_user_connected(self):
        async def steps(client):
            tokens = await self.connect(client)
            refreshed = await client.post("/token", data={
                "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
                "client_id": tokens["client_id"], "resource": RESOURCE,
            })
            self.assertEqual(200, refreshed.status_code, refreshed.text)
            status, message = await self.call_tool(client, refreshed.json()["access_token"])
            self.assertEqual(200, status)
            self.assertFalse(message["result"].get("isError"), message)

        asyncio.run(self.scenario(steps))
        self.assertEqual(USER_SECRET, self.seen_credentials[-1].client_secret)

    def test_without_a_valid_token_nothing_runs(self):
        async def steps(client):
            for token in ("", "pse1.faux", "jeton-quelconque"):
                status, _ = await self.call_tool(client, token)
                self.assertEqual(401, status)

        asyncio.run(self.scenario(steps))
        self.assertEqual([], self.seen_credentials)


if __name__ == "__main__":
    unittest.main()
