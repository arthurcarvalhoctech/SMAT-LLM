"""Offline checks for provenance, labels, semantic-preserving views and splits."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import types

from scripts.prepare_laya_colab import load_criteria, render_state, source_files, extract, read_catalog, split_groups
from scripts.train_laya_colab import refresh_gold, audit_rows
from scripts.build_laya_kaggle_notebook import KAGGLE_INPUT_CELL

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "laya_training_data/mergedataset_full_colab"


class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = [json.loads(line) for line in (DATA / "all.jsonl").read_text(encoding="utf-8").splitlines()]
        cls.cases = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))
        cls.questions = json.loads((DATA / "questions.json").read_text(encoding="utf-8"))

    def test_exactly_four_views_of_ninety_real_cases(self):
        self.assertEqual(len(self.rows), 360)
        counts = Counter(row["_meta"]["case_id"] for row in self.rows)
        self.assertEqual(set(counts.values()), {4})
        self.assertEqual(len(counts), 90)
        self.assertEqual(Counter(case["label"] for case in self.cases), {"No": 73, "Yes": 17})

    def test_unknown_criteria_are_not_fabricated(self):
        for row in self.rows:
            self.assertEqual(set(row["gold"]), {"semantic_interference"})
            label = row["_meta"]["label"] == "Yes"
            self.assertEqual(row["gold"]["semantic_interference"]["probabilities"],
                             {"false": float(not label), "true": float(label)})

    def test_project_question_definitions_match_exactly(self):
        criteria = load_criteria()
        expected = criteria.build_questions(witness_candidates=criteria.WITNESS_CANDIDATE_DESCRIPTIONS)
        actual = {k:v for k,v in self.questions.items() if k != "semantic_interference"}
        self.assertEqual(actual, expected)

    def test_every_view_retains_all_source_snippets(self):
        by_id = {case["id"]: case for case in self.cases}
        for row in self.rows:
            case = by_id[row["_meta"]["case_id"]]
            self.assertEqual(row["state"], render_state(case, row["_meta"]["variant"]))
            for version in case["versions"].values():
                self.assertIn(version["code"], row["state"])
                for field in version["fields"]:
                    self.assertIn(field, row["state"])
        views = defaultdict(set)
        for row in self.rows:
            views[row["_meta"]["case_id"]].add(row["state"])
        self.assertTrue(all(len(value) == 4 for value in views.values()))

    def test_no_merge_group_or_exact_state_leaks(self):
        groups, states = defaultdict(set), defaultdict(set)
        for row in self.rows:
            groups[row["_meta"]["group_id"]].add(row["_meta"]["split"])
            states[row["state"]].add(row["_meta"]["split"])
        self.assertTrue(all(len(value) == 1 for value in groups.values()))
        self.assertTrue(all(len(value) == 1 for value in states.values()))
        self.assertEqual(split_groups(self.cases), {r["_meta"]["case_id"]: r["_meta"]["split"] for r in self.rows})

    def test_test_and_validation_have_one_view_per_case(self):
        for split, expected in (("train", 228), ("validation", 16), ("test", 17)):
            rows = [json.loads(line) for line in (DATA / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), expected)
            self.assertEqual({r["_meta"]["label"] for r in rows}, {"Yes", "No"})
            if split != "train":
                self.assertEqual({r["_meta"]["variant"] for r in rows}, {0})

    def test_provenance_has_no_local_paths_or_synthetic_sources(self):
        catalog = {r["id"]: r for r in read_catalog()}
        for row in self.rows:
            meta = row["_meta"]
            self.assertIn(meta["case_id"], catalog)
            self.assertEqual(meta["label"], catalog[meta["case_id"]]["Locally Observable Interference"])
            self.assertEqual(set(meta["source_files"]), {"base", "left", "right", "merge"})
            for branch, name in meta["source_files"].items():
                self.assertNotIn(":", name)
                self.assertNotIn("dataset-sintetico", name)
                self.assertEqual(len(meta["source_sha256"][branch]), 64)

    def test_source_hashes_if_download_cache_exists(self):
        cache = ROOT / ".laya_smat/mergedataset_sources"
        if not cache.exists():
            self.skipTest("Optional downloaded source cache is not present")
        for row in self.rows[::4]:
            for branch, name in row["_meta"]["source_files"].items():
                self.assertEqual(hashlib.sha256((cache / name).read_bytes()).hexdigest(),
                                 row["_meta"]["source_sha256"][branch])

    def test_overloads_are_not_selected_arbitrarily(self):
        case = next(c for c in self.cases if c["csv_line"] == 25)
        self.assertEqual(case["versions"]["base"]["scope"], "overload_set")
        self.assertIn("coalesce(T value", case["versions"]["base"]["code"])
        self.assertIn("coalesce(Field<T> field", case["versions"]["base"]["code"])

    def test_annotations_require_evidence_and_valid_labels(self):
        row = json.loads(json.dumps(self.rows[0]))
        identity = row["_meta"]["case_id"]
        qid = "criterion_1_global_divergence"
        with self.assertRaises(ValueError):
            refresh_gold([row], {identity: {"answers": {qid: True}}}, self.questions)
        refresh_gold([row], {identity: {"answers": {qid: True}, "evidence": "Reviewed test trace"}}, self.questions)
        self.assertEqual(row["gold"][qid]["probabilities"], {"false": 0., "true": 1.})
        with self.assertRaises(ValueError):
            refresh_gold([row], {identity: {"answers": {"primary_criterion": "invented"}, "evidence": "trace"}}, self.questions)

    def test_context_audit_excludes_whole_case(self):
        class Tokenizer:
            def encode(self, state, add_special_tokens=False):
                return list(range(len(state)))
        rows = [{"state": "x"*size, "_meta": {"id": identity, "case_id": case}}
                for size, identity, case in ((20, "a0", "a"), (200, "a1", "a"), (10, "b0", "b"))]
        kept, audit = audit_rows(rows, Tokenizer(), 150, 20)
        self.assertEqual([r["_meta"]["id"] for r in kept], ["b0"])
        self.assertEqual(audit["rejected_case_ids"], ["a"])

    def test_notebook_code_syntax_and_clean_outputs(self):
        notebook = json.loads((ROOT / "notebooks/laya_semantic_interference_colab.ipynb").read_text(encoding="utf-8"))
        self.assertEqual(notebook["nbformat"], 4)
        for i, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), f"cell_{i}", "exec")
                self.assertEqual(cell["outputs"], [])
                self.assertIsNone(cell["execution_count"])

    def test_portable_zip_is_complete_and_contains_identical_data(self):
        with zipfile.ZipFile(ROOT / "notebooks/laya_mergedataset_full_colab.zip") as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn("train_laya_colab.py", archive.namelist())
            self.assertIn("criteria_snapshot.py", archive.namelist())
            self.assertIn("data/SOURCE_NOTICES.txt", archive.namelist())
            for name in ("all.jsonl", "train.jsonl", "validation.jsonl", "test.jsonl", "annotations.json"):
                self.assertEqual(archive.read("data/" + name), (DATA / name).read_bytes())

    def test_kaggle_notebook_has_no_colab_runtime_dependencies(self):
        path = ROOT / "notebooks/laya_semantic_interference_kaggle.ipynb"
        notebook = json.loads(path.read_text(encoding="utf-8"))
        source = "\n".join("".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code")
        self.assertNotIn("google.colab", source)
        self.assertNotIn("/content/", source)
        self.assertNotIn("files.download", source)
        self.assertIn("/kaggle/input", source)
        self.assertIn("/kaggle/working/laya_smat_checkpoint.zip", source)
        for i, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), f"kaggle_cell_{i}", "exec")
                self.assertEqual(cell["outputs"], [])

    def test_kaggle_input_loader_accepts_zip_and_expanded_dataset(self):
        package = ROOT / "notebooks/laya_mergedataset_full_colab.zip"
        for expanded in (False, True):
            with self.subTest(expanded=expanded), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                inputs, work = base / "input", base / "working"
                dataset = inputs / "my-private-dataset"
                dataset.mkdir(parents=True)
                if expanded:
                    with zipfile.ZipFile(package) as archive:
                        archive.extractall(dataset)
                else:
                    import shutil
                    shutil.copy2(package, dataset / package.name)
                source = KAGGLE_INPUT_CELL.replace("Path('/kaggle/input')", f"Path({str(inputs)!r})")
                source = source.replace("Path('/kaggle/working/laya_smat')", f"Path({str(work)!r})")
                import contextlib
                import io
                with contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(source, "kaggle_input_loader", "exec"), {})
                self.assertEqual((work / "data/train.jsonl").read_bytes(), (DATA / "train.jsonl").read_bytes())
                self.assertEqual((work / "train_laya_colab.py").read_bytes(), (ROOT / "scripts/train_laya_colab.py").read_bytes())

    def test_evaluation_cells_follow_pinned_laya_api(self):
        # Contract verified against laya/agent.py at the notebook's pinned
        # revision: Agent.__init__ has no max_len; predict/system_one does.
        import contextlib
        import io
        calls = []
        class Agent:
            def __init__(self, model_id_or_path, device=None):
                calls.append(("load", model_id_or_path, device))
            def predict(self, state, questions, *, max_len=None, head_max_len=None):
                self_outer.assertEqual((max_len, head_max_len), (8192, 512))
                calls.append(("predict", state, tuple(questions)))
                return {"answers": {q: {"noul": .8 if state == "positive" else .2}
                                    for q in questions}, "usage": {"truncated": 0}}
        self_outer = self
        fake_laya = types.ModuleType("laya")
        fake_laya.Agent = Agent
        torch = types.SimpleNamespace(cuda=types.SimpleNamespace(empty_cache=lambda: None))
        rows = [{"state": state, "_meta": {"case_id": state, "label": label}}
                for state, label in (("positive", "Yes"), ("negative", "No"))]
        for platform in ("colab", "kaggle"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as tmp:
                notebook = json.loads((ROOT / f"notebooks/laya_semantic_interference_{platform}.ipynb").read_text(encoding="utf-8"))
                code = ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]
                evaluation = next(s for s in code if "def evaluate_predictions(" in s)
                inference = next(s for s in code if "usable = [r for r in splits['test']" in s)
                scope = {"BASE_MODEL": "base-model", "OUTPUT": Path(tmp), "MAX_LEN": 8192,
                         "HEAD_MAX_LEN": 512, "questions": self.questions,
                         "project_questions": {q:v for q,v in self.questions.items() if q != "semantic_interference"},
                         "splits": {s: rows for s in ("validation", "test")},
                         "audit": {s: {"rejected_case_ids": []} for s in ("validation", "test")},
                         "torch": torch, "json": json}
                with patch.dict("sys.modules", {"laya": fake_laya}), contextlib.redirect_stdout(io.StringIO()):
                    exec(compile(evaluation, f"{platform}_evaluation", "exec"), scope)
                    exec(compile(inference, f"{platform}_inference", "exec"), scope)
                report = json.loads((Path(tmp) / "scenario_evaluation.json").read_text())
                self.assertEqual(report["finetuned_test_0.5"]["f1"], 1.)
                self.assertEqual(report["finetuned_test_0.5"]["n"], 2)
        self.assertEqual(sum(call[0] == "load" for call in calls), 6)


if __name__ == "__main__":
    unittest.main()
