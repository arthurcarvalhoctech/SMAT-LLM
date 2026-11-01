#!/usr/bin/env python3
"""Live Laya A/B: baseline JSON state vs compact state + consistent policy.

Run inside an environment with the optional ``laya`` package and the cached
multilingual checkpoint, for example:

    HF_HOME=/home/arthur/.cache/huggingface HF_HUB_OFFLINE=1 \
      PYTHONPATH=SMAT:/tmp/smat-venv/lib/python3.12/site-packages \
      /tmp/laya-live-venv/bin/python scripts/laya_live_compare.py

The script does not call the LLM flow.
"""

import argparse
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("HF_HOME", "/home/arthur/.cache/huggingface")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "dataset-sintetico/input-smat-sintetico.json"
GOLD = ROOT / "dataset-sintetico/gold-sintetico.json"
DEFAULT_CASES = (
    "n01_mapa_chaves_distintas,n02_texto_ordem_independente,"
    "n03_mesma_mudanca_dos_dois_lados,c2a_lista_acumulada,"
    "c3a_xyz_apostila,d1_taxa_sobrescrita"
)


def remap_paths(value):
    if isinstance(value, str):
        return value.replace("/app/", str(ROOT) + "/")
    if isinstance(value, list):
        return [remap_paths(item) for item in value]
    if isinstance(value, dict):
        return {key: remap_paths(item) for key, item in value.items()}
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=DEFAULT_CASES)
    parser.add_argument("--out", default=str(ROOT / "docs/laya-live-compare.json"))
    parser.add_argument("--max-len", type=int, default=4000)
    args = parser.parse_args()
    selected = {item for item in args.cases.split(",") if item}

    from nimrod.input_parsing.input_parser import JsonInputParser
    from nimrod.laya_interference.client import RouterLayaClient
    from nimrod.laya_interference.config import LayaFlowConfig
    from nimrod.laya_interference.flow import LayaInterferenceFlow

    raw = remap_paths(json.loads(INPUT.read_text(encoding="utf-8")))
    raw = [scenario for scenario in raw if scenario["scenarioCommits"]["merge"] in selected]
    if not raw:
        raise SystemExit("No selected cases found in the synthetic input.")

    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as handle:
        json.dump(raw, handle, ensure_ascii=False)
        temp_input = handle.name
    try:
        scenarios = JsonInputParser().parse_input(temp_input)
    finally:
        os.unlink(temp_input)

    gold = {
        (item["commit"], item["class"], item["method"]): item["label"]
        for item in json.loads(GOLD.read_text(encoding="utf-8"))
    }
    client = RouterLayaClient(model="multilingual", max_len=args.max_len)
    configs = {
        "baseline_json": LayaFlowConfig(
            model="multilingual",
            threshold=0.91,
            max_len=args.max_len,
            decision_rule="baseline",
            state_format="json",
            criterion_thresholds=(0.91, 0.91, 0.91),
        ),
        "compact_consistent": LayaFlowConfig(
            model="multilingual",
            threshold=0.91,
            max_len=args.max_len,
            decision_rule="consistent",
            state_format="compact",
            witness=True,
            witness_two_stage=True,
            criterion_thresholds=(0.91, 0.91, 0.91),
        ),
    }

    results = []
    for scenario in scenarios:
        commit = scenario.scenario_commits.merge
        for class_name, items in (scenario.targets or {}).items():
            for item in items:
                label = gold.get((commit, class_name, item["method"]), "-")
                for name, config in configs.items():
                    flow = LayaInterferenceFlow(
                        config,
                        client=client,
                        log_dir="/tmp/laya-live-compare",
                    )
                    assessments = flow.run_for_scenario(
                        _single_target_scenario(scenario, class_name, item)
                    )
                    for assessment in assessments:
                        results.append(
                            {
                                "case": commit,
                                "config": name,
                                "label": label,
                                "class": assessment.class_name,
                                "method": assessment.method_name,
                                "classification": assessment.classification,
                                "triggered_criteria": assessment.triggered_criteria,
                                "primary_criterion": assessment.primary_criterion,
                                "none_probability": assessment.none_probability,
                                "witness": assessment.witness,
                                "witness_confidence": assessment.witness_confidence,
                                "decision_rule": assessment.decision_rule,
                                "decision_reason": assessment.decision_reason,
                                "state_format": assessment.state_format,
                                "probabilities": {
                                    key: value.probability
                                    for key, value in assessment.criteria.items()
                                },
                                "state_digest": assessment.state_digest,
                                "error": assessment.error,
                            }
                        )
                print(
                    f"{commit} [{name if False else ''}] label={label}",
                    flush=True,
                )

    report = {
        "cases": sorted(selected),
        "model": "multilingual",
        "max_len": args.max_len,
        "results": results,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)


def _single_target_scenario(scenario, class_name, item):
    from copy import copy

    selected = copy(scenario)
    selected.targets = {class_name: [item]}
    return selected


if __name__ == "__main__":
    main()
