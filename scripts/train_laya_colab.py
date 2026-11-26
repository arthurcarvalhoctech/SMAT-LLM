"""Single-GPU RLCD using the official Laya notebook's canonical primitives.

Train/calibration/test are separated by real merge before augmentation. Only
genuine gold entries are trained. Missing criterion targets are never filled.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import random


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def audit_rows(rows, tokenizer, max_len, head_max_len):
    """Conservative full-state budget; omit a complete case, never crop it."""
    rejected, lengths = set(), {}
    for row in rows:
        size = len(tokenizer.encode(row["state"], add_special_tokens=False))
        lengths[row["_meta"]["id"]] = size
        if size + head_max_len + 32 > max_len:
            rejected.add(row["_meta"]["case_id"])
    return [r for r in rows if r["_meta"]["case_id"] not in rejected], {
        "input_rows": len(rows), "kept_rows": sum(r["_meta"]["case_id"] not in rejected for r in rows),
        "rejected_case_ids": sorted(rejected), "state_token_lengths": lengths,
        "reason": "Full state plus head reserve does not fit; whole case excluded. No silent truncation."}


def refresh_gold(rows, annotations, questions):
    """Optional reviewed labels, encoded in the notebook's probabilities schema."""
    for row in rows:
        annotation = annotations.get(row["_meta"]["case_id"], {})
        answers = annotation.get("answers", {})
        if answers and not annotation.get("evidence"):
            raise ValueError("Each reviewed annotation must include evidence")
        for qid, value in answers.items():
            if qid not in questions or qid == "semantic_interference":
                raise ValueError(f"Unsupported annotation question: {qid}")
            q = questions[qid]
            if q["type"] == "noul":
                if type(value) is not bool:
                    raise ValueError("Noul gold must be a boolean")
                keys, key = ["false", "true"], str(value).lower()
            elif q["type"] == "score":
                if type(value) is not int or not 0 <= value < len(q["criteria"]):
                    raise ValueError("Score gold must be an integer level")
                keys, key = [str(i) for i in range(len(q["criteria"]))], str(value)
            else:
                keys, key = list(q["criteria"]), value
                if key not in keys:
                    raise ValueError(f"Unknown label for {qid}: {key}")
            row["gold"][qid] = {"label": key, "probabilities": {k: float(k == key) for k in keys}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base", default="convaiinnovations/laya-multilingual")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--max-len", type=int, default=8192)
    parser.add_argument("--head-max-len", type=int, default=512)
    parser.add_argument("--micro-batch", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--freeze-encoder", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--require-criterion-gold", action="store_true")
    args = parser.parse_args()
    import numpy as np
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer
    from laya.agent import _fix_tokenizer_config
    from laya.train import (TrainConfig, load_checkpoint, items_from_rows, train_model,
                            calibration_records, save_checkpoint, evaluate_records,
                            calibration_report, optimizer_updates)
    from laya.calibrate import fit_temperature_map
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    questions = json.loads((args.data_dir / "questions.json").read_text(encoding="utf-8"))
    annotations = json.loads((args.data_dir / "annotations.json").read_text(encoding="utf-8"))
    splits = {s: read_rows(args.data_dir / f"{s}.jsonl") for s in ("train", "validation", "test")}
    groups = {s: {r["_meta"]["group_id"] for r in rows} for s, rows in splits.items()}
    assert not (groups["train"] & groups["test"] or groups["train"] & groups["validation"] or groups["validation"] & groups["test"])
    for rows in splits.values():
        refresh_gold(rows, annotations, questions)
    supervised = dict(Counter(q for row in splits["train"] for q in row["gold"]))
    criterion_ids = [q for q in questions if q.startswith("criterion_")]
    if args.require_criterion_gold:
        for qid in criterion_ids:
            values = {r["gold"][qid]["label"] for r in splits["train"] if qid in r["gold"]}
            if values != {"false", "true"}:
                raise ValueError(f"{qid} needs reviewed positive AND negative targets in train")
    model_dir = Path(args.base) if Path(args.base).is_dir() else Path(snapshot_download(args.base))
    _fix_tokenizer_config(str(model_dir))
    tok = AutoTokenizer.from_pretrained(model_dir / "tokenizer")
    cfg = json.loads((model_dir / "rl_agent_config.json").read_text())
    encoder_cfg = json.loads((model_dir / "encoder/config.json").read_text())
    capacity = encoder_cfg.get("max_position_embeddings", encoder_cfg.get("max_seq_len"))
    if capacity and args.max_len > capacity:
        raise ValueError(f"Requested context {args.max_len} exceeds encoder capacity {capacity}")
    audit = {}
    for name, rows in splits.items():
        splits[name], audit[name] = audit_rows(rows, tok, args.max_len, args.head_max_len)
    items = {}
    preprocessing_errors = []
    for name, rows in splits.items():
        items[name], skipped = items_from_rows(tok, rows, args.max_len, args.head_max_len)
        audit[name]["canonical_skipped"] = skipped
        audit[name]["decisions"] = len(items[name])
        audit[name]["labels"] = dict(Counter(r["_meta"]["label"] for r in rows))
        if skipped:
            preprocessing_errors.append(f"Unexpected canonical preprocessing skips in {name}: {skipped}")
        if not items[name] or set(audit[name]["labels"]) != {"Yes", "No"}:
            preprocessing_errors.append(f"{name} needs both scenario classes after the context audit")
    (args.out / "context_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps({"supervised": supervised, "audit": {s: {k:v for k,v in a.items() if k != "state_token_lengths"} for s,a in audit.items()}}, indent=2), flush=True)
    if preprocessing_errors:
        raise ValueError("; ".join(preprocessing_errors))
    if args.audit_only:
        return
    if not torch.cuda.is_available():
        raise RuntimeError("Enable a GPU runtime in Colab before training")
    device = torch.device("cuda")
    model, tok, cfg = load_checkpoint(str(model_dir))
    model.to(device)
    cfg = dict(cfg, max_len=args.max_len, head_max_len=args.head_max_len,
               gradient_checkpointing=True, max_tokens_per_batch=args.max_len)
    config = TrainConfig(epochs=args.epochs, micro_batch=args.micro_batch, grad_accum=args.grad_accum,
                         encoder_lr=1e-5, head_lr=1e-4, loss="rlcd", max_len=args.max_len,
                         head_max_len=args.head_max_len, amp=True, gradient_checkpointing=True,
                         freeze_encoder=args.freeze_encoder, seed=args.seed, log_every=10,
                         calib_frac=0, calib_max=0)
    def records(name):
        return calibration_records(model, tok, items[name], device, args.max_len,
                                   args.head_max_len, batch_size=1)
    before = evaluate_records(records("test"), cfg.get("temperature"), cfg.get("temperature_by_options"))
    print("Optimizer updates:", optimizer_updates(len(items["train"]), args.micro_batch, args.grad_accum, args.epochs), flush=True)
    def checkpoint(epoch, loss):
        save_checkpoint(model, tok, cfg, str(args.out / "checkpoint_latest"))
        print(f"Epoch {epoch}: loss={loss:.6f}; rolling checkpoint saved", flush=True)
    history = train_model(model, tok, items["train"], config, device, args.max_len,
                          args.head_max_len, on_epoch_end=checkpoint)
    calibration = records("validation")
    fitted = fit_temperature_map(calibration)
    cfg["temperature"] = fitted["temperature"]
    cfg.pop("temperature_by_options", None)
    if fitted.get("temperature_by_options"):
        cfg["temperature_by_options"] = fitted["temperature_by_options"]
    cfg["fine_tuned"] = True
    cfg["training"] = {"source": "mergedataset-full", "supervised_questions": supervised,
                       "unlabeled_questions": sorted(set(questions) - set(supervised)),
                       "seed": args.seed, "epochs": args.epochs, "loss": "rlcd",
                       "note": "Scenario-only supervision does not train criterion identities. Calibration also changes shared question-type temperatures."}
    save_checkpoint(model, tok, cfg, str(args.out))
    for name in ("questions.json", "project_questions.json", "manifest.json"):
        (args.out / name).write_bytes((args.data_dir / name).read_bytes())
    after = evaluate_records(records("test"), cfg["temperature"], cfg.get("temperature_by_options"))
    report = {"before": before, "after": after, "history": history,
              "calibration": calibration_report(calibration, cfg["temperature"]),
              "supervised_questions": supervised, "base_snapshot": str(model_dir),
              "test_is_held_out": True, "test_unit": "original real case, one view",
              "criterion_metrics": "Unavailable unless reviewed criterion gold was supplied."}
    (args.out / "training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
