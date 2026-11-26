"""Check real-corpus evaluation retains split boundaries and context exclusions."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.evaluate_laya_mergedataset import evaluate_originals, partition_results, prepare_rows
from scripts.evaluate_laya_synthetic import write_outputs
from scripts.audit_laya_env import read_public_settings, audit
from scripts.compare_laya_contexts import compare_runs

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "laya_training_data/mergedataset_full_colab"


class RealCorpusEvaluationTests(unittest.TestCase):
    def test_one_original_per_case_and_no_augmentation(self):
        manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
        original = [json.loads(line) for line in (DATA / "all.jsonl").read_text(encoding="utf-8").splitlines()
                    if json.loads(line)["_meta"]["variant"] == 0]
        rejected = original[0]["_meta"]["case_id"]
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp)
            (model / "questions.json").write_text((DATA / "questions.json").read_text(encoding="utf-8"), encoding="utf-8")
            (model / "rl_agent_config.json").write_text(json.dumps({"max_len":8192,"head_max_len":512}))
            (model / "manifest.json").write_text(json.dumps(manifest))
            (model / "context_audit.json").write_text(json.dumps({s:{"rejected_case_ids":[rejected] if s=="train" else []} for s in ("train","validation","test")}))
            (model / "scenario_evaluation.json").write_text(json.dumps({"validation_selected_threshold":.5}))
            rows,_,_,threshold,_ = prepare_rows(DATA,model)
            self.assertEqual(len(rows),90)
            self.assertEqual({r["_meta"]["variant"] for r in rows},{0})
            self.assertEqual(len({r["_meta"]["id"] for r in rows}),90)
            self.assertEqual(rows[0]["_meta"]["exposure"],"not_used_due_to_context")
            self.assertEqual(threshold,.5)
            self.assertTrue(all(r["_meta"]["exposure"] == "held_out_test" for r in rows if r["_meta"]["split"] == "test"))
            manifest["source_revision"] = "other"
            (model / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"revision"):
                prepare_rows(DATA,model)

    def test_oversize_case_is_not_sent_to_model(self):
        class Tokenizer:
            def encode(inner,state,add_special_tokens=False):
                return list(range(10 if state == "short" else 100))
        calls = []
        class Agent:
            tok = Tokenizer()
            def predict(inner,state,questions,*,max_len,head_max_len):
                calls.append(state)
                return {"answers":{"semantic_interference":{"noul":.8}},"usage":{"truncated":0}}
        rows = [{"state":state,"_meta":{"id":state,"class":"C","method":"m()",
                                         "label":"Yes","split":"test","exposure":"held_out_test"}}
                for state in ("short","long")]
        with contextlib.redirect_stdout(io.StringIO()):
            result = evaluate_originals(Agent(),rows,{"semantic_interference":{}},50,5)
        self.assertEqual(calls,["short"])
        self.assertEqual(result[1]["status"],"context_excluded")
        self.assertIsNone(result[1]["probability"])
        test = partition_results(result,.5)["test"]
        self.assertEqual(test["metrics"]["coverage"],.5)
        self.assertEqual(test["metrics"]["tp"],1)

    def test_training_metrics_do_not_replace_held_out_test(self):
        rows = [{"gold":gold,"probability":p,"split":split,"id":str(i),"status":"ok"}
                for i,(gold,p,split) in enumerate(((False,.1,"train"),(True,.2,"test"),(False,.9,"test")))]
        result = partition_results(rows,.5)
        self.assertEqual(result["train"]["metrics"]["accuracy"],1.)
        self.assertEqual(result["test"]["metrics"]["accuracy"],0.)
        self.assertEqual(result["test"]["roc"]["auc"],0.)
        self.assertEqual(result["validation"]["metrics"]["n"],0)

    def test_csv_retains_split_and_training_exposure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            report = {"roc":{"points":[]},"predictions":[{
                "id":"one","split":"train","exposure":"trained","source_tokens":12,
                "gold":True,"probability":.8,"prediction":True,"status":"ok"}]}
            write_outputs(path,report,extra_fields=("split","exposure","source_tokens"))
            import csv
            with path.with_suffix(".csv").open(encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["split"],"train")
            self.assertEqual(row["exposure"],"trained")

    def test_env_audit_only_retains_explicit_public_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text('DEEPSEEK_API_KEY=private-test-value\nSMAT_LAYA_MODEL=multilingual\nSMAT_LAYA_MAX_LEN=4048\nPATH_DATASET="/datasets/dataset-sintetico"\n',encoding="utf-8")
            settings = read_public_settings(env)
        self.assertNotIn("private-test-value",json.dumps(settings))
        report = audit(settings,{"max_len":8192,"head_max_len":512},{"predictions":[
            {"source_tokens":1000,"gold":True,"split":"test"},
            {"source_tokens":5000,"gold":False,"split":"test"}]})
        self.assertEqual(report["context_coverage_estimates"]["4048"]["fit_cases"],1)
        self.assertEqual(report["context_coverage_estimates"]["8192"]["fit_cases"],2)
        self.assertEqual(len(report["findings"]),4)

    def test_context_comparison_uses_identical_model_and_common_cases(self):
        common = {"id":"one","gold":True,"probability":.8,"status":"ok","class":"C","method":"m()","split":"test"}
        extra = {"id":"two","gold":False,"probability":.2,"status":"ok","class":"C","method":"n()","split":"test"}
        base = {"model_sha256":"same","data_sha256":"same","question":"semantic_interference","threshold":.5,
                "metrics":{},"partitions":{},"predictions":[common]}
        a,b = {**base,"max_len":4048},{**base,"max_len":8192,"predictions":[common,extra]}
        result = compare_runs(a,b)
        self.assertEqual(result["common_cases"],1)
        self.assertEqual(result["changed_decision_ids"],[])
        self.assertEqual(len(result["additional_full_context_cases"]),1)
        with self.assertRaisesRegex(ValueError,"model_sha256"):
            compare_runs(a,{**b,"model_sha256":"different"})


if __name__ == "__main__":
    unittest.main()
