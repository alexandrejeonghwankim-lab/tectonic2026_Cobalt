import csv
import tempfile
import unittest
from pathlib import Path

import generate_data
from intent_engine import (CATALOGUE, TEMPLATES, backtest, compile_intent, customer_decision,
                           decide, eligible, matches, population, profiles, validate)


class IntentEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.people = {p["first_name"]: p for p in profiles()[:8]}
        cls.rows = {row["customer_id"]: row for row in population()[:8]}

    def row(self, name):
        return self.rows[self.people[name]["customer_id"]]

    def test_generated_data_is_diverse_and_reproducible(self):
        with tempfile.TemporaryDirectory() as temp:
            counts = generate_data.generate(population=80, profile_count=10, output=Path(temp))
            self.assertEqual(sum(counts.values()), 80)
            with (Path(temp) / "signals.csv").open(newline="") as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), 80)
            self.assertEqual(len({row["customer_id"] for row in rows}), 80)
            self.assertTrue(any(int(row["age"]) < 18 for row in rows))
            self.assertTrue(all(row["consent_tier"] == "service" for row in rows if int(row["age"]) < 18))
            self.assertTrue(all(int(row["childcare_planning_opt_in"]) == 0 for row in rows if int(row["age"]) < 18))
            self.assertTrue(all("term_deposit" not in row and "marital" not in row for row in rows))
            self.assertGreaterEqual(counts["under 18"], 1)

    def test_compiler_is_guided_and_rejects_sensitive_requests(self):
        self.assertEqual(compile_intent("Help with childcare costs")["intent_id"], "childcare")
        for text in ("Infer new parent from baby purchases", "Target health expenses", "Offer investment advice", "Target minors", "Childcare and savings buffer", "", "Anything whatsoever"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                compile_intent(text)

    def test_governance_rejects_changes_to_reviewed_spec(self):
        spec = {**TEMPLATES["childcare"], "conditions": [{"signal": "new_child_likely", "op": "=", "value": True}]}
        with self.assertRaises(ValueError):
            validate(spec)
        with self.assertRaises(ValueError):
            validate({**TEMPLATES["childcare"], "message": "Get a loan now!"})
        with self.assertRaises(ValueError):
            validate({**TEMPLATES["childcare"], "min_consent_tier": "service"})
        self.assertNotIn("new_child_likely", CATALOGUE)

    def test_underage_and_service_only_cannot_receive_guidance(self):
        for name in ("Noor", "Sam"):
            row = self.row(name)
            self.assertFalse(eligible(row, TEMPLATES["buffer"]))
            winner, _ = decide(row, list(TEMPLATES.values()))
            self.assertIsNone(winner)

    def test_childcare_requires_explicit_opt_in_and_consent(self):
        lotte = self.row("Lotte")
        sam = self.row("Sam")
        self.assertTrue(matches(lotte, TEMPLATES["childcare"]))
        self.assertTrue(eligible(lotte, TEMPLATES["childcare"]))
        self.assertTrue(matches(sam, TEMPLATES["childcare"]))
        self.assertFalse(eligible(sam, TEMPLATES["childcare"]))
        self.assertFalse(matches(self.row("Jules"), TEMPLATES["childcare"]))

    def test_arbitration_selects_only_one_and_records_silence(self):
        winner, suppressed = decide(self.row("Lotte"), list(TEMPLATES.values()))
        self.assertEqual(winner["intent_id"], "childcare")
        self.assertTrue(any(s["intent_id"] == "buffer" for s in suppressed))
        winner, suppressed = decide(self.row("Claire"), list(TEMPLATES.values()))
        self.assertIsNone(winner)
        self.assertTrue(any("budget" in s["reason"].lower() for s in suppressed))

    def test_optout_immediately_suppresses_customer(self):
        person = self.people["Lotte"]
        before = customer_decision(person, list(TEMPLATES.values()))
        after = customer_decision(person, list(TEMPLATES.values()), frozenset([person["customer_id"]]))
        self.assertTrue(before["sent"])
        self.assertFalse(after["sent"])
        self.assertGreaterEqual(len(after["suppressed"]), 1)

    def test_not_relevant_feedback_suppresses_without_changing_consent(self):
        person = self.people["Lotte"]
        after = customer_decision(person, list(TEMPLATES.values()), not_relevant=frozenset([person["customer_id"]]))
        self.assertFalse(after["sent"])
        self.assertEqual(after["consent"], "guidance")
        self.assertTrue(all("Not relevant" in item["reason"] for item in after["suppressed"]))

    def test_backtest_counts_and_age_channel_gates(self):
        report = backtest(TEMPLATES["childcare"], [TEMPLATES["buffer"], TEMPLATES["cashflow"], TEMPLATES["moving"]])
        self.assertEqual(report["population"], 100_000)
        self.assertGreater(report["matched"], 0)
        self.assertGreater(report["overlap"], 0)
        self.assertLessEqual(report["selected"], report["consented"])
        self.assertLessEqual(report["consented"], report["matched"])
        self.assertEqual(report["ages"].get("under 18", 0), 0)
        self.assertEqual(sum(report["channels"].values()), report["selected"])


if __name__ == "__main__":
    unittest.main()
