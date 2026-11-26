"""Offline evaluator checks: genuine synthetic inputs, fixed threshold, ROC ties."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.evaluate_laya_synthetic import binary_metrics, load_inputs, roc_curve, run_evaluation, write_outputs

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dataset-sintetico/laya_global_eval.jsonl"
MODEL = ROOT / "laya_checkpoints/laya_semantic_global"


class SyntheticEvaluationTests(unittest.TestCase):
    def test_external_cases_and_labels_match_execution_gold(self):
        rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines()]
        gold = json.loads((ROOT / "dataset-sintetico/gold-sintetico.json").read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 20)
        self.assertEqual(sum(r["_meta"]["label"] == "Yes" for r in rows), 12)
        for row, actual in zip(rows, gold):
            self.assertEqual(row["_meta"]["id"], actual["commit"])
            self.assertEqual(row["_meta"]["label"], actual["label"])
            self.assertEqual(set(row["questions"]), {"semantic_interference"})
            folder = ROOT / "dataset-sintetico/cases" / actual["commit"] / "source" / actual["class"].rsplit(".", 1)[1]
            for branch in ("base", "left", "right", "merge"):
                self.assertIn((folder / f"{branch}.java").read_text(encoding="utf-8"), row["state"])
            self.assertNotIn("gold_criteria", row["state"])
            self.assertNotIn('"observed"', row["state"])

    def test_metrics_exclude_truncation_and_report_coverage(self):
        rows = [{"gold": y, "probability": p, "status": status} for y,p,status in
                ((True,.8,"ok"),(False,.6,"ok"),(False,.1,"ok"),(True,.2,"ok"),(True,.99,"truncated"))]
        actual = binary_metrics(rows, .5)
        self.assertEqual((actual["tp"],actual["fp"],actual["tn"],actual["fn"]), (1,1,1,1))
        self.assertEqual(actual["coverage"], .8)
        self.assertEqual(actual["f1"], .5)

    def test_roc_perfect_reverse_and_ties(self):
        def rows(positive,negative):
            return [{"gold":True,"probability":positive,"status":"ok"},
                    {"gold":False,"probability":negative,"status":"ok"}]
        self.assertEqual(roc_curve(rows(.9,.1))["auc"], 1.)
        self.assertEqual(roc_curve(rows(.1,.9))["auc"], 0.)
        self.assertEqual(roc_curve(rows(.5,.5))["auc"], .5)
        self.assertEqual(len(roc_curve(rows(.5,.5))["points"]), 2)
        self.assertIsNone(roc_curve(rows(.9,.1)[:1])["auc"])

    def test_threshold_is_loaded_from_real_validation_not_synthetic_scores(self):
        rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines()]
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp)
            (model / "questions.json").write_text(json.dumps(rows[0]["questions"]))
            (model / "rl_agent_config.json").write_text(json.dumps({"max_len":8192,"head_max_len":512}))
            (model / "scenario_evaluation.json").write_text(json.dumps({"validation_selected_threshold":.63}))
            _,_,_,threshold,source = load_inputs(model,DATA)
            self.assertEqual(threshold,.63)
            self.assertEqual(source,"real_dataset_validation")
            self.assertEqual(load_inputs(model,DATA,.7)[3],.7)

    def test_inference_only_receives_state_question_and_prediction_budget(self):
        row = json.loads(DATA.read_text(encoding="utf-8").splitlines()[0])
        class Agent:
            def predict(inner,state,questions,*,max_len,head_max_len):
                self.assertEqual(state,row["state"])
                self.assertEqual(questions,row["questions"])
                self.assertEqual((max_len,head_max_len),(8192,512))
                return {"answers":{"semantic_interference":{"noul":.2}},"usage":{"truncated":0}}
        with contextlib.redirect_stdout(io.StringIO()):
            predictions = run_evaluation(Agent(),[row],row["questions"],8192,512)
        self.assertEqual(predictions[0]["status"],"ok")
        self.assertFalse(predictions[0]["gold"])
        self.assertEqual(predictions[0]["probability"],.2)
        predictions[0]["prediction"] = False
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            report = {"predictions":predictions,"roc":roc_curve(predictions)}
            write_outputs(out,report)
            self.assertTrue(out.exists())
            self.assertTrue(out.with_suffix(".csv").exists())
            self.assertTrue(out.with_name("report_roc.csv").exists())


if __name__ == "__main__":
    unittest.main()
