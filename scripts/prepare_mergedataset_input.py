#!/usr/bin/env python3
"""Prepare an SMAT input file from the mergedataset artifact.

The artifact input (inputs/input-smat.json from the Zenodo package) uses
placeholder paths such as:

    /path/mergedataset/mergedataset/<project>/<hash>/transformed/...

This script rewrites those paths to a real dataset root and keeps only the
scenarios whose four branch JARs exist locally. It also accepts inputs whose
paths are already absolute.
"""

import argparse
import json
import os
from typing import Any, Dict, List

PLACEHOLDER = "/path/mergedataset/mergedataset"


def _rewrite(value: str, dataset_root: str, path_prefix: str) -> str:
    if PLACEHOLDER in value:
        return value.replace(PLACEHOLDER, path_prefix)
    if os.path.isabs(value):
        return value
    return os.path.join(path_prefix, value)


def _all_jars_exist(scenario: Dict[str, Any], dataset_root: str) -> bool:
    for branch in ("base", "left", "right", "merge"):
        value = scenario.get("scenarioJars", {}).get(branch, "")
        for jar_path in value.split(":"):
            if not jar_path:
                continue
            local_path = jar_path
            if PLACEHOLDER in local_path:
                local_path = local_path.replace(PLACEHOLDER, dataset_root)
            elif not os.path.isabs(local_path):
                local_path = os.path.join(dataset_root, local_path)
            if not os.path.isfile(local_path):
                return False
    return True


def prepare(
    artifact_input: str,
    dataset_root: str,
    path_prefix: str,
) -> List[Dict[str, Any]]:
    with open(artifact_input, "r", encoding="utf-8") as file:
        scenarios = json.load(file)

    prepared: List[Dict[str, Any]] = []
    for scenario in scenarios:
        if not _all_jars_exist(scenario, dataset_root):
            continue

        new_scenario = dict(scenario)
        new_scenario["scenarioJars"] = {
            branch: _rewrite(value, dataset_root, path_prefix)
            for branch, value in scenario.get("scenarioJars", {}).items()
        }
        prepared.append(new_scenario)

    return prepared


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-input", required=True, help="Path to the artifact input-smat.json")
    parser.add_argument("--dataset-root", required=True, help="Path to the mergedataset checkout on this machine")
    parser.add_argument("--output", required=True, help="Path of the prepared JSON input")
    parser.add_argument(
        "--path-prefix",
        default=None,
        help="Prefix written into the JSON (for Docker, e.g. /data/mergedataset). Defaults to --dataset-root.",
    )
    args = parser.parse_args()

    path_prefix = args.path_prefix or args.dataset_root
    prepared = prepare(args.artifact_input, args.dataset_root, path_prefix)

    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(prepared, file, indent=2, ensure_ascii=False)
        file.write("\n")

    methods = sum(len(methods) for scenario in prepared for methods in scenario["targets"].values())
    print(f"Scenarios: {len(prepared)}")
    print(f"Target methods: {methods}")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
