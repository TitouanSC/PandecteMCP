#!/usr/bin/env python3
"""Les deux modes d'accès, joués de bout en bout et hors réseau.

Reprend le socle de ``test_oauth_end_to_end`` : application HTTP complète
(garde HTTP, authentification du SDK, transport Streamable HTTP, outils),
jetons OAuth signés localement, aucun appel vers PISTE.
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "scripts"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from test_oauth_end_to_end import OAuthServerCase  # noqa: E402

from mcp_server import server as mcp_app  # noqa: E402
from mcp_server.access import (  # noqa: E402
    encode_personal_key,
    hash_personal_token,
    new_personal_token,
)
from mcp_server.quotas import GLOBAL_SCOPE, QuotaPolicy  # noqa: E402
from mcp_server.store import Store  # noqa: E402
from pandecte.credentials import PisteCredentials, request_credentials  # noqa: E402
from pandecte.errors import LegifranceError  # noqa: E402

ALICE = PisteCredentials("alice-client-id-0001", "alice-client-secret-0001")


def _report_credentials(query: str) -> dict:
    """Outil simulé : rapporte quels identifiants l'appel aurait utilisés."""
    creds = request_credentials()
    return {"query": query, "client_id": creds.client_id if creds else "titulaire"}


class AccessCase(OAuthServerCase):
    def setUp(self) -> None:
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        mcp_app.QUOTAS = QuotaPolicy(
            self.store,
            user_per_minute=50,
            user_per_day=100,
            global_per_day=1000,
            keys_per_minute_per_ip=30,
        )

    def personal_token(self, subject: str) -> str:
        token = new_personal_token()
        mcp_app.STORE.replace_token(subject, hash_personal_token(token, mcp_app.token_pepper()))
        return token


class PersonalKeysModeTests(AccessCase):
    def test_call_uses_the_caller_credentials_not_the_owner_ones(self):
        with mock.patch.object(mcp_app.legal_tools, "search", side_effect=_report_credentials):
            resultat = self.call_tool(encode_personal_key(ALICE), "search", {"query": "x"})
        self.assertFalse(self.en_erreur(resultat), resultat.content)
        self.assertEqual(ALICE.client_id, self.contenu_structure(resultat)["client_id"])

    def test_owner_daily_counters_are_never_touched(self):
        with mock.patch.object(mcp_app.legal_tools, "search", return_value={}):
            self.call_tool(encode_personal_key(ALICE), "search", {"query": "x"})
        day = mcp_app.QUOTAS._now().date().isoformat()
        self.assertEqual(0, self.store.count(GLOBAL_SCOPE, day))

    def test_upstream_error_never_echoes_the_caller_credentials(self):
        def fail(_query):
            raise LegifranceError(
                f"refus pour {ALICE.client_secret}",
                exit_code=3,
                detail=f"client_id={ALICE.client_id}&client_secret={ALICE.client_secret}",
            )

        with mock.patch.object(mcp_app.legal_tools, "search", side_effect=fail):
            with self.assertLogs("pandecte.mcp", level="INFO") as journal:
                resultat = self.call_tool(encode_personal_key(ALICE), "search", {"query": "x"})
        self.assertTrue(self.en_erreur(resultat))
        rendu = str(resultat.content) + " | ".join(journal.output)
        self.assertNotIn(ALICE.client_secret, rendu)
        self.assertNotIn(ALICE.client_id, rendu)
        self.assertNotIn(encode_personal_key(ALICE), rendu)

    def test_ip_rate_limit_applies(self):
        mcp_app.QUOTAS = QuotaPolicy(
            self.store, user_per_minute=50, user_per_day=100,
            global_per_day=1000, keys_per_minute_per_ip=1,
        )
        with mock.patch.object(mcp_app.legal_tools, "search", return_value={}):
            premier = self.call_tool(encode_personal_key(ALICE), "search", {"query": "x"})
            second = self.call_tool(encode_personal_key(ALICE), "search", {"query": "x"})
        self.assertFalse(self.en_erreur(premier), premier.content)
        self.assertTrue(self.en_erreur(second))
        self.assertIn("depuis cette adresse", str(second.content))
        self.assertIn("retry_after=", str(second.content))

    def test_malformed_personal_key_is_refused_like_any_bad_token(self):
        reponse = self.post_mcp("pk1.pas-une-cle.valide")
        self.assertEqual(401, reponse.status_code)
        self.assertNotIn("pas-une-cle", reponse.text)


class PersonalKeysDisabledTests(AccessCase):
    extra_env = {"MCP_PERSONAL_KEYS_ENABLED": "false"}

    def test_personal_keys_are_refused_when_disabled(self):
        self.assertEqual(401, self.post_mcp(encode_personal_key(ALICE)).status_code)


class PersonalTokenModeTests(AccessCase):
    def test_personal_token_uses_the_shared_mode(self):
        token = self.personal_token("user_01ALICE")
        with mock.patch.object(mcp_app.legal_tools, "search", side_effect=_report_credentials):
            resultat = self.call_tool(token, "search", {"query": "x"})
        self.assertFalse(self.en_erreur(resultat), resultat.content)
        self.assertEqual("titulaire", self.contenu_structure(resultat)["client_id"])
        day = mcp_app.QUOTAS._now().date().isoformat()
        self.assertEqual(1, self.store.count("user:user_01ALICE", day))

    def test_oauth_and_personal_token_share_one_quota_per_person(self):
        mcp_app.QUOTAS = QuotaPolicy(
            self.store, user_per_minute=50, user_per_day=2,
            global_per_day=1000, keys_per_minute_per_ip=30,
        )
        token = self.personal_token("user_01BOB")
        with mock.patch.object(mcp_app.legal_tools, "search", return_value={}):
            self.call_tool(token, "search", {"query": "x"})
            self.call_tool(self.token(sub="user_01BOB"), "search", {"query": "x"})
            troisieme = self.call_tool(token, "search", {"query": "x"})
        self.assertTrue(self.en_erreur(troisieme))
        self.assertIn("Quota journalier", str(troisieme.content))
        self.assertIn("00:00 UTC", str(troisieme.content))

    def test_revoked_personal_token_is_refused(self):
        token = self.personal_token("user_01CAROL")
        mcp_app.STORE.revoke("user_01CAROL")
        self.assertEqual(401, self.post_mcp(token).status_code)


class HttpGuardTests(AccessCase):
    def test_repeated_bad_tokens_get_429_with_retry_after(self):
        async def run():
            async with self._running("pdt_" + "x" * 43) as client:
                statuts = []
                for _ in range(32):
                    reponse = await client.post(
                        "/mcp",
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                        headers={"Accept": "application/json, text/event-stream"},
                    )
                    statuts.append(reponse.status_code)
                return statuts, reponse

        statuts, derniere = asyncio.run(run())
        self.assertEqual([401] * 30, statuts[:30])
        self.assertEqual(429, statuts[30])
        self.assertTrue(int(derniere.headers["retry-after"]) > 0)


if __name__ == "__main__":
    unittest.main()
