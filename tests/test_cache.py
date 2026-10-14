#!/usr/bin/env python3
"""Cache des réponses : durées, datation, retrait Judilibre, erreurs, hors réseau."""
from __future__ import annotations

import datetime as dt
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
from mcp_server.cache import ResponseCache  # noqa: E402
from mcp_server.store import Store  # noqa: E402
from pandecte.errors import LegifranceError  # noqa: E402

ARTICLE = {"id": "LEGIARTI000032041571", "title": "Article 1240", "text": "Tout fait…",
           "metadata": {"as_of_date": "2026-10-14", "source": "Légifrance API"}}
DECISION = {"id": "667e8f1a2b3c4d5e6f708192", "title": "Cour de cassation…", "text": "…",
            "metadata": {"retrieved_at": "2026-10-14T08:00:00+00:00", "source": "Judilibre"}}


class Clock:
    def __init__(self) -> None:
        self.now = 1_792_000_000.0
        self.day = dt.date(2026, 10, 14)


class ResponseCacheTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.addCleanup(self.store.close)
        self.clock = Clock()
        self.suppressed: frozenset[str] = frozenset()
        self.cache = self.make()

    def make(self, **overrides) -> ResponseCache:
        options = dict(text_ttl=6 * 3600, decision_ttl=24 * 3600, max_bytes=10_000_000)
        options.update(overrides)
        return ResponseCache(
            self.store, suppressed=lambda: self.suppressed,
            clock=lambda: self.clock.now, today=lambda: self.clock.day, **options,
        )

    def roundtrip(self, operation, args, result, kwargs=None):
        plan = self.cache.plan(operation, args, kwargs or {})
        self.cache.put(plan, result)
        return plan, self.cache.get(plan)

    def test_article_is_served_from_cache_with_its_retrieval_date(self):
        _, cached = self.roundtrip("get_article", ("LEGIARTI000032041571", None), dict(ARTICLE))
        self.assertTrue(cached["metadata"]["from_cache"])
        self.assertEqual(
            dt.datetime.fromtimestamp(int(self.clock.now), dt.timezone.utc).isoformat(),
            cached["metadata"]["retrieved_at"],
        )
        self.assertEqual(ARTICLE["text"], cached["text"])

    def test_decision_keeps_its_original_retrieved_at(self):
        self.clock.now += 3600
        _, cached = self.roundtrip("get_decision", (DECISION["id"],), dict(DECISION))
        self.assertEqual("2026-10-14T08:00:00+00:00", cached["metadata"]["retrieved_at"])

    def test_durations(self):
        text_plan, _ = self.roundtrip("get_text", ("LEGITEXT000006070721", None), {"id": "T"})
        decision_plan, _ = self.roundtrip("get_decision", ("abc",), {"id": "abc"})
        self.clock.now += 6 * 3600 + 1
        self.assertIsNone(self.cache.get(text_plan))
        self.assertIsNotNone(self.cache.get(decision_plan))
        self.clock.now += 18 * 3600
        self.assertIsNone(self.cache.get(decision_plan))

    def test_a_new_server_day_never_reuses_yesterday_dating(self):
        plan, _ = self.roundtrip("get_article", ("LEGIARTI000032041571", None), dict(ARTICLE))
        self.clock.day += dt.timedelta(days=1)
        self.assertNotEqual(plan.key, self.cache.plan("get_article", ("LEGIARTI000032041571", None), {}).key)

    def test_searches_are_never_cached(self):
        for operation in ("search", "search_articles", "search_case_law", "inconnu"):
            self.assertIsNone(self.cache.plan(operation, ("x",), {}))

    def test_fetch_follows_the_identifier_kind(self):
        self.assertEqual("text", self.cache.plan("fetch", ("LEGIARTI000032041571",), {}).kind)
        self.assertEqual("decision", self.cache.plan("fetch", ("667e8f1a",), {}).kind)

    def test_zero_duration_disables_a_kind(self):
        cache = self.make(decision_ttl=0)
        self.assertIsNone(cache.plan("get_decision", ("abc",), {}))
        self.assertIsNotNone(cache.plan("get_article", ("LEGIARTI000032041571",), {}))

    def test_withdrawn_decision_is_dropped_on_read(self):
        plan, cached = self.roundtrip("fetch", (DECISION["id"].upper(),), dict(DECISION))
        self.assertIsNotNone(cached)
        self.suppressed = frozenset({DECISION["id"]})
        self.assertIsNone(self.cache.get(plan))
        self.assertEqual((0, 0), self.store.cache_size())

    def test_incomplete_or_oversized_results_are_not_stored(self):
        for result in ({}, {"title": "sans id"}, None):
            self.roundtrip("get_article", ("LEGIARTI000000000001",), result)
        cache = self.make(max_bytes=1000)
        plan = cache.plan("get_text", ("LEGITEXT000000000001",), {})
        cache.put(plan, {"id": "T", "text": "x" * 200})
        self.assertEqual(0, self.store.cache_size()[0])

    def test_size_cap_evicts_the_oldest_entries(self):
        cache = self.make(max_bytes=50_000)
        for index in range(60):
            plan = cache.plan("get_text", (f"LEGITEXT{index:012d}",), {})
            cache.put(plan, {"id": f"T{index}", "text": "x" * 2_000})
            self.clock.now += 1
        count, size = self.store.cache_size()
        self.assertLessEqual(size, 50_000 + 2_100 * 10)  # ménage toutes les 50 écritures
        self.assertLess(count, 60)
        newest = cache.plan("get_text", (f"LEGITEXT{59:012d}",), {})
        self.assertIsNotNone(cache.get(newest))

    def test_key_holds_no_user_data(self):
        plan = self.cache.plan("get_article", ("LEGIARTI000032041571", None), {})
        self.assertRegex(plan.key, r"^[0-9a-f]{64}$")


class ServerCacheTests(OAuthServerCase):
    """Le cache tel que le serveur l'applique autour des outils."""

    def setUp(self):
        self.calls = 0

    def counting(self, result=None, error=None):
        def get_article(id, date=None):  # noqa: A002 — même signature que l'outil
            self.calls += 1
            if error is not None:
                raise error
            return dict(result, id=id)

        return get_article

    def call(self, article_id):
        # Un sujet par test : le quota par minute du socle (2) reste par sujet.
        return self.call_tool(self.token(sub=self.id()), "get_article", {"id": article_id})

    def test_second_read_does_not_reach_the_api(self):
        with mock.patch.object(mcp_app.legal_tools, "get_article", self.counting(ARTICLE)):
            with self.assertLogs("pandecte.mcp", level="INFO") as journal:
                first = self.call("LEGIARTI000000000101")
                second = self.call("LEGIARTI000000000101")
        self.assertEqual(1, self.calls)
        self.assertNotIn("from_cache", self.contenu_structure(first)["metadata"])
        self.assertTrue(self.contenu_structure(second)["metadata"]["from_cache"])
        rendu = " ".join(journal.output)
        self.assertIn("cache=miss", rendu)
        self.assertIn("cache=hit", rendu)

    def test_errors_are_never_cached(self):
        failing = self.counting(error=LegifranceError("Article introuvable.", exit_code=5))
        with mock.patch.object(mcp_app.legal_tools, "get_article", failing):
            self.assertTrue(self.en_erreur(self.call("LEGIARTI000000000102")))
        with mock.patch.object(mcp_app.legal_tools, "get_article", self.counting(ARTICLE)):
            resultat = self.call("LEGIARTI000000000102")
        self.assertFalse(self.en_erreur(resultat))
        self.assertNotIn("from_cache", self.contenu_structure(resultat)["metadata"])
        self.assertEqual(2, self.calls)

    def test_cache_hits_still_count_against_the_user_quota(self):
        # Le quota protège aussi le service contre l'abus, pas seulement PISTE.
        with mock.patch.object(mcp_app.legal_tools, "get_article", self.counting(ARTICLE)):
            for _ in range(2):
                self.call("LEGIARTI000000000103")
            troisieme = self.call("LEGIARTI000000000103")
        self.assertTrue(self.en_erreur(troisieme))
        self.assertIn("par minute", str(troisieme.content))


if __name__ == "__main__":
    unittest.main()
