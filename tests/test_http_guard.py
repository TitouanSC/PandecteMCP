#!/usr/bin/env python3
"""Résolution de l'IP cliente et page de diagnostic du garde HTTP, hors réseau."""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp_server.http_guard import DIAGNOSTIC_PATH, HttpGuard, resolve_client_ip  # noqa: E402


def scope(headers: dict[str, str] | list[tuple[str, str]], client="10.0.0.9", path="/mcp"):
    items = headers.items() if isinstance(headers, dict) else headers
    return {
        "type": "http",
        "path": path,
        "client": (client, 1234),
        "headers": [(k.encode(), v.encode()) for k, v in items],
    }


class ResolveClientIpTests(unittest.TestCase):
    def test_without_trusted_proxy_the_socket_wins(self):
        s = scope({"x-forwarded-for": "198.51.100.7"})
        self.assertEqual("10.0.0.9", resolve_client_ip(s, 0))

    def test_rightmost_trusted_entry_ignores_spoofed_prefix(self):
        s = scope({"x-forwarded-for": "6.6.6.6, 203.0.113.5, 10.1.1.1"})
        self.assertEqual("10.1.1.1", resolve_client_ip(s, 1))
        self.assertEqual("203.0.113.5", resolve_client_ip(s, 2))

    def test_too_few_entries_falls_back_to_socket(self):
        self.assertEqual("10.0.0.9", resolve_client_ip(scope({"x-forwarded-for": "1.2.3.4"}), 2))

    def test_configured_header_has_priority_when_single_and_valid(self):
        s = scope({"cf-connecting-ip": "2001:db8::1", "x-forwarded-for": "6.6.6.6, 10.1.1.1"})
        self.assertEqual("2001:db8::1", resolve_client_ip(s, 1, "cf-connecting-ip"))
        doubled = scope([("cf-connecting-ip", "1.1.1.1"), ("cf-connecting-ip", "2.2.2.2"),
                         ("x-forwarded-for", "10.1.1.1")])
        self.assertEqual("10.1.1.1", resolve_client_ip(doubled, 1, "cf-connecting-ip"))
        invalid = scope({"cf-connecting-ip": "pas-une-ip"})
        self.assertEqual("10.0.0.9", resolve_client_ip(invalid, 0, "cf-connecting-ip"))


class DiagnosticTests(unittest.TestCase):
    def run_guard(self, guard: HttpGuard, s: dict) -> tuple[int, bytes]:
        sent: list[dict] = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            sent.append(message)

        asyncio.run(guard(s, receive, send))
        status = next(m["status"] for m in sent if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        return status, body

    def inner(self):
        async def app(_scope, _receive, send):
            await send({"type": "http.response.start", "status": 404, "headers": []})
            await send({"type": "http.response.body", "body": b"inner"})

        return app

    def test_disabled_by_default(self):
        guard = HttpGuard(self.inner(), trusted_hops=1)
        status, body = self.run_guard(guard, scope({}, path=DIAGNOSTIC_PATH))
        self.assertEqual((404, b"inner"), (status, body))

    def test_reports_the_caller_view_when_enabled(self):
        guard = HttpGuard(self.inner(), trusted_hops=1, diagnostic=True)
        s = scope({"x-forwarded-for": "198.51.100.7, 10.1.1.1", "authorization": "Bearer pdt_x"},
                  path=DIAGNOSTIC_PATH)
        status, body = self.run_guard(guard, s)
        report = json.loads(body)
        self.assertEqual(200, status)
        self.assertEqual("10.1.1.1", report["resolved_ip"])
        self.assertEqual(["198.51.100.7, 10.1.1.1"], report["headers"]["x-forwarded-for"])
        self.assertNotIn(b"pdt_x", body)


if __name__ == "__main__":
    unittest.main()
