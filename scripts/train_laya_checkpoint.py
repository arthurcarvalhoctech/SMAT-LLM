#!/usr/bin/env python3
"""Prepare a Laya fine-tuning run from the SMAT probe labels and train it.

The training rows come from ``dataset-sintetico/resultados/probe_t1.json``:
each row already carries the compact state (``state_v1``), the scenario label
(``Yes``/``No``) and, for the synthetic cases, the triggered criteria. The
script builds ``{state, questions, gold}`` JSONL rows compatible with
``laya-train``, makes a stratified train/eval split, and optionally runs
``laya-train``.

Usage (from the repository root):

    python3 scripts/train_laya_checkpoint.py --prepare-only
    python3 scripts/train_laya_checkpoint.py --dry-run
    python3 scripts/train_laya_checkpoint.py --out laya_checkpoints/laya_finetuned_smat_multilingual

The output layout is the one ``laya.load()`` expects:
    rl_agent_config.json, model.safetensors, encoder/, tokenizer/
"""

import argparse
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "SMAT"))

# Load the criteria module directly: importing the package would pull
# source_context -> tree-sitter, which is not needed to prepare training data.
_criteria_path = ROOT / "SMAT/nimrod/laya_interference/criteria.py"
_spec = importlib.util.spec_from_file_location(
    "_smat_laya_criteria", _criteria_path
)
if _spec is None or _spec.loader is None:
    raise SystemExit(f"Could not load {_criteria_path}")
_criteria_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_criteria_module)
CRITERIA = _criteria_module.CRITERIA
build_questions = _criteria_module.build_questions

PROBE = ROOT / "dataset-sintetico/resultados/probe_t1.json"
FULL_INPUT = ROOT / "input-smat-mergedataset-full.json"
FULL_GOLD = ROOT / "gold-mergedataset-full.json"
DEFAULT_DATA_DIR = ROOT / "laya_training_data"
DEFAULT_OUT = ROOT / "laya_checkpoints/laya_finetuned_smat_multilingual"

T1_QUESTION = {
    "type": "noul",
    "instructions": (
        "As mudanças de Left e Right podem interagir neste método?"
    ),
}
CRITERION_QUESTIONS = {
    criterion.id: build_questions()[criterion.id]
    for criterion in CRITERIA
}
WITNESS_QUESTION_ID = _criteria_module.WITNESS_QUESTION_ID
PRIMARY_QUESTION_ID = _criteria_module.PRIMARY_CRITERION_QUESTION_ID
NONE_CRITERION = _criteria_module.NONE_CRITERION_LABEL
WITNESS_CANDIDATES = _criteria_module.WITNESS_CANDIDATE_DESCRIPTIONS
GOLD_SYNTHETIC = ROOT / "dataset-sintetico/gold-sintetico.json"


def _questions():
    all_questions = build_questions()
    return {
        "T1": T1_QUESTION,
        **CRITERION_QUESTIONS,
        WITNESS_QUESTION_ID: _criteria_module.build_witness_question(
            WITNESS_CANDIDATES
        ),
        PRIMARY_QUESTION_ID: all_questions[PRIMARY_QUESTION_ID],
    }


def _state_metadata(state):
    """Field order/types and whether the method returns something."""
    fields = {}
    for line in state.splitlines():
        if not line.startswith("Atributos:"):
            continue
        content = line.split(":", 1)[1].strip()
        if content.lower() in {"", "nenhum", "none"}:
            continue
        for match in re.finditer(
            r"([A-Za-z_]\w*)\s*:\s*([^,]+?)(?=\s*,\s*[A-Za-z_]\w*\s*:|$)",
            content,
        ):
            fields[match.group(1)] = match.group(2).strip()
    return fields, "return" in state


def _witness_gold(case, field_types, has_return, synthetic_elements):
    if case.get("label") != "Yes":
        return "none"
    elements = []
    for values in synthetic_elements.get(case.get("id"), {}).values():
        elements.extend(values)
    field_names = list(field_types)
    for element in elements:
        if element in field_types:
            index = field_names.index(element)
            if index < 4:
                return f"field_{index}"
        if element == "size":
            for index, name in enumerate(field_names):
                if any(
                    marker in field_types[name]
                    for marker in ("List", "Map", "Set", "Collection")
                ):
                    if index < 4:
                        return f"field_{index}"
        if "(" in element and has_return:
            return "return"
    if has_return:
        return "return"
    if field_names:
        return "field_0"
    return "none"


def _primary_gold(case):
    if case.get("label") == "No":
        return NONE_CRITERION
    criteria = set(case.get("criteria") or [])
    for criterion in CRITERIA:
        if f"C{criterion.number}" in criteria:
            return criterion.id
    return None


def _gold_for(row):
    label = row.get("label")
    if label not in ("Yes", "No"):
        return None
    gold = {"T1": label == "Yes"}
    criteria = set(row.get("criteria") or [])
    if label == "No":
        for criterion in CRITERIA:
            gold[criterion.id] = False
    elif criteria:
        for criterion in CRITERIA:
            gold[criterion.id] = f"C{criterion.number}" in criteria
    # A real "Yes" without criteria labels is useful for T1 only.
    return gold


def _full_rows():
    """Build real mergedataset rows from the full input and its gold labels."""
    if not FULL_INPUT.is_file() or not FULL_GOLD.is_file():
        return []
    os.environ.setdefault(
        "PATH_DATASET", str(ROOT.parent / "mergedataset")
    )
    try:
        from nimrod.core.merge_scenario_under_analysis import (
            MergeScenarioUnderAnalysis,
            ScenarioInformation,
        )
        from nimrod.laya_interference.source_context import build_method_state
    except Exception as error:  # tree-sitter or dataset dependencies missing
        print(f"Skipping full mergedataset: {error}", file=sys.stderr)
        return []

    raw_scenarios = json.loads(FULL_INPUT.read_text(encoding="utf-8"))
    gold_items = json.loads(FULL_GOLD.read_text(encoding="utf-8"))
    gold = {}
    for item in gold_items:
        gold[(item.get("commit"), item.get("class"), item.get("method"))] = item
    rows = []
    for raw in raw_scenarios:
        jars = raw.get("scenarioJars") or {}
        merge_jar = os.path.expandvars(str(jars.get("merge", "")))
        match = re.search(r"/([0-9a-f]{40})/", merge_jar)
        commit = match.group(1) if match else ""
        targets = raw.get("targets") or {}
        if isinstance(targets, list):
            normalized = {}
            for entry in targets:
                class_name = entry.get("class")
                methods = entry.get("methods", [])
                if not class_name:
                    continue
                normalized[class_name] = [
                    method if isinstance(method, dict) else {"method": method}
                    for method in methods
                ]
            targets = normalized
        scenario = MergeScenarioUnderAnalysis(
            project_name=str(raw.get("projectName")),
            run_analysis=bool(raw.get("runAnalysis", True)),
            scenario_commits=ScenarioInformation(
                **{
                    branch: (raw.get("scenarioCommits") or {}).get(branch)
                    for branch in ("base", "left", "right", "merge")
                }
            ),
            targets=targets,
            scenario_jars=ScenarioInformation(
                **{
                    branch: os.path.expandvars(str(jars.get(branch, "")))
                    for branch in ("base", "left", "right", "merge")
                }
            ),
            jar_type=str(raw.get("jarType")),
        )
        for class_name, methods in targets.items():
            for method_item in methods:
                method = (
                    method_item.get("method")
                    if isinstance(method_item, dict)
                    else str(method_item)
                )
                gold_item = gold.get((commit, class_name, method))
                if gold_item is None:
                    continue
                label = gold_item.get("label")
                if label not in ("Yes", "No"):
                    continue
                try:
                    state = build_method_state(
                        scenario, class_name, method_item
                    )
                except Exception as error:
                    print(
                        f"Skipping {class_name}.{method}: {error}",
                        file=sys.stderr,
                    )
                    continue
                state_text = state.to_compact_payload()
                fields, has_return = _state_metadata(state_text)
                witness = _witness_gold(
                    {"label": label, "id": f"{commit}/{class_name}.{method}"},
                    fields,
                    has_return,
                    {},
                )
                primary = _primary_gold({"label": label, "criteria": []})
                rows.append(
                    {
                        "state": state_text,
                        "questions": _questions(),
                        "gold": {"T1": label == "Yes"},
                        "witness": witness,
                        "primary": primary,
                        "criteria": [],
                        "_set": "mergedataset",
                        "_label": label,
                        "_id": f"{commit}/{class_name}.{method}",
                    }
                )
    return rows


def build_rows():
    cases = json.loads(PROBE.read_text(encoding="utf-8"))
    synthetic = {
        item["commit"]: item.get("elements", {})
        for item in json.loads(GOLD_SYNTHETIC.read_text(encoding="utf-8"))
    }
    rows = []
    for case in cases:
        if case.get("set") != "sintetico":
            continue
        state = case.get("state_v1")
        gold = _gold_for(case)
        if not state or gold is None:
            continue
        field_types, has_return = _state_metadata(state)
        witness = _witness_gold(
            case, field_types, has_return, synthetic
        )
        primary = _primary_gold(case)
        rows.append(
            {
                "state": state,
                "questions": _questions(),
                "gold": gold,
                "witness": witness,
                "primary": primary,
                "criteria": case.get("criteria") or [],
                "_set": case.get("set", "unknown"),
                "_label": case.get("label"),
                "_id": case.get("id"),
            }
        )
    full_rows = _full_rows()
    if full_rows:
        rows.extend(full_rows)
    else:
        # Keep the 13 real probe cases if the full mergedataset cannot be loaded.
        for case in cases:
            if case.get("set") != "mergedataset":
                continue
            state = case.get("state_v1")
            gold = _gold_for(case)
            if not state or gold is None:
                continue
            field_types, has_return = _state_metadata(state)
            witness = _witness_gold(
                case, field_types, has_return, synthetic
            )
            primary = _primary_gold(case)
            rows.append(
                {
                    "state": state,
                    "questions": _questions(),
                    "gold": gold,
                    "witness": witness,
                    "primary": primary,
                    "criteria": case.get("criteria") or [],
                    "_set": case.get("set", "unknown"),
                    "_label": case.get("label"),
                    "_id": case.get("id"),
                }
            )
    return rows


def split_rows(rows, eval_fraction, seed):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["_set"], row["_label"])].append(row)
    rng = random.Random(seed)
    train, evaluation = [], []
    for key in sorted(groups):
        group = groups[key]
        rng.shuffle(group)
        n_eval = max(1, round(len(group) * eval_fraction)) if len(group) > 1 else 0
        evaluation.extend(group[:n_eval])
        train.extend(group[n_eval:])
    rng.shuffle(train)
    rng.shuffle(evaluation)
    return train, evaluation


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            expected = dict(row["gold"])
            expected[WITNESS_QUESTION_ID] = row["witness"]
            if row["primary"] is not None:
                expected[PRIMARY_QUESTION_ID] = row["primary"]
            clean = {
                "state": row["state"],
                "questions": row["questions"],
                "expected": expected,
                "_meta": {
                    "set": row["_set"],
                    "label": row["_label"],
                    "id": row["_id"],
                    "criteria": row.get("criteria", []),
                },
            }
            handle.write(json.dumps(clean, ensure_ascii=False) + "\n")


def find_laya_train():
    executable = shutil.which("laya-train")
    if executable:
        return [executable]
    try:
        import laya.train_cli  # noqa: F401
    except ImportError:
        return None
    return [sys.executable, "-m", "laya.train_cli"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--base", default="multilingual")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--max-len", type=int, default=4000)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--eval-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--full-finetune",
        action="store_true",
        help="Train the encoder too (default: freeze encoder for the small dataset).",
    )
    args = parser.parse_args()

    rows = build_rows()
    if not rows:
        raise SystemExit("No labeled rows found in probe_t1.json.")
    train, evaluation = split_rows(rows, args.eval_fraction, args.seed)
    data_dir = Path(args.data_dir)
    train_path = data_dir / "train.jsonl"
    eval_path = data_dir / "eval.jsonl"
    all_path = data_dir / "all.jsonl"
    write_jsonl(train_path, train)
    write_jsonl(eval_path, evaluation)
    write_jsonl(all_path, rows)
    manifest = {
        "source": str(PROBE.relative_to(ROOT)),
        "total_labeled": len(rows),
        "train": len(train),
        "eval": len(evaluation),
        "sets": {
            f"{set_name}/{label}": sum(
                1
                for row in rows
                if row["_set"] == set_name and row["_label"] == label
            )
            for set_name, label in sorted(
                {(row["_set"], row["_label"]) for row in rows}
            )
        },
        "witness": {
            "none": sum(1 for row in rows if row["witness"] == "none"),
            "concrete": sum(1 for row in rows if row["witness"] != "none"),
        },
        "primary": {
            "none": sum(1 for row in rows if row["primary"] == NONE_CRITERION),
            "concrete": sum(
                1
                for row in rows
                if row["primary"] not in (None, NONE_CRITERION)
            ),
            "unlabeled": sum(1 for row in rows if row["primary"] is None),
        },
        "note": (
            "Small labeled set. Keep eval separate and treat the result as an "
            "experiment; synthetic cases have criterion labels, real cases may "
            "only have the T1 yes/no label."
        ),
    }
    (data_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Training data: {train_path} ({len(train)} rows)")
    print(f"Evaluation data: {eval_path} ({len(evaluation)} rows)")
    print(f"All labeled data: {all_path} ({len(rows)} rows)")
    print(f"Manifest: {data_dir / 'manifest.json'}")
    if args.prepare_only:
        return

    laya_train = find_laya_train()
    if laya_train is None:
        print(
            "\nLaya is not installed in this Python environment. Install it with:\n"
            "  pip install -r SMAT/requirements-laya.txt\n"
            "or run the training inside Docker with INSTALL_LAYA=true.\n"
            "The JSONL files above are ready.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    command = laya_train + [
        "--data",
        str(train_path),
        "--eval",
        str(eval_path),
        "--base",
        args.base,
        "--out",
        str(args.out),
        "--epochs",
        str(args.epochs),
        "--micro-batch",
        "2",
        "--grad-accum",
        "4",
        "--loss",
        "rlcd",
        "--max-len",
        str(args.max_len),
        "--device",
        args.device,
        "--seed",
        str(args.seed),
    ]
    if not args.full_finetune:
        command.append("--freeze-encoder")
    if args.dry_run:
        command.append("--dry-run")

    print("\nRunning:", " ".join(command), flush=True)
    subprocess.run(command, check=True)
    if args.dry_run:
        print("\nDry-run only; no checkpoint was written.")
        return
    print(f"\nCheckpoint: {Path(args.out)}")
    print("To use it in Docker:")
    print("  LAYA_SMAT_DIR=./laya_checkpoints")
    print("  SMAT_LAYA_MODEL=/laya_smat/laya_finetuned_smat_multilingual")


if __name__ == "__main__":
    main()
