import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from laya_evaluate import binary_metrics, expected_criteria, export_rows, load_cases, summarize
from nimrod.laya_interference.criteria import CRITERIA
from nimrod.tests.test_laya_interference import make_state


class EvaluationTest(unittest.TestCase):
    def test_abstention_is_not_a_true_negative_and_recall_counts_missed_positives(self):
        metrics = binary_metrics([(True, True), (True, None), (False, None), (False, False)])
        self.assertEqual(metrics["tp"], 1)
        self.assertEqual(metrics["tn"], 1)
        self.assertEqual(metrics["abstained"], 2)
        self.assertEqual(metrics["recall_all_positives"], .5)
        self.assertEqual(metrics["coverage"], .5)

    def test_overall_labels_do_not_invent_criterion_labels(self):
        self.assertEqual(expected_criteria({"label": "Yes"}), {})
        self.assertEqual(expected_criteria({"label": "No"}), {})

    def test_export_uses_production_payload_and_keeps_labels_out_of_state(self):
        state = make_state()
        case = {"key": ["p", "commit", "Foo", "value()"], "group": "p", "split": "train",
                "scenario": None, "class": "Foo", "item": "value()", "gold": {"criteria": ["C2"]}}
        with patch("laya_evaluate.build_method_state", return_value=state):
            row = list(export_rows([case], "choice_ab"))[0]
        self.assertEqual(row["state"], state.to_payload())
        self.assertEqual(row["expected"][CRITERIA[1].id], "A")
        self.assertEqual(row["expected"][CRITERIA[0].id], "B")
        self.assertNotIn("expected", row["state"])
        self.assertNotIn("gold", row["state"])

    def test_summarize_does_not_treat_high_truncated_scores_as_positive(self):
        record = {"gold": {"label": "Yes", "criteria": ["C2"]}, "assessment": {"criteria": {
            c.id: {"status": "insufficient_context", "probability": .99} for c in CRITERIA}}}
        metrics = summarize([record], .5)
        self.assertEqual(metrics["overall"]["abstained_positive"], 1)
        self.assertEqual(metrics["overall"]["tp"], 0)
        self.assertIsNone(metrics["criteria"][CRITERIA[1].id]["brier_assessed_only"])

    def test_grouping_and_disputed_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path, gold_path = Path(tmp) / "input.json", Path(tmp) / "gold.json"
            scenario = {"projectName": "p", "scenarioCommits": {"merge": "commit"},
                        "scenarioJars": {b: f"/dataset/commit/original/{b}/x.jar" for b in ("base", "left", "right", "merge")},
                        "jarType": "original", "targets": {"Foo": ["first()", "second()", "third()"]}}
            gold = [{"project": "p", "commit": "commit", "class": "Foo", "method": name,
                     "label": "No", "disputed": name == "third()"}
                    for name in scenario["targets"]["Foo"]]
            input_path.write_text(json.dumps([scenario]))
            gold_path.write_text(json.dumps(gold))
            cases, excluded = load_cases(input_path, gold_path, split_by="scenario")
        self.assertEqual(len(cases), 2)
        self.assertEqual(len(excluded), 1)
        self.assertEqual(cases[0]["split"], cases[1]["split"])
        self.assertEqual(cases[0]["group"], cases[1]["group"])


if __name__ == "__main__":
    unittest.main()
