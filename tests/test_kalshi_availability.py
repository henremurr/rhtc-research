import asyncio
import unittest
from unittest.mock import patch
from app.options import prediction_markets as pm

class AvailabilityTests(unittest.TestCase):
    def test_exhausted_budget_skips_catalog_hydration(self):
        with patch.dict("os.environ",{"OPENAI_API_KEY":"test"}), patch.object(pm,"daily_usage",return_value={"requests":100,"request_limit":100,"input_tokens":1,"output_tokens":1,"token_limit":1000000}), patch.object(pm,"research_status") as status, patch.object(pm,"latest",side_effect=AssertionError("unbounded read")):
            asyncio.run(pm.enrich_pending())
            self.assertEqual(status.call_args.args[0],"budget limited")

    def test_recovery_pause_skips_catalog_hydration(self):
        with patch.dict("os.environ",{"OPENAI_API_KEY":"test","RHTC_PREDICTION_RESEARCH_PAUSED":"1"}), patch.object(pm,"daily_usage",return_value={"requests":0,"request_limit":100,"input_tokens":0,"output_tokens":0,"token_limit":1000000}), patch.object(pm,"research_status") as status, patch.object(pm,"latest",side_effect=AssertionError("unbounded read")):
            asyncio.run(pm.enrich_pending())
            self.assertEqual(status.call_args.args[0],"paused")
