"""Evaluate a trained Laya checkpoint on the external 20-case synthetic set.

Inference only; no training or threshold fitting. Runtime needs laya/torch,
while --dry-run and metric calculations only need Python's standard library.
"""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import time

os.environ.setdefault("USE_TF", "0")
GLOBAL_ID = "semantic_interference"
ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def binary_metrics(rows, threshold):
    evaluated = [r for r in rows if r.get("status") == "ok"]
    tp = sum(r["gold"] and r["probability"] >= threshold for r in evaluated)
    fp = sum(not r["gold"] and r["probability"] >= threshold for r in evaluated)
    fn = sum(r["gold"] and r["probability"] < threshold for r in evaluated)
    tn = len(evaluated) - tp - fp - fn
    precision = tp / (tp+fp) if tp+fp else 0.
    recall = tp / (tp+fn) if tp+fn else 0.
    return {"n": len(evaluated), "coverage": len(evaluated)/len(rows) if rows else 0.,
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": precision, "recall": recall,
            "f1": 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.,
            "accuracy": (tp+tn)/len(evaluated) if evaluated else None,
            "brier": sum((r["probability"]-r["gold"])**2 for r in evaluated)/len(evaluated) if evaluated else None}


def roc_curve(rows):
    """Exact ROC with tied scores grouped; trapezoidal AUC, no fitted cutoff."""
    rows = [r for r in rows if r.get("status") == "ok"]
    positives = sum(r["gold"] for r in rows)
    negatives = len(rows) - positives
    if not positives or not negatives:
        return {"auc": None, "points": [], "reason": "Both classes are required"}
    buckets = {}
    for row in rows:
        bucket = buckets.setdefault(row["probability"], [0, 0])
        bucket[0 if row["gold"] else 1] += 1
    points = [{"threshold": None, "fpr": 0., "tpr": 0.}]
    tp = fp = 0
    for threshold in sorted(buckets, reverse=True):
        positive, negative = buckets[threshold]
        tp += positive
        fp += negative
        points.append({"threshold": threshold, "fpr": fp/negatives, "tpr": tp/positives})
    auc = sum((b["fpr"]-a["fpr"])*(a["tpr"]+b["tpr"])/2 for a,b in zip(points, points[1:]))
    return {"auc": auc, "points": points, "positives": positives, "negatives": negatives,
            "threshold_note": "The first point predicts no positives; threshold=null denotes above the highest score."}


def load_inputs(model, data, threshold=None):
    rows = [json.loads(line) for line in data.read_text(encoding="utf-8").splitlines() if line.strip()]
    questions = json.loads((model / "questions.json").read_text(encoding="utf-8"))
    cfg = json.loads((model / "rl_agent_config.json").read_text(encoding="utf-8"))
    if questions.get(GLOBAL_ID, {}).get("type") != "noul":
        raise ValueError("Checkpoint has no trained semantic_interference noul question")
    if len({r["_meta"]["id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate test case IDs")
    for row in rows:
        if row["questions"].get(GLOBAL_ID) != questions[GLOBAL_ID]:
            raise ValueError("Test question differs from the checkpoint's trained question")
        if row["_meta"]["label"] not in ("Yes", "No"):
            raise ValueError("Test case has no yes/no gold")
    threshold_source = "command_line"
    if threshold is None:
        report_path = model / "scenario_evaluation.json"
        threshold = json.loads(report_path.read_text())["validation_selected_threshold"] if report_path.exists() else .5
        threshold_source = "real_dataset_validation" if report_path.exists() else "default_0.5"
    if not 0 <= threshold <= 1:
        raise ValueError("Threshold must be between zero and one")
    return rows, {GLOBAL_ID: questions[GLOBAL_ID]}, cfg, float(threshold), threshold_source


def run_evaluation(agent, rows, questions, max_len, head_max_len):
    predictions = []
    for i, row in enumerate(rows, 1):
        start = time.perf_counter()
        out = agent.predict(row["state"], questions, max_len=max_len, head_max_len=head_max_len)
        usage = out.get("usage", {})
        probability = float(out["answers"][GLOBAL_ID]["noul"])
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("Agent returned an invalid probability")
        prediction = {"id": row["_meta"]["id"], "class": row["_meta"]["class"],
                      "method": row["_meta"]["method"], "gold": row["_meta"]["label"] == "Yes",
                      "probability": probability, "status": "truncated" if usage.get("truncated") else "ok",
                      "usage": usage, "latency_ms": 1000*(time.perf_counter()-start)}
        predictions.append(prediction)
        print(f"[{i:02d}/{len(rows)}] {prediction['id']}: P(Yes)={probability:.4f}; {prediction['status']}", flush=True)
    return predictions


def write_outputs(out, report, extra_fields=()):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    fields = ["id", "class", "method", "gold", "probability", "prediction", "status", "latency_ms", *extra_fields]
    with out.with_suffix(".csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report["predictions"])
    with out.with_name(out.stem + "_roc.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["threshold", "fpr", "tpr"])
        writer.writeheader()
        writer.writerows(report["roc"]["points"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / "laya_checkpoints/laya_semantic_global")
    parser.add_argument("--data", type=Path, default=ROOT / "dataset-sintetico/laya_global_eval.jsonl")
    parser.add_argument("--out", type=Path, default=ROOT / "dataset-sintetico/resultados/laya_semantic_global_eval.json")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="cpu")
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows, questions, cfg, threshold, threshold_source = load_inputs(args.model, args.data, args.threshold)
    summary = {"cases": len(rows), "labels": dict(Counter(r["_meta"]["label"] for r in rows)),
               "model": str(args.model), "question": GLOBAL_ID, "threshold": threshold,
               "threshold_source": threshold_source, "max_len": cfg["max_len"], "head_max_len": cfg["head_max_len"]}
    print(json.dumps(summary, indent=2), flush=True)
    if args.dry_run:
        return
    try:
        import laya
        import torch
    except ImportError as error:
        raise SystemExit("Laya/PyTorch not installed. Use docker compose -f docker-compose.laya-eval.yml run --rm --build laya-eval") from error
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    agent = laya.Agent(str(args.model), device=None if args.device == "auto" else args.device)
    predictions = run_evaluation(agent, rows, questions, int(cfg["max_len"]), int(cfg["head_max_len"]))
    for row in predictions:
        row["prediction"] = row["probability"] >= threshold if row["status"] == "ok" else None
    report = {**summary, "metrics": binary_metrics(predictions, threshold), "roc": roc_curve(predictions),
              "predictions": predictions, "data_sha256": sha256_file(args.data),
              "model_sha256": sha256_file(args.model / "model.safetensors"),
              "environment": {p: importlib.metadata.version(p) for p in ("laya", "torch", "transformers")},
              "note": "External synthetic test only; no training or threshold fitting on these cases. Labels originate from prior Java executions, not from this inference run. Only the scenario-level question was trained. Full small classes preserve helper methods and initial fields; source distribution differs from real training cases."}
    write_outputs(args.out, report)
    print(json.dumps({"metrics": report["metrics"], "roc_auc": report["roc"]["auc"], "report": str(args.out)}, indent=2), flush=True)
    if any(r["status"] != "ok" for r in predictions):
        raise SystemExit("Some cases were truncated and excluded from metrics; inspect coverage and predictions")


if __name__ == "__main__":
    main()
