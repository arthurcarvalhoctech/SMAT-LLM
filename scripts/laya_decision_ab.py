#!/usr/bin/env python3
"""A/B the Laya decision rules on the fine-tuned checkpoint.

Runs the witness two-stage flow and applies baseline/consistent/conservative to
the same raw model outputs, so the comparison isolates the decision policy.
No role prompt and no LLM are used.
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path

os.environ.setdefault("HF_HOME", "/home/arthur/.cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "dataset-sintetico/resultados/probe_t1.json"
CHECKPOINT = ROOT / "laya_checkpoints/laya_finetuned_smat_multilingual"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_criteria = load_module(
    "_smat_laya_criteria",
    ROOT / "SMAT/nimrod/laya_interference/criteria.py",
)
_decision = load_module(
    "_smat_laya_decision",
    ROOT / "SMAT/nimrod/laya_interference/decision.py",
)
CRITERIA = _criteria.CRITERIA
build_questions = _criteria.build_questions
WITNESS_ID = _criteria.WITNESS_QUESTION_ID
WITNESS_CANDIDATES = _criteria.WITNESS_CANDIDATE_DESCRIPTIONS
decide = _decision.decide


def metrics(rows, rule):
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    uncertain = 0
    no_signal = 0
    for row in rows:
        gold_yes = row["label"] == "Yes"
        classification = row["classification"]
        if classification == "uncertain":
            uncertain += 1
        if classification == "no_signal":
            no_signal += 1
        predicted = classification == "possible_interference"
        if predicted and gold_yes:
            counts["tp"] += 1
        elif predicted:
            counts["fp"] += 1
        elif gold_yes:
            counts["fn"] += 1
        else:
            counts["tn"] += 1
    precision = counts["tp"] / (counts["tp"] + counts["fp"]) if counts["tp"] + counts["fp"] else 0.0
    recall = counts["tp"] / (counts["tp"] + counts["fn"]) if counts["tp"] + counts["fn"] else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        **counts,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "uncertain": uncertain,
        "no_signal": no_signal,
        "coverage": round((len(rows) - uncertain) / len(rows), 4),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default=str(CHECKPOINT))
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-len", type=int, default=4000)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--thresholds", default="0.8,0.81,0.84")
    parser.add_argument("--none-threshold", type=float, default=0.9)
    args = parser.parse_args()

    checkpoint = Path(args.checkpoint)
    if not checkpoint.is_dir():
        raise SystemExit(f"Checkpoint not found: {checkpoint}")
    values = [float(value) for value in args.thresholds.split(",")]
    if len(values) != 3:
        raise SystemExit("--thresholds must contain three values")
    thresholds = {
        criterion.id: values[index]
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
    witness_questions = build_questions(
        WITNESS_CANDIDATES, include_criteria=False
    )
    criteria_questions = build_questions()

    rows = []
    for case in cases:
        state = case["state_v1"]
        witness_result = agent.predict(
            state, witness_questions, max_len=args.max_len
        )
        witness = (
            witness_result.get("answers", {})
            .get(WITNESS_ID, {})
            .get("choice")
        )
        if witness in (None, "none"):
            probabilities = {criterion.id: None for criterion in CRITERIA}
            primary = None
            none_probability = None
            witness = "none"
        else:
            focused = state + "\nTestemunha: " + str(witness)
            response = agent.predict(
                focused, criteria_questions, max_len=args.max_len
            )
            answers = response.get("answers", {})
            probabilities = {
                criterion.id: float(answers[criterion.id]["noul"])
                for criterion in CRITERIA
            }
            primary_answer = answers.get("primary_criterion", {})
            primary = primary_answer.get("choice")
            none_probability = (
                primary_answer.get("probabilities", {}).get("none")
            )
            if none_probability is not None:
                none_probability = float(none_probability)

        decisions = {}
        for rule in ("baseline", "consistent", "conservative"):
            classification, reason = decide(
                rule,
                probabilities,
                thresholds,
                primary,
                none_probability,
                none_threshold=args.none_threshold,
                witness=witness,
            )
            decisions[rule] = {
                "classification": classification,
                "reason": reason,
            }
        rows.append(
            {
                "id": case["id"],
                "label": case["label"],
                "witness": witness,
                "primary": primary,
                "none_probability": none_probability,
                "probabilities": probabilities,
                "decisions": decisions,
            }
        )
        print(case["id"], case["label"], witness, flush=True)

    report = {
        "checkpoint": str(checkpoint),
        "max_len": args.max_len,
        "thresholds": thresholds,
        "none_threshold": args.none_threshold,
        "rules": {
            rule: metrics(
                [
                    {
                        "label": row["label"],
                        "classification": row["decisions"][rule]["classification"],
                    }
                    for row in rows
                ],
                rule,
            )
            for rule in ("baseline", "consistent", "conservative")
        },
        "results": rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["rules"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
