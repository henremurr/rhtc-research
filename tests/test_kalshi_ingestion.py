import sqlite3
import json
from contextlib import closing
from datetime import datetime, timezone, timedelta
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

    def test_probability_history_and_missing_observations(self):
        stamp = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
        current = {"stamp": stamp.isoformat(), "count": 1}
        row = {"id": "kalshi:A", "probabilities": {"Yes": .65, "No": .35}}
        with closing(k.connect()) as db, db:
            for days, hours, probability in [(1, 0, .5), (7, 13, .4), (30, 0, .3)]:
                prior = (stamp - timedelta(days=days, hours=hours)).isoformat()
                db.execute("INSERT INTO scans VALUES (?,1)", (prior,))
                db.execute("INSERT INTO snapshots VALUES (?,?,?)",
                    (prior, row["id"], json.dumps({"probabilities": {"Yes": probability, "No": 1-probability}})))
        result = k.add_history(current, [row])[0]["changes_pp"]
        self.assertEqual(result["1"], {"Yes": 15.0, "No": -15.0})
        self.assertEqual(result["7"], {})
        self.assertEqual(result["30"], {"Yes": 35.0, "No": -35.0})
        other = {"id": "kalshi:B", "probabilities": {"Yes": .7}}
        self.assertEqual(k.add_history(current, [other])[0]["changes_pp"], {"1": {}, "7": {}, "30": {}})
