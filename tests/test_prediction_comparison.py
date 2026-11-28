import unittest
from app.options.prediction_comparison import compare


def row(provider, probability, **overrides):
    return dict(id=provider+":A", provider=provider, title="Will event occur?",
                description="Resolves yes if event occurs by deadline.",
                end_date="2026-12-01T00:00:00Z",
                observed_at="2026-11-27T12:00:00Z",
                probabilities={"Yes": probability, "No": 1-probability}) | overrides


class ComparisonTests(unittest.TestCase):
    def test_divergence(self):
        result = compare([row("polymarket", .72), row("kalshi", .58)])
        self.assertEqual(result[0]["classification"], "divergence")
        self.assertEqual(result[0]["kalshi_minus_polymarket_pp"], -14)

    def test_agreement(self):
        self.assertEqual(compare([row("polymarket", .5), row("kalshi", .54)])[0]["classification"], "agreement")

    def test_different_rules_deadlines_or_observation_times(self):
        for changes in [{"description": "Other rules"}, {"end_date": "2026-12-02T00:00:00Z"},
                        {"observed_at": "2026-11-27T14:00:00Z"}]:
            self.assertEqual(compare([row("polymarket", .5), row("kalshi", .6, **changes)]), [])

    def test_ambiguous_pair(self):
        self.assertEqual(compare([row("polymarket", .5), row("kalshi", .6),
                                  row("kalshi", .7, id="kalshi:B")]), [])
