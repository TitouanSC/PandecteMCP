#!/usr/bin/env python3
"""Clé personnelle pk1 et objet d'accès, hors réseau."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "scripts"))
sys.path.insert(0, str(ROOT))

from mcp_server.access import (  # noqa: E402
    AccessGrant,
    encode_personal_key,
    parse_personal_key,
)
from pandecte.credentials import PisteCredentials  # noqa: E402

CREDS = PisteCredentials(
    "0f8c2a54-1b7e-4c3d-9a61-7c2e9b0d4f11", "c9e1b7a2-55d0-4e8f-8b3a-2d6f0a9c1e74"
)


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


class AccessGrantTests(unittest.TestCase):
    def test_credentials_never_appear_in_representations(self):
        grant = AccessGrant(token="[clé personnelle]", client_id="c", scopes=[], credentials=CREDS)
        self.assertEqual("keys", grant.mode)
        for rendering in (repr(grant), str(grant), grant.model_dump_json()):
            self.assertNotIn(CREDS.client_secret, rendering)
            self.assertNotIn(CREDS.client_id, rendering)


if __name__ == "__main__":
    unittest.main()
