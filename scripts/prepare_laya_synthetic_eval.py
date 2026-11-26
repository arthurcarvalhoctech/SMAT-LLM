"""Prepare an external synthetic test for the trained scenario-level question."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_laya_colab import BRANCHES, GLOBAL_ID, render_state


def prepare():
    dataset = ROOT / "dataset-sintetico"
    gold = json.loads((dataset / "gold-sintetico.json").read_text(encoding="utf-8"))
    question = json.loads((ROOT / "laya_training_data/mergedataset_full_colab/questions.json").read_text(encoding="utf-8"))[GLOBAL_ID]
    rows = []
    for case in gold:
        folder = dataset / "cases" / case["commit"] / "source" / case["class"].rsplit(".", 1)[1]
        paths = {branch: folder / f"{branch}.java" for branch in BRANCHES}
        # Full classes are small here and retain helper methods and initial
        # fields needed to interpret cleanText(), unlike a method-only excerpt.
        versions = {branch: {"code": path.read_text(encoding="utf-8"), "fields": []}
                    for branch, path in paths.items()}
        state = render_state({"class": case["class"], "declaration": case["method"], "versions": versions}, 0)
        label = case["label"]
        if label not in ("Yes", "No"):
            raise ValueError(f"Unknown label in synthetic gold: {label}")
        rows.append({"state": state, "questions": {GLOBAL_ID: question},
                     "gold": {GLOBAL_ID: {"label": str(label == "Yes").lower(),
                                           "probabilities": {"false": float(label == "No"), "true": float(label == "Yes")}}},
                     "_meta": {"id": case["commit"], "label": label, "class": case["class"],
                               "method": case["method"], "gold_criteria": case["criteria"],
                               "state_format": "training_headings_full_small_classes_BLRM",
                               "source_sha256": {b: hashlib.sha256(p.read_bytes()).hexdigest() for b,p in paths.items()}}})
    target = dataset / "laya_global_eval.jsonl"
    target.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"Prepared {len(rows)} external synthetic test cases: {target}")
    return target


if __name__ == "__main__":
    prepare()
