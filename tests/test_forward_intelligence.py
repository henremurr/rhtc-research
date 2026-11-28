import unittest
from datetime import datetime, timezone, timedelta
from app.options import forward_intelligence as fi

class ForwardIntelligenceTests(unittest.TestCase):
    def assessment(self, **changes):
        now=datetime.now(timezone.utc).isoformat()
        return dict(factors={k:1 for k in fi.FIS_WEIGHTS},fis=100,
                    as_of=now,reviewed_at=now,review_approved=True,
                    review_note="Independently verified",adjustment=.25) | changes

    def test_weighting_and_missing(self):
        self.assertEqual(fi.forward_score({k:.5 for k in fi.FIS_WEIGHTS}),50)
        self.assertIsNone(fi.forward_score({k:None for k in fi.FIS_WEIGHTS}))
        self.assertIsNone(fi.forward_score({k:True for k in fi.FIS_WEIGHTS}))
        self.assertIsNone(fi.forward_score({k:float("nan") for k in fi.FIS_WEIGHTS}))

    def test_composite_eligibility(self):
        a=self.assessment()
        self.assertEqual(fi.composite_score(4,3,a),7.25)
        self.assertEqual(fi.composite_score(4,3,self.assessment(adjustment=-.25)),6.75)
        self.assertEqual(fi.composite_score(5,5,a),10)
        self.assertIsNone(fi.composite_score(None,3,a))
        self.assertEqual(fi.composite_score(4,3,self.assessment(review_approved=False)),7)
        self.assertEqual(fi.composite_score(4,3,self.assessment(review_note="")),7)
        self.assertEqual(fi.composite_score(4,3,self.assessment(fis=99)),7)
        stale=(datetime.now(timezone.utc)-timedelta(hours=13)).isoformat()
        future=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        for stamp in (stale,future):
            self.assertEqual(fi.composite_score(4,3,self.assessment(as_of=stamp)),7)
        self.assertEqual(fi.score_fields(4,3,a)["forward_adjustment"],.25)

    def test_candidate_requires_citation_and_nonoverlap(self):
        event={"id":"1","title":"Example","association":"candidate ticker","quality":"higher liquidity",
               "research":{"relevance":10},"changes_pp":{"1":{"Yes":20}},
               "end_date":datetime.now(timezone.utc).date().isoformat()}
        context={"status":"available","as_of":datetime.now(timezone.utc).isoformat(),"selected":[event]}
        url="https://example.com/evidence"
        raw={"market_id":"1","source_url":url,"direction":"positive","rationale":"Evidence",
             "corroborated":True,"already_reflected":False,"economic_impact":1,"corroboration":1}
        candidate=fi.assess_fis_candidate("TEST",raw,context,[{"url":url}])
        self.assertEqual(candidate["fis"],100)
        self.assertFalse(candidate["review_approved"])
        self.assertIsNone(fi.assess_fis_candidate("TEST",raw,context,[]))
        self.assertIsNone(fi.assess_fis_candidate("TEST",raw | {"already_reflected":True},context,[{"url":url}]))
        self.assertIsNone(fi.assess_fis_candidate("TEST",raw | {"source_url":"https://polymarket.com/event"},context,[{"url":"https://polymarket.com/event"}]))

    def test_report_bound_review(self):
        import sqlite3
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from fastapi import HTTPException
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"test.sqlite3"
            def connect():
                db=sqlite3.connect(path)
                db.row_factory=sqlite3.Row
                return db
            with connect() as db:
                db.execute("CREATE TABLE stock_analysis_reports (report_id INTEGER PRIMARY KEY,symbol TEXT)")
                db.execute("INSERT INTO stock_analysis_reports VALUES (1,'TEST')")
            with patch("app.options.api.connect_watchlist_db",side_effect=connect):
                fi.persist_fis("TEST",self.assessment(review_approved=False),1)
                self.assertEqual(fi.latest_fis()["TEST"]["report_id"],1)
                with self.assertRaises(HTTPException):
                    fi.review_fis("TEST",1,True,"")
                approved=fi.review_fis("TEST",1,True,"Verified independent evidence")
                self.assertTrue(fi.eligible_adjustment(approved))
                self.assertFalse(fi.eligible_adjustment(fi.review_fis("TEST",1,False,"Rejected")))
                with connect() as db:
                    db.execute("INSERT INTO stock_analysis_reports VALUES (2,'TEST')")
                self.assertNotIn("TEST",fi.latest_fis())
                with self.assertRaises(HTTPException):
                    fi.review_fis("TEST",1,True,"Old report")
