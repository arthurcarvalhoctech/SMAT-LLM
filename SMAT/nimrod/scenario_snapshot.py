"""Persist merge scenarios as a readable source snapshot.

The snapshot layout is:

    <output_root>/<input_file_stem>_<timestamp>/
        manifest.json
        001_<project>/
            base
            left
            right
            merge
        ...

Each branch file contains the Java sources of every target class for that
branch, separated by headers. The files are intended for inspection and
analysis; concatenating multiple classes does not produce a compilable Java
file.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from nimrod.core.merge_scenario_under_analysis import MergeScenarioUnderAnalysis
from nimrod.source_code import find_source_code_paths
from nimrod.tests.utils import get_base_output_path


BRANCHES: Tuple[str, ...] = ("base", "left", "right", "merge")


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_")
    return safe or "unnamed"


def dataset_name_from_input(input_path: str) -> str:
    """Derive the dataset name from the input file name."""
    if not input_path:
        return "dataset"
    return _safe_name(Path(input_path).stem)


def default_snapshot_root() -> str:
    """Return ``SMAT/output-test-dest/scenarios`` next to the existing reports."""
    return os.path.join(os.path.dirname(get_base_output_path()), "scenarios")


def scenario_folder_name(index: int, project_name: str) -> str:
    return f"{index:03d}_{_safe_name(project_name)}"


def _collect_branch_sources(
    scenario: MergeScenarioUnderAnalysis,
) -> Tuple[Dict[str, Dict[str, List[str]]], List[str]]:
    """Return branch -> source_path -> target classes, plus missing-source notes."""
    sources: Dict[str, Dict[str, List[str]]] = {branch: {} for branch in BRANCHES}
    missing: List[str] = []

    jar_for_paths = scenario.scenario_jars.left or scenario.scenario_jars.right
    if not jar_for_paths:
        return sources, ["no scenario jar available"]

    for class_name in scenario.targets or {}:
        try:
            paths = find_source_code_paths(
                jar_for_paths, scenario.jar_type, class_name
            )
        except Exception as error:
            missing.append(f"{class_name}: {error}")
            continue

        for branch in BRANCHES:
            path = paths.get(branch, "")
            if not path:
                missing.append(f"{class_name}: no {branch} source")
                continue
            sources[branch].setdefault(path, []).append(class_name)

    return sources, missing


def _render_branch_file(
    dataset: str,
    run_id: str,
    scenario_index: int,
    scenario: MergeScenarioUnderAnalysis,
    branch: str,
    sources: Dict[str, List[str]],
    missing: Sequence[str],
) -> str:
    lines = [
        "// " + "=" * 76,
        "// SMAT merge scenario snapshot",
        f"// dataset: {dataset}",
        f"// run: {run_id}",
        f"// scenario: {scenario_index:03d} - {scenario.project_name}",
        f"// branch: {branch}",
        f"// jar_type: {scenario.jar_type}",
        "// scenario_commits: "
        + json.dumps(
            scenario.scenario_commits.__dict__,
            ensure_ascii=False,
            sort_keys=True,
        ),
        "// NOTE: multiple target classes may be concatenated below; this file is",
        "// a snapshot for analysis and is not intended to compile as one Java file.",
        "// " + "=" * 76,
        "",
    ]

    if not sources:
        lines.append(f"// No source files found for branch '{branch}'.")
        if missing:
            lines.append("// Missing sources:")
            lines.extend(f"//   - {note}" for note in missing)
        return "\n".join(lines) + "\n"

    for source_path, class_names in sources.items():
        lines.append("// " + "-" * 76)
        lines.append("// target classes: " + ", ".join(class_names))
        lines.append(f"// source: {source_path}")
        lines.append("// " + "-" * 76)
        try:
            content = Path(source_path).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError as error:
            lines.append(f"// Could not read source file: {error}")
            content = ""
        lines.append(content.rstrip())
        lines.append("")

    if missing:
        lines.append("// Missing sources:")
        lines.extend(f"//   - {note}" for note in missing)
        lines.append("")

    return "\n".join(lines) + "\n"


def persist_merge_scenarios(
    scenarios: Sequence[MergeScenarioUnderAnalysis],
    input_path: str = "",
    output_root: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> str:
    """Write one folder per merge scenario and return the snapshot root.

    Returns an empty string when there is no scenario to persist.
    """
    scenario_list = list(scenarios)
    if not scenario_list:
        logging.info("No merge scenarios to persist")
        return ""

    run_id = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dataset = dataset_name_from_input(input_path)
    root = os.path.join(
        output_root or default_snapshot_root(),
        f"{dataset}_{run_id}",
    )

    try:
        os.makedirs(root, exist_ok=True)
    except OSError as error:
        logging.error("Could not create scenario snapshot root %s: %s", root, error)
        return ""

    manifest: Dict[str, object] = {
        "dataset": dataset,
        "run_id": run_id,
        "input_path": input_path,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": root,
        "scenarios": [],
    }
    manifest_scenarios: List[Dict[str, object]] = []

    for index, scenario in enumerate(scenario_list, start=1):
        folder = scenario_folder_name(index, scenario.project_name)
        scenario_dir = os.path.join(root, folder)
        sources, missing = _collect_branch_sources(scenario)

        try:
            os.makedirs(scenario_dir, exist_ok=True)
            for branch in BRANCHES:
                content = _render_branch_file(
                    dataset=dataset,
                    run_id=run_id,
                    scenario_index=index,
                    scenario=scenario,
                    branch=branch,
                    sources=sources[branch],
                    missing=missing,
                )
                Path(os.path.join(scenario_dir, branch)).write_text(
                    content, encoding="utf-8"
                )
        except OSError as error:
            logging.error(
                "Could not persist merge scenario %s (%s): %s",
                index,
                scenario.project_name,
                error,
            )

        manifest_scenarios.append(
            {
                "index": index,
                "folder": folder,
                "project": scenario.project_name,
                "run_analysis": scenario.run_analysis,
                "jar_type": scenario.jar_type,
                "scenario_commits": scenario.scenario_commits.__dict__,
                "scenario_jars": scenario.scenario_jars.__dict__,
                "targets": scenario.targets,
                "files": {
                    branch: os.path.join(scenario_dir, branch)
                    for branch in BRANCHES
                },
                "missing_sources": missing,
            }
        )

    manifest["scenarios"] = manifest_scenarios
    try:
        with open(
            os.path.join(root, "manifest.json"), "w", encoding="utf-8"
        ) as manifest_file:
            json.dump(manifest, manifest_file, indent=2, ensure_ascii=False)
            manifest_file.write("\n")
    except OSError as error:
        logging.error("Could not write scenario snapshot manifest in %s: %s", root, error)

    logging.info(
        "Persisted %d merge scenario(s) to %s", len(scenario_list), root
    )
    return root
