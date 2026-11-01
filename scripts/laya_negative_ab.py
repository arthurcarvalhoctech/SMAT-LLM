#!/usr/bin/env python3
"""A/B the criterion instructions on a fine-tuned Laya checkpoint.

Runs the same labeled synthetic cases with and without the negative
instructions (C1/C2/C3), using the fine-tuned checkpoint already trained for
the SMAT flow. It does not use an LLM and does not use roles.

    HF_HOME=/home/arthur/.cache/huggingface HF_HUB_OFFLINE=1 \
      PYTHONPATH=SMAT /tmp/laya-live-venv/bin/python scripts/laya_negative_ab.py \
      --out docs/laya-negative-ab.json
"""

import argparse
import importlib.util
import json
import os
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("HF_HOME", "/home/arthur/.cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "dataset-sintetico/resultados/probe_t1.json"
CHECKPOINT = ROOT / "laya_checkpoints/laya_finetuned_smat_multilingual"

_criteria_path = ROOT / "SMAT/nimrod/laya_interference/criteria.py"
_spec = importlib.util.spec_from_file_location("_smat_laya_criteria", _criteria_path)
if _spec is None or _spec.loader is None:
    raise SystemExit(f"Could not load {_criteria_path}")
_criteria = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_criteria)
CRITERIA = _criteria.CRITERIA
build_questions = _criteria.build_questions


def criterion_questions(negative_instructions):
    all_questions = build_questions(
        negative_instructions=negative_instructions
    )
    return {criterion.id: all_questions[criterion.id] for criterion in CRITERIA}


def probabilities(answer):
    return {
        criterion.id: float(answer[criterion.id]["noul"])
        for criterion in CRITERIA
    }


def metrics(rows, prediction_key, thresholds):
    counts = {
        criterion.id: {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
        for criterion in CRITERIA
    }
    final = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for row, expected in rows:
        labels = {
            criterion.id: (
                f"C{criterion.number}" in (row.get("criteria") or [])
            )
            for criterion in CRITERIA
        }
        predicted = {
            criterion.id: (
                expected[criterion.id] >= thresholds[criterion.id]
            )
            for criterion in CRITERIA
        }
        for criterion in CRITERIA:
            key = "tp" if predicted[criterion.id] and labels[criterion.id] else (
                "fp" if predicted[criterion.id] else (
                    "fn" if labels[criterion.id] else "tn"
                )
            )
            counts[criterion.id][key] += 1
        gold_any = row.get("label") == "Yes"
        pred_any = any(predicted.values())
        key = "tp" if pred_any and gold_any else (
            "fp" if pred_any else ("fn" if gold_any else "tn")
        )
        final[key] += 1

    def summarize(values):
        precision = values["tp"] / (values["tp"] + values["fp"]) if values["tp"] + values["fp"] else 0.0
        recall = values["tp"] / (values["tp"] + values["fn"]) if values["tp"] + values["fn"] else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {
            **values,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    return {
        "per_criterion": {
            criterion.id: summarize(counts[criterion.id])
            for criterion in CRITERIA
        },
        "final": summarize(final),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default=str(CHECKPOINT))
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-len", type=int, default=4000)
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--thresholds",
        default="0.8,0.81,0.84",
        help="C1,C2,C3 thresholds",
    )
    args = parser.parse_args()

    checkpoint = Path(args.checkpoint)
    if not checkpoint.is_dir():
        raise SystemExit(f"Checkpoint not found: {checkpoint}")
    thresholds_values = [float(value) for value in args.thresholds.split(",")]
    if len(thresholds_values) != 3:
        raise SystemExit("--thresholds must contain three values")
    thresholds = {
        criterion.id: thresholds_values[index]
        for index, criterion in enumerate(CRITERIA)
    }

    cases = [
        case
        for case in json.loads(PROBE.read_text(encoding="utf-8"))
        if case.get("set") == "sintetico"
        and case.get("label") in ("Yes", "No")
        and case.get("state_v1")
    ]
    if not cases:
        raise SystemExit("No labeled synthetic cases found.")

    from laya import load

    agent = load(str(checkpoint), device=args.device)
    results = {"old": [], "new": []}
    for case in cases:
        state = case["state_v1"]
        for variant, negative in (("old", False), ("new", True)):
            questions = criterion_questions(negative)
            response = agent.predict(state, questions, max_len=args.max_len)
            result = probabilities(response["answers"])
            results[variant].append(
                {
                    "id": case["id"],
                    "label": case["label"],
                    "criteria": case.get("criteria") or [],
                    "probabilities": result,
                }
            )
        print(case["id"], case["label"], flush=True)

    old_rows = [(cases[index], result["probabilities"]) for index, result in enumerate(results["old"])]
    new_rows = [(cases[index], result["probabilities"]) for index, result in enumerate(results["new"])]
    report = {
        "checkpoint": str(checkpoint),
        "max_len": args.max_len,
        "thresholds": thresholds,
        "negative_instructions": {
            criterion.id: criterion.negative_instruction
            for criterion in CRITERIA
        },
        "old": metrics(old_rows, "old", thresholds),
        "new": metrics(new_rows, "new", thresholds),
        "results": results,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["old"], indent=2, ensure_ascii=False))
    print(json.dumps(report["new"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
