#!/usr/bin/env python3
"""Evaluate/export Laya with production source extraction and prompts.

No weights are loaded with --export-only. Disputed or unlabelled cases are
excluded. Groups are assigned deterministically before any parameter search.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "SMAT"))

from nimrod.core.merge_scenario_under_analysis import MergeScenarioUnderAnalysis, ScenarioInformation
from nimrod.laya_interference.config import LayaFlowConfig
from nimrod.laya_interference.criteria import CRITERIA, PROMPT_VERSION, QUESTION_FORMATS, build_questions
from nimrod.laya_interference.flow import LayaInterferenceFlow
from nimrod.laya_interference.source_context import build_method_state, parse_method_item


def group_split(group, seed="smat-laya-v2"):
    bucket = int(hashlib.sha256((seed + ":" + group).encode()).hexdigest()[:8], 16) % 100
    return "train" if bucket < 70 else "validation" if bucket < 85 else "test"


def load_cases(input_path, gold_path, mappings=(), dataset_root="", split_by="project", seed="smat-laya-v2"):
    data = json.loads(Path(input_path).read_text(encoding="utf-8-sig"))
    gold_data = json.loads(Path(gold_path).read_text(encoding="utf-8-sig"))
    gold_rows = gold_data if isinstance(gold_data, list) else gold_data["methods"]
    gold = {}
    for row in gold_rows:
        key = (row["project"], row["commit"], row["class"], row["method"])
        if key in gold:
            raise ValueError(f"Duplicate gold key: {key}")
        gold[key] = row

    def resolve(path):
        if "${PATH_DATASET}" in path:
            if not dataset_root:
                raise ValueError("Set --dataset-root or PATH_DATASET")
            path = path.replace("${PATH_DATASET}", dataset_root)
        for old, new in mappings:
            path = path.replace(old, new)
        return path

    cases, excluded, seen = [], [], set()
    for entry in data:
        jars = {key: resolve(entry["scenarioJars"].get(key, "")) for key in ("base", "left", "right", "merge")}
        commits = entry.get("scenarioCommits", {})
        commit = commits.get("merge", "")
        if not commit:
            match = re.search(r"[/\\]([0-9a-f]{40})[/\\]", jars["merge"])
            if not match:
                raise ValueError(f"Cannot identify merge commit for {entry['projectName']}")
            commit = match.group(1)
        for cls, items in entry["targets"].items():
            for item in items if isinstance(items, list) else [items]:
                signature = parse_method_item(item)[0]
                key = (entry["projectName"], commit, cls, signature)
                if key in seen:
                    raise ValueError(f"Duplicate input key: {key}")
                seen.add(key)
                label = gold.get(key)
                if not label or label.get("label") not in {"Yes", "No"} or label.get("disputed"):
                    excluded.append({"key": key, "reason": "missing_label_or_disputed"})
                    continue
                group = entry["projectName"] if split_by == "project" else entry["projectName"] + "/" + commit
                scenario = MergeScenarioUnderAnalysis(
                    project_name=entry["projectName"], run_analysis=True,
                    scenario_commits=ScenarioInformation(**{b: commits.get(b, "") for b in jars}),
                    scenario_jars=ScenarioInformation(**jars), targets={cls: [item]}, jar_type=entry["jarType"],
                )
                cases.append({"key": key, "group": group, "split": group_split(group, seed),
                              "scenario": scenario, "class": cls, "item": item, "gold": label})
    return cases, excluded


def expected_criteria(gold, question_format="noul"):
    # An overall positive label does not identify which criterion is true.
    if "criteria" not in gold:
        return {}
    unknown = set(gold["criteria"]) - {f"C{c.number}" for c in CRITERIA}
    if unknown:
        raise ValueError(f"Unknown gold criteria: {unknown}")
    expected = {c.id: f"C{c.number}" in gold["criteria"] for c in CRITERIA}
    if question_format == "choice_ab":
        return {key: "A" if value else "B" for key, value in expected.items()}
    return expected


def binary_metrics(pairs):
    """None means abstention, never a true negative. Recall includes all positives."""
    tp = sum(y and p is True for y, p in pairs)
    fp = sum(not y and p is True for y, p in pairs)
    tn = sum(not y and p is False for y, p in pairs)
    fn = sum(y and p is False for y, p in pairs)
    abstained = sum(p is None for _, p in pairs)
    positives = sum(y for y, _ in pairs)
    return {"n": len(pairs), "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "abstained": abstained, "abstained_positive": sum(y and p is None for y, p in pairs),
            "coverage": (len(pairs) - abstained) / len(pairs) if pairs else None,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall_all_positives": tp / positives if positives else None}


def summarize(records, threshold):
    pairs, per_criterion, brier = [], {c.id: [] for c in CRITERIA}, {c.id: [] for c in CRITERIA}
    for record in records:
        assessment = record["assessment"]
        criteria = assessment["criteria"]
        decisions = []
        expected = expected_criteria(record["gold"])
        for criterion in CRITERIA:
            result = criteria[criterion.id]
            probability = result["probability"]
            decision = probability >= threshold if result["status"] == "assessed" and probability is not None else None
            decisions.append(decision)
            if criterion.id in expected:
                label = expected[criterion.id]
                per_criterion[criterion.id].append((label, decision))
                if decision is not None:
                    brier[criterion.id].append((probability - int(label)) ** 2)
        prediction = True if any(d is True for d in decisions) else None if None in decisions else False
        pairs.append((record["gold"]["label"] == "Yes", prediction))
    return {"threshold": threshold, "overall": binary_metrics(pairs),
            "criteria": {key: binary_metrics(values) | {
                "brier_assessed_only": sum(brier[key]) / len(brier[key]) if brier[key] else None
            } for key, values in per_criterion.items()}}


def export_rows(cases, question_format):
    questions = build_questions(question_format)
    for case in cases:
        expected = expected_criteria(case["gold"], question_format)
        if not expected:
            raise ValueError(f"Per-criterion labels required for training export: {case['key']}")
        state = build_method_state(case["scenario"], case["class"], case["item"])
        if state.missing_branches:
            raise ValueError(f"Incomplete training source: {case['key']} {state.missing_branches}")
        yield {"state": state.to_payload(), "questions": questions, "expected": expected,
               "metadata": {"key": case["key"], "group": case["group"], "split": case["split"],
                            "prompt_version": PROMPT_VERSION, "question_format": question_format,
                            "state_digest": state.digest()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--map-path", action="append", default=[], metavar="OLD=NEW")
    parser.add_argument("--dataset-root", default=os.environ.get("PATH_DATASET", ""))
    parser.add_argument("--split-by", choices=["project", "scenario"], default="project")
    parser.add_argument("--split", choices=["all", "train", "validation", "test"], default="all")
    parser.add_argument("--seed", default="smat-laya-v2")
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--models", nargs="+", default=["english"])
    parser.add_argument("--max-lens", nargs="+", type=int, default=[512, 1024, 2048])
    parser.add_argument("--formats", nargs="+", choices=QUESTION_FORMATS, default=["noul"])
    parser.add_argument("--thresholds", nargs="+", type=float, default=[.3, .5, .7])
    args = parser.parse_args()
    if any(not math.isfinite(t) or not 0 <= t <= 1 for t in args.thresholds):
        parser.error("thresholds must be finite numbers in [0, 1]")
    if any(n <= 0 for n in args.max_lens):
        parser.error("max-lens must be positive")
    if args.export_only and len(args.formats) != 1:
        parser.error("export one question format at a time")
    mappings = []
    for value in args.map_path:
        old, separator, new = value.partition("=")
        if not separator or not old or not new:
            parser.error("map-path must be OLD=NEW")
        mappings.append((old, new))
    cases, excluded = load_cases(args.input, args.gold, mappings, args.dataset_root, args.split_by, args.seed)
    selected = [case for case in cases if args.split == "all" or case["split"] == args.split]
    if not selected:
        parser.error("No labelled cases in selected split; inspect grouping or add projects")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = {"prompt_version": PROMPT_VERSION, "split_by": args.split_by, "split": args.split,
                "input_sha256": hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
                "gold_sha256": hashlib.sha256(Path(args.gold).read_bytes()).hexdigest(),
                "seed": args.seed, "selected": len(selected), "excluded": excluded,
                "split_counts": {s: sum(c["split"] == s for c in cases) for s in ("train", "validation", "test")},
                "note": "Tune on validation only. Inspect group balance; synthetic scenarios may share templates."}
    if args.export_only:
        # Validate all rows before writing to avoid a partial training artifact.
        rows = list(export_rows(selected, args.formats[0]))
        output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
        return
    report = {"metadata": metadata, "runs": []}
    for model in args.models:
        # Reuse one checkpoint across formats and budgets.
        from nimrod.laya_interference.client import RouterLayaClient
        client = RouterLayaClient(model=model)
        for max_len in args.max_lens:
            client.max_len = max_len
            for fmt in args.formats:
                config = LayaFlowConfig(model=model, max_len=max_len, question_format=fmt)
                flow = LayaInterferenceFlow(config, client=client, log_dir=str(output.parent))
                records = []
                for case in selected:
                    started = time.perf_counter()
                    assessment = flow._analyze_method(case["scenario"], case["class"], case["item"])
                    records.append({"key": case["key"], "group": case["group"], "split": case["split"],
                                    "elapsed_seconds": time.perf_counter() - started,
                                    "gold": case["gold"], "assessment": assessment.to_dict()})
                run = {"model": model, "max_len": max_len, "question_format": fmt, "client": client.describe(),
                       "errors": sum(bool(r["assessment"]["error"]) for r in records),
                       "incomplete": sum(not r["assessment"]["assessment_complete"] for r in records),
                       "median_seconds_including_source_extraction": statistics.median(r["elapsed_seconds"] for r in records),
                       "metrics": [summarize(records, t) for t in args.thresholds], "records": records}
                report["runs"].append(run)
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps({k: v for k, v in run.items() if k != "records"}), flush=True)


if __name__ == "__main__":
    main()
