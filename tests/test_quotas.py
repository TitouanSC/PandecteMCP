#!/usr/bin/env python3
"""Stockage SQLite et quotas des deux modes d'accès, hors réseau."""
from __future__ import annotations

import datetime as dt
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp_server.quotas import (  # noqa: E402
    GLOBAL_SCOPE,
    QuotaExceeded,
    QuotaPolicy,
    SlidingWindow,
    format_delay,
)
from mcp_server.runtime import RuntimeCapacityError  # noqa: E402
from mcp_server.store import Store  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.monotonic = 1000.0
        self.utc = dt.datetime(2026, 10, 14, 22, 0, tzinfo=dt.timezone.utc)

    def advance(self, seconds: float) -> None:
        self.monotonic += seconds
        self.utc += dt.timedelta(seconds=seconds)


def policy(store: Store, clock: FakeClock, **limits) -> QuotaPolicy:
    values = dict(user_per_minute=3, user_per_day=5, global_per_day=8, keys_per_minute_per_ip=2)
    values.update(limits)
    return QuotaPolicy(store, clock=lambda: clock.monotonic, now=lambda: clock.utc, **values)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)

    def test_one_active_token_per_subject(self):
        self.store.replace_token("user_1", "hash-a")
        self.store.replace_token("user_1", "hash-b")
        self.assertIsNone(self.store.subject_for("hash-a"))
        self.assertEqual("user_1", self.store.subject_for("hash-b"))
        self.store.revoke("user_1")
        self.assertIsNone(self.store.subject_for("hash-b"))
        self.assertFalse(self.store.has_token("user_1"))

    def test_consume_is_all_or_nothing(self):
        self.assertIsNone(self.store.consume("2026-10-14", [("a", 1), ("b", 5)]))
        self.assertEqual("a", self.store.consume("2026-10-14", [("a", 1), ("b", 5)]))
        self.assertEqual(1, self.store.count("b", "2026-10-14"))

    def test_counters_survive_a_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data" / "pandecte.sqlite3"
            first = Store(path)
            first.consume("2026-10-14", [("user:x", 10)])
            first.replace_token("x", "h")
            first.close()
            second = Store(path)
            self.assertEqual(1, second.count("user:x", "2026-10-14"))
            self.assertEqual("x", second.subject_for("h"))
            second.close()

    def test_old_counters_are_purged(self):
        self.store.consume("2026-10-13", [("a", 5)])
        self.store.purge_counters_before("2026-10-14")
        self.assertEqual(0, self.store.count("a", "2026-10-13"))


class SharedModeQuotaTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.policy = policy(self.store, self.clock)

    def test_minute_limit_gives_exact_retry_after(self):
        for _ in range(3):
            self.policy.check_shared("alice")
            self.clock.advance(10)
        with self.assertRaises(QuotaExceeded) as caught:
            self.policy.check_shared("alice")
        # Le plus ancien appel sort de la fenêtre 30 s plus tard.
        self.assertEqual(31, caught.exception.retry_after)
        self.assertIn("par minute", str(caught.exception))
        self.clock.advance(31)
        self.policy.check_shared("alice")

    def test_daily_limit_resets_at_utc_midnight(self):
        for _ in range(5):
            self.policy.check_shared("alice")
            self.clock.advance(61)
        with self.assertRaises(QuotaExceeded) as caught:
            self.policy.check_shared("alice")
        self.assertIn("journalier", str(caught.exception))
        self.assertIn("00:00 UTC", str(caught.exception))
        self.assertAlmostEqual(2 * 3600 - 5 * 61, caught.exception.retry_after, delta=2)
        self.clock.advance(caught.exception.retry_after)
        self.policy.check_shared("alice")

    def test_refused_call_consumes_nothing(self):
        for _ in range(5):
            self.policy.check_shared("alice")
            self.clock.advance(61)
        for _ in range(3):
            with self.assertRaises(QuotaExceeded):
                self.policy.check_shared("alice")
        day = self.clock.utc.date().isoformat()
        self.assertEqual(5, self.store.count("user:alice", day))
        self.assertEqual(5, self.store.count(GLOBAL_SCOPE, day))

    def test_global_limit_protects_the_owner_quota(self):
        for user in ("a", "b", "c", "d"):
            for _ in range(2):
                self.policy.check_shared(user)
        with self.assertRaises(QuotaExceeded) as caught:
            self.policy.check_shared("e")
        self.assertIn("serveur partagé", str(caught.exception))
        self.assertIn("vos propres clés", str(caught.exception))

    def test_users_are_independent(self):
        for _ in range(3):
            self.policy.check_shared("alice")
        self.policy.check_shared("bob")

    def test_concurrent_calls_never_exceed_the_minute_limit(self):
        accepted: list[int] = []
        barrier = threading.Barrier(10)

        def call() -> None:
            barrier.wait()
            try:
                self.policy.check_shared("alice")
                accepted.append(1)
            except QuotaExceeded:
                pass

        threads = [threading.Thread(target=call) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(3, len(accepted))

    def test_quota_error_is_a_capacity_error(self):
        # Le serveur traite déjà RuntimeCapacityError comme un refus propre.
        self.assertTrue(issubclass(QuotaExceeded, RuntimeCapacityError))


class PersonalKeysQuotaTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.policy = policy(self.store, self.clock)

    def test_only_ip_rate_applies_and_owner_counters_stay_untouched(self):
        self.policy.check_personal_keys("203.0.113.7")
        self.policy.check_personal_keys("203.0.113.7")
        with self.assertRaises(QuotaExceeded) as caught:
            self.policy.check_personal_keys("203.0.113.7")
        self.assertEqual(61, caught.exception.retry_after)
        self.policy.check_personal_keys("198.51.100.1")
        day = self.clock.utc.date().isoformat()
        self.assertEqual(0, self.store.count(GLOBAL_SCOPE, day))


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
