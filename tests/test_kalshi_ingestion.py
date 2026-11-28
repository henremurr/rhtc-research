import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.options import kalshi_ingestion as k


def market(ticker):
    return {"ticker": ticker, "market_type": "binary", "status": "active"}


class KalshiIngestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch("app.options.api.watchlist_db_path", return_value=Path(self.tmp.name) / "watchlist.sqlite3")
        p.start()
        self.addCleanup(p.stop)

    def test_resume_and_atomic_publish(self):
        cp = k.begin()
        cp = k.persist(cp, [market("A")], "next")
        self.assertEqual(k.begin(), cp)
        self.assertEqual(k.latest(), (None, []))
        with self.assertRaisesRegex(ValueError, "incomplete"):
            k.finish(cp)
        cp = k.persist(cp, [market("B")], None)
        self.assertEqual(k.finish(cp), 2)
        scan, rows = k.latest()
        self.assertEqual(scan["count"], 2)
        self.assertEqual({r["id"] for r in rows}, {"kalshi:A", "kalshi:B"})

    def test_empty_attempt_preserves_prior(self):
        cp = k.persist(k.begin(), [market("A")], None)
        k.finish(cp)
        previous = k.latest()
        cp = k.persist(k.begin(), [], None)
        with self.assertRaisesRegex(ValueError, "Empty"):
            k.finish(cp)
        self.assertEqual(k.latest(), previous)
        self.assertFalse(k.begin()["exhausted"])

    def test_repeated_cursor_rolls_back(self):
        cp = k.persist(k.begin(), [market("A")], "next")
        with self.assertRaisesRegex(ValueError, "stopped advancing"):
            k.persist(cp, [market("B")], "next")
        self.assertEqual(k.begin(), cp)
        cp = k.persist(cp, [], None)
        self.assertEqual(k.finish(cp), 1)

    def test_stale_checkpoint_rejected(self):
        cp = k.begin()
        newer = k.persist(cp, [market("A")], "next")
        with self.assertRaisesRegex(ValueError, "changed"):
            k.persist(cp, [market("B")], None)
        self.assertEqual(k.begin(), newer)

    def test_nonbinary_and_closed_excluded(self):
        cp = k.persist(k.begin(), [market("A"), dict(market("B"), market_type="scalar"),
                                    dict(market("C"), status="closed")], None)
        self.assertEqual(k.finish(cp), 1)
