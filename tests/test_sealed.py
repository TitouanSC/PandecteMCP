#!/usr/bin/env python3
"""Enveloppes chiffrées : confidentialité, intégrité, usage, expiration, rotation."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp_server.sealed import (  # noqa: E402
    MAX_SEALED_CHARS,
    PREFIX,
    SealError,
    Sealer,
    _b64decode,
    _b64encode,
    new_key_text,
    parse_key,
)

KEY = bytes(range(32))
OTHER = bytes(range(1, 33))
SECRET = "secret-piste-tres-confidentiel"


class Clock:
    def __init__(self) -> None:
        self.now = 1_792_000_000.0

    def __call__(self) -> float:
        return self.now


class SealerTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.sealer = Sealer(KEY, clock=self.clock)

    def test_roundtrip_keeps_claims_and_adds_expiry(self):
        token = self.sealer.seal("access", {"cid": "abc", "cs": SECRET}, 3600)
        self.assertTrue(token.startswith(PREFIX))
        claims = self.sealer.open("access", token)
        self.assertEqual("abc", claims["cid"])
        self.assertEqual(SECRET, claims["cs"])
        self.assertEqual(int(self.clock.now) + 3600, claims["exp"])

    def test_content_is_not_readable_by_the_carrier(self):
        token = self.sealer.seal("access", {"cs": SECRET}, 60)
        self.assertNotIn(SECRET.encode(), _b64decode(token[len(PREFIX):]))
        self.assertNotIn(SECRET, token)

    def test_two_seals_of_the_same_content_differ(self):
        first = self.sealer.seal("access", {"cs": SECRET}, 60)
        self.assertNotEqual(first, self.sealer.seal("access", {"cs": SECRET}, 60))

    def test_purpose_is_bound(self):
        code = self.sealer.seal("code", {"cs": SECRET}, 60)
        for other in ("access", "refresh", "client", "authreq"):
            with self.assertRaises(SealError):
                self.sealer.open(other, code)

    def test_tampering_is_detected(self):
        token = self.sealer.seal("access", {"cs": SECRET}, 60)
        raw = bytearray(_b64decode(token[len(PREFIX):]))
        for index in (0, 5, len(raw) // 2, len(raw) - 1):
            altered = bytearray(raw)
            altered[index] ^= 0x01
            with self.assertRaises(SealError):
                self.sealer.open("access", PREFIX + _b64encode(bytes(altered)))

    def test_expiry(self):
        token = self.sealer.seal("access", {}, 60)
        self.clock.now += 59
        self.sealer.open("access", token)
        self.clock.now += 1
        with self.assertRaises(SealError):
            self.sealer.open("access", token)

    def test_foreign_key_is_refused(self):
        token = Sealer(OTHER, clock=self.clock).seal("access", {}, 60)
        with self.assertRaises(SealError):
            self.sealer.open("access", token)

    def test_rotation_reads_previous_key_and_seals_with_new_one(self):
        old = self.sealer.seal("refresh", {"cid": "x"}, 60)
        rotated = Sealer(OTHER, (KEY,), clock=self.clock)
        self.assertEqual("x", rotated.open("refresh", old)["cid"])
        fresh = rotated.seal("refresh", {"cid": "y"}, 60)
        with self.assertRaises(SealError):
            self.sealer.open("refresh", fresh)

    def test_garbage_is_refused_without_detail(self):
        for value in ("", "pse1.", "pse1.!!!", "autre.abc", PREFIX + "A" * MAX_SEALED_CHARS,
                      PREFIX + _b64encode(b"court"), None, 42):
            with self.assertRaises(SealError) as ctx:
                self.sealer.open("access", value)  # type: ignore[arg-type]
            self.assertEqual("Enveloppe invalide.", str(ctx.exception))

    def test_unknown_purpose_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            self.sealer.seal("autre", {}, 60)


class KeyTests(unittest.TestCase):
    def test_new_key_parses(self):
        self.assertEqual(32, len(parse_key(new_key_text())))

    def test_bad_keys_are_refused(self):
        for text in ("", "trop-court", _b64encode(b"x" * 31), "@@@"):
            with self.assertRaises(ValueError):
                parse_key(text)
        with self.assertRaises(ValueError):
            Sealer(b"x" * 16)


if __name__ == "__main__":
    unittest.main()
