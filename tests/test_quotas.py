#!/usr/bin/env python3
"""Limite de débit par adresse IP, hors réseau."""
from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp_server.quotas import (  # noqa: E402
    IpRateLimit,
    QuotaExceeded,
    SlidingWindow,
    format_delay,
)
from mcp_server.runtime import RuntimeCapacityError  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.monotonic = 1000.0

    def advance(self, seconds: float) -> None:
        self.monotonic += seconds


class IpRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.limit = IpRateLimit(2, clock=lambda: self.clock.monotonic)

    def test_limit_gives_exact_retry_after(self):
        self.limit.check("203.0.113.7")
        self.clock.advance(10)
        self.limit.check("203.0.113.7")
        with self.assertRaises(QuotaExceeded) as ctx:
            self.limit.check("203.0.113.7")
        self.assertEqual(51, ctx.exception.retry_after)
        self.assertIn("51 s", str(ctx.exception))
        self.clock.advance(50.5)
        self.limit.check("203.0.113.7")

    def test_addresses_are_independent(self):
        self.limit.check("203.0.113.7")
        self.limit.check("203.0.113.7")
        self.limit.check("198.51.100.1")

    def test_refused_call_consumes_nothing(self):
        for _ in range(2):
            self.limit.check("203.0.113.7")
        for _ in range(5):
            with self.assertRaises(QuotaExceeded):
                self.limit.check("203.0.113.7")
        self.clock.advance(60)
        self.limit.check("203.0.113.7")
        self.limit.check("203.0.113.7")

    def test_concurrent_calls_never_exceed_the_limit(self):
        limit = IpRateLimit(5)
        accepted, lock = [], threading.Lock()

        def call():
            try:
                limit.check("203.0.113.9")
            except QuotaExceeded:
                return
            with lock:
                accepted.append(1)

        threads = [threading.Thread(target=call) for _ in range(40)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(5, len(accepted))

    def test_quota_error_is_a_capacity_error(self):
        self.assertTrue(issubclass(QuotaExceeded, RuntimeCapacityError))


class HelperTests(unittest.TestCase):
    def test_format_delay(self):
        self.assertEqual("42 s", format_delay(42))
        self.assertEqual("3 min 05 s", format_delay(185))
        self.assertEqual("2 h 07 min", format_delay(7620))

    def test_sliding_window_memory_is_bounded(self):
        clock = FakeClock()
        window = SlidingWindow(1, clock=lambda: clock.monotonic)
        for index in range(1000):
            window.hit(f"ip-{index}")
            clock.advance(1)
        self.assertLessEqual(window.tracked_keys, 61)


if __name__ == "__main__":
    unittest.main()
