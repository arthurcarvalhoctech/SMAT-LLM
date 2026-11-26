"""Evaluate every original real case, keeping training exposure visible.

No augmentation, training, threshold search or silent truncation. Pooled
metrics include training cases and are diagnostic; only the original test
partition is held out from fitting the weights and calibration.
"""
import argparse
from collections import Counter
import importlib.metadata
import json
import os
from pathlib import Path

try:
    from scripts.evaluate_laya_synthetic import binary_metrics, load_inputs, roc_curve, run_evaluation, sha256_file, write_outputs
except ModuleNotFoundError:
    from evaluate_laya_synthetic import binary_metrics, load_inputs, roc_curve, run_evaluation, sha256_file, write_outputs

ROOT = Path(__file__).resolve().parents[1]
SPLITS = ("train", "validation", "test")


def prepare_rows(data_dir, model, threshold=None):
    rows, questions, cfg, threshold, threshold_source = load_inputs(model, data_dir / "all.jsonl", threshold)
    cases = {c["id"]: c for c in json.loads((data_dir / "cases.json").read_text(encoding="utf-8"))}
    previous_audit = json.loads((model / "context_audit.json").read_text(encoding="utf-8"))
    originals = []
    for row in rows:
        meta = row["_meta"]
        if meta["variant"] != 0:
            continue
        case_id, split = meta["case_id"], meta["split"]
        if split not in SPLITS:
            raise ValueError(f"Unknown original split {split}")
        case = cases[case_id]
        excluded_before = case_id in previous_audit[split]["rejected_case_ids"]
        exposure = "not_used_due_to_context" if excluded_before else {
            "train": "trained", "validation": "calibration", "test": "held_out_test"}[split]
        originals.append({**row, "_meta": {**meta, "id": case_id, "class": case["class"],
                                           "method": case["declaration"], "exposure": exposure}})
    if len(originals) != len(cases) or len({r["_meta"]["id"] for r in originals}) != len(cases):
        raise ValueError("Need exactly one original view per real case")
    # A changed source revision would invalidate the claimed training exposure.
    trained_manifest = json.loads((model / "manifest.json").read_text(encoding="utf-8"))
    if any(r["_meta"]["source_revision"] != trained_manifest["source_revision"] for r in originals):
        raise ValueError("Source revision differs from the checkpoint training manifest")
    return originals, questions, cfg, threshold, threshold_source


def evaluate_originals(agent, rows, questions, max_len, head_max_len):
    ready, excluded, source_tokens = [], [], {}
    for row in rows:
        tokens = len(agent.tok.encode(row["state"], add_special_tokens=False))
        meta = row["_meta"]
        source_tokens[meta["id"]] = tokens
        if tokens + head_max_len + 32 <= max_len:
            ready.append(row)
        else:
            excluded.append({"id": meta["id"], "class": meta["class"], "method": meta["method"],
                             "gold": meta["label"] == "Yes", "probability": None,
                             "status": "context_excluded", "latency_ms": None,
                             "reason": "The entire B/L/R/M state and question reserve do not fit; no inference or truncation performed."})
            print(f"[context] excluded {meta['id']}: {tokens} state tokens", flush=True)
    actual = run_evaluation(agent, ready, questions, max_len, head_max_len)
    by_id = {r["id"]: r for r in [*actual, *excluded]}
    result = []
    for row in rows:
        meta = row["_meta"]
        result.append({**by_id[meta["id"]], "split": meta["split"],
                       "exposure": meta["exposure"], "source_tokens": source_tokens[meta["id"]]})
    return result


def partition_results(predictions, threshold):
    descriptions = {"train": "Training cases; these metrics do not measure generalization.",
                    "validation": "Used for temperature fitting and threshold choice; not an independent test.",
                    "test": "Original reserved test partition; context exclusions are included in coverage."}
    result = {}
    for split in SPLITS:
        selected = [p for p in predictions if p["split"] == split]
        result[split] = {"input_cases": len(selected), "input_labels": {
            "Yes": sum(p["gold"] for p in selected), "No": sum(not p["gold"] for p in selected)},
            "metrics": binary_metrics(selected, threshold), "roc": roc_curve(selected),
            "excluded_case_ids": [p["id"] for p in selected if p["status"] != "ok"],
            "interpretation": descriptions[split]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=ROOT / "laya_checkpoints/laya_semantic_global")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "laya_training_data/mergedataset_full_colab")
    parser.add_argument("--out", type=Path, default=ROOT / "mergedataset-full/resultados/laya_semantic_global_eval.json")
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cpu")
    parser.add_argument("--max-len", type=int, help="Override the inference context for a controlled comparison")
    parser.add_argument("--threshold", type=float, help="Fixed threshold; never fitted on this evaluation dataset")
    parser.add_argument("--profile-note", default="Checkpoint configuration; production .env is not loaded")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    rows, questions, cfg, threshold, threshold_source = prepare_rows(args.data_dir, args.model, args.threshold)
    max_len = args.max_len if args.max_len is not None else int(cfg["max_len"])
    encoder_cfg = json.loads((args.model / "encoder/config.json").read_text(encoding="utf-8"))
    capacity = encoder_cfg.get("max_position_embeddings")
    if max_len <= int(cfg["head_max_len"]) + 32 or (capacity and max_len > capacity):
        raise ValueError("Inference context is outside the usable encoder budget")
    summary = {"cases": len(rows), "labels": dict(Counter(r["_meta"]["label"] for r in rows)),
               "original_partitions": dict(Counter(r["_meta"]["split"] for r in rows)),
               "training_exposure": dict(Counter(r["_meta"]["exposure"] for r in rows)),
               "threshold": threshold, "threshold_source": threshold_source,
               "max_len": max_len, "head_max_len": cfg["head_max_len"],
               "checkpoint_max_len": cfg["max_len"], "profile_note": args.profile_note,
               "question": "semantic_interference", "views_per_case": 1}
    print(json.dumps(summary, indent=2), flush=True)
    if args.dry_run:
        return
    import laya
    import torch
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    agent = laya.Agent(str(args.model), device=None if args.device == "auto" else args.device)
    predictions = evaluate_originals(agent, rows, questions, max_len, int(cfg["head_max_len"]))
    for prediction in predictions:
        prediction["prediction"] = prediction["probability"] >= threshold if prediction["status"] == "ok" else None
    report = {**summary, "metrics": binary_metrics(predictions, threshold), "roc": roc_curve(predictions),
              "partitions": partition_results(predictions, threshold), "predictions": predictions,
              "data_sha256": sha256_file(args.data_dir / "all.jsonl"),
              "model_sha256": sha256_file(args.model / "model.safetensors"),
              "environment": {p: importlib.metadata.version(p) for p in ("laya", "torch", "transformers")},
              "catalog": json.loads((args.data_dir / "manifest.json").read_text(encoding="utf-8")),
              "note": "Pooled metrics include training cases and must not be presented as held-out performance. Only the test partition was reserved from gradient training and calibration. One unaugmented view per real case. Context exclusions remain visible in coverage. No training, calibration, threshold fitting or synthetic cases in this run. Only semantic_interference was supervised."}
    write_outputs(args.out, report, extra_fields=("split", "exposure", "source_tokens"))
    for split, partition in report["partitions"].items():
        points_path = args.out.with_name(args.out.stem + f"_{split}_roc.csv")
        import csv
        with points_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["threshold", "fpr", "tpr"])
            writer.writeheader()
            writer.writerows(partition["roc"]["points"])
    print(json.dumps({"diagnostic_pooled_metrics": report["metrics"],
                      "partitions": {s: {"metrics": p["metrics"], "roc_auc": p["roc"]["auc"]} for s,p in report["partitions"].items()},
                      "report": str(args.out)}, indent=2), flush=True)
    if any(p["status"] == "truncated" for p in predictions):
        raise SystemExit("Unexpected inference truncation; see predictions and coverage")


if __name__ == "__main__":
    main()
