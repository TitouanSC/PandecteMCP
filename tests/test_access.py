#!/usr/bin/env python3
"""Reconnaissance des trois formes de jeton et choix du mode, hors réseau."""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "scripts"))
sys.path.insert(0, str(ROOT))

from mcp.server.auth.provider import AccessToken  # noqa: E402

from mcp_server.access import (  # noqa: E402
    AccessGrant,
    AccessVerifier,
    encode_personal_key,
    hash_personal_token,
    new_personal_token,
    parse_personal_key,
)
from mcp_server.store import Store  # noqa: E402
from pandecte.credentials import PisteCredentials  # noqa: E402

PEPPER = b"poivre-de-test-" + b"x" * 32
RESOURCE = "https://pandecte.example.com/mcp"
CREDS = PisteCredentials(
    "0f8c2a54-1b7e-4c3d-9a61-7c2e9b0d4f11", "c9e1b7a2-55d0-4e8f-8b3a-2d6f0a9c1e74"
)


def verifier(store: Store, oauth=None, **kwargs) -> AccessVerifier:
    return AccessVerifier(
        store=store, pepper=PEPPER, resource=RESOURCE, scopes=[], oauth_verifier=oauth, **kwargs
    )


def verify(v: AccessVerifier, token: str):
    return asyncio.run(v.verify_token(token))


class PersonalKeyFormatTests(unittest.TestCase):
    def test_round_trip_with_and_without_key_id(self):
        self.assertEqual(CREDS, parse_personal_key(encode_personal_key(CREDS)))
        with_key = PisteCredentials(CREDS.client_id, CREDS.client_secret, "cle-judilibre-01")
        self.assertEqual(with_key, parse_personal_key(encode_personal_key(with_key)))

    def test_known_encoding(self):
        # Valeur de référence : la page web doit produire exactement la même.
        self.assertEqual(
            "pk1.aWRlbnRpZmlhbnQ.c2VjcmV0LTEyMw",
            encode_personal_key(PisteCredentials("identifiant", "secret-123")),
        )

    def test_strict_rejections(self):
        valid = encode_personal_key(CREDS)
        for raw in (
            "pk1.",
            "pk1.YQ",  # un seul segment
            valid + ".YQ.YQ",  # trop de segments
            valid + "=",  # remplissage
            valid.replace("pk1.", "pk2."),
            "pk1.aWRlbnRpZmlhbnQ.c2Vj cmV0",  # espace
            "pk1." + "QUJD" + ".c2VjcmV0LTEyMw",  # valeur trop courte (« ABC »)
            "pk1.aWTDqQ.c2VjcmV0LTEyMw",  # non ASCII après décodage
            "pk1.aWRlbnRpZmlhbnR.c2VjcmV0LTEyMw",  # base64 non canonique
            "pk1." + "QUFB" * 400 + ".c2VjcmV0LTEyMw",  # trop long
        ):
            with self.subTest(raw=raw[:40]):
                self.assertIsNone(parse_personal_key(raw))


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def test_personal_key_selects_keys_mode_without_exposing_values(self):
        grant = verify(verifier(self.store), encode_personal_key(CREDS))
        self.assertIsInstance(grant, AccessGrant)
        self.assertEqual("keys", grant.mode)
        self.assertEqual(CREDS, grant.credentials)
        self.assertTrue(grant.subject.startswith("cle:"))
        rendus = (repr(grant), str(grant), grant.model_dump_json(), grant.token, grant.subject)
        for rendu in rendus:
            self.assertNotIn(CREDS.client_id, rendu)
            self.assertNotIn(CREDS.client_secret, rendu)
            self.assertNotIn(encode_personal_key(CREDS), rendu)

    def test_personal_keys_can_be_disabled(self):
        v = verifier(self.store, personal_keys_enabled=False)
        self.assertIsNone(verify(v, encode_personal_key(CREDS)))

    def test_personal_token_selects_shared_mode_for_its_owner(self):
        token = new_personal_token()
        self.store.replace_token("user_01ABC", hash_personal_token(token, PEPPER))
        grant = verify(verifier(self.store), token)
        self.assertEqual(("shared", "user_01ABC"), (grant.mode, grant.subject))
        self.assertIsNone(grant.credentials)
        self.assertNotIn(token, repr(grant) + grant.token)

    def test_unknown_revoked_or_malformed_personal_tokens_are_refused(self):
        token = new_personal_token()
        v = verifier(self.store)
        self.assertIsNone(verify(v, token))
        self.store.replace_token("user_1", hash_personal_token(token, PEPPER))
        self.store.revoke("user_1")
        self.assertIsNone(verify(v, token))
        for bad in ("pdt_", "pdt_court", token + "x", token[:-1] + "!"):
            self.assertIsNone(verify(v, bad))

    def test_token_hash_depends_on_the_pepper(self):
        token = new_personal_token()
        self.store.replace_token("user_1", hash_personal_token(token, b"autre-poivre" * 4))
        self.assertIsNone(verify(verifier(self.store), token))

    def test_stored_value_is_never_the_token(self):
        token = new_personal_token()
        digest = hash_personal_token(token, PEPPER)
        self.assertNotIn(token, digest)
        self.assertEqual(64, len(digest))

    def test_oauth_tokens_are_delegated_and_stripped(self):
        oauth = mock.Mock()
        oauth.verify_token = mock.AsyncMock(
            return_value=AccessToken(
                token="eyJ.jwt.brut", client_id="client-claude", scopes=["openid"],
                expires_at=2_000_000_000, resource=RESOURCE, subject="user_01XYZ",
            )
        )
        grant = verify(verifier(self.store, oauth), "eyJ.jwt.brut")
        self.assertEqual(("shared", "user_01XYZ"), (grant.mode, grant.subject))
        self.assertNotIn("eyJ.jwt.brut", grant.token)
        oauth.verify_token.assert_awaited_once_with("eyJ.jwt.brut")

    def test_oauth_rejection_and_absence(self):
        oauth = mock.Mock()
        oauth.verify_token = mock.AsyncMock(return_value=None)
        self.assertIsNone(verify(verifier(self.store, oauth), "eyJ.faux"))
        self.assertIsNone(verify(verifier(self.store), "eyJ.faux"))

    def test_oversized_bearer_is_refused_before_any_work(self):
        oauth = mock.Mock()
        oauth.verify_token = mock.AsyncMock()
        self.assertIsNone(verify(verifier(self.store, oauth), "a" * 5000))
        oauth.verify_token.assert_not_awaited()

    def test_rejections_are_logged_without_the_token(self):
        bad = "pk1.aWRlbnRpZmlhbnQ.c2Vj cmV0"
        with self.assertLogs("pandecte.mcp.auth", level="INFO") as journal:
            verify(verifier(self.store), bad)
        self.assertNotIn("aWRlbnRpZmlhbnQ", " ".join(journal.output))


if __name__ == "__main__":
    unittest.main()
