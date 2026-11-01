#!/usr/bin/env python3
"""Evaluate Laya probe variants against the labeled synthetic/real cases.

This script is intentionally dependency-free: it consumes the probabilities
already stored in ``dataset-sintetico/resultados/probe_t1.json`` and applies
simple decision rules. It does not call the Laya model.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "dataset-sintetico/resultados/probe_t1.json"


def probabilities(case, variant):
    cell = case.get(variant) or {}
    if "T1" in cell:
        return {"T1": float(cell["T1"])}
    return {
        key: float(cell.get(key, 0.0))
        for key in (
            "criterion_1_global_divergence",
            "criterion_2_parent_change_loss",
            "criterion_3_merge_new_effect",
        )
    }


def metrics(rows, predictions):
    tp = fp = tn = fn = 0
    for case, predicted in zip(rows, predictions):
        actual = case.get("label") == "Yes"
        if predicted and actual:
            tp += 1
        elif predicted and not actual:
            fp += 1
        elif not predicted and actual:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def best_threshold(rows, variant):
    values = [probabilities(case, variant) for case in rows]
    best = None
    for step in range(1, 100):
        threshold = step / 100
        prediction = [max(value.values()) >= threshold for value in values]
        score = metrics(rows, prediction)
        if best is None or (score["f1"], score["precision"]) > (
            best["metrics"]["f1"],
            best["metrics"]["precision"],
        ):
            best = {"threshold": threshold, "metrics": score}
    return best


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(DEFAULT_DATA))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    cases = json.loads(Path(args.data).read_text(encoding="utf-8"))
    rows = [case for case in cases if case.get("label") in ("Yes", "No")]
    baseline = metrics(
        rows,
        [max(probabilities(case, "v3/base").values()) >= 0.70 for case in rows],
    )
    report = {
        "labeled_cases": len(rows),
        "yes": sum(case.get("label") == "Yes" for case in rows),
        "no": sum(case.get("label") == "No" for case in rows),
        "baseline_v3_base_0.70": baseline,
        "best_v3_base": best_threshold(rows, "v3/base"),
        "best_v3_ajustado": best_threshold(rows, "v3/ajustado"),
        "best_v3pt_ajustado": best_threshold(rows, "v3pt/ajustado"),
        "note": (
            "Probe probabilities only; no Laya forward pass is performed. "
            "Use this report to compare operating points before live runs."
        ),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
