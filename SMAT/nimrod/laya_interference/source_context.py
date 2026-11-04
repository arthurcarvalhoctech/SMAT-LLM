"""Build the source-code state sent to Laya for a target method."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from nimrod.core.merge_scenario_under_analysis import MergeScenarioUnderAnalysis
from nimrod.source_code import extract_java_class_info, find_source_code_paths
from nimrod.laya_interference.criteria import OBSERVATION_POLICY


BRANCHES = ("base", "left", "right", "merge")


@dataclass
class BranchSource:
    branch: str
    path: str = ""
    fields: List[str] = field(default_factory=list)
    constructors: List[str] = field(default_factory=list)
    method_code: str = ""
    error: Optional[str] = None

    @property
    def available(self) -> bool:
        return bool(self.path and self.method_code.strip()) and self.error is None

    def to_payload(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "error": self.error,
            "method": self.method_code,
            "fields": self.fields,
            "constructors": self.constructors,
        }


@dataclass
class LayaMethodState:
    project_name: str
    class_name: str
    method_name: str
    method_signature: str
    jar_type: str
    left_changes_summary: str
    right_changes_summary: str
    branches: Dict[str, BranchSource] = field(default_factory=dict)
    observations: List[str] = field(default_factory=list)
    observation_context: str = ""

    @property
    def missing_branches(self) -> List[str]:
        return [
            branch
            for branch in BRANCHES
            if branch not in self.branches
            or not self.branches[branch].available
            or self.branches[branch].error is not None
        ]

    def source_paths(self) -> Dict[str, str]:
        return {
            branch: self.branches[branch].path
            if branch in self.branches
            else ""
            for branch in BRANCHES
        }

    def to_payload(self) -> Dict[str, Any]:
        return {
            "observation_policy": OBSERVATION_POLICY,
            "observations": self.observations,
            "observation_context": self.observation_context,
            "method_signature": self.method_signature,
            "versions": {
                branch: self.branches[branch].to_payload()
                if branch in self.branches
                else {"available": False, "error": "source unavailable"}
                for branch in BRANCHES
            },
            "left_changes_summary": self.left_changes_summary,
            "right_changes_summary": self.right_changes_summary,
        }

    def digest(self) -> str:
        serialized = json.dumps(
            self.to_payload(), sort_keys=True, ensure_ascii=False
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def parse_method_item(
    method_item: Union[str, Dict[str, str]]
) -> tuple[str, str, str]:
    """Return ``(signature, left_summary, right_summary)`` for a target item."""
    if isinstance(method_item, dict):
        signature = str(method_item.get("method", ""))
        left_summary = str(method_item.get("leftChangesSummary", "") or "")
        right_summary = str(method_item.get("rightChangesSummary", "") or "")
        return signature, left_summary, right_summary

    return str(method_item), "", ""


def build_method_state(
    scenario: MergeScenarioUnderAnalysis,
    class_name: str,
    method_item: Union[str, Dict[str, Any]],
) -> LayaMethodState:
    """Extract the base/left/right/merge snippets for one target method."""
    jar_for_paths = scenario.scenario_jars.left or scenario.scenario_jars.right
    if not jar_for_paths:
        raise ValueError(
            f"No scenario jar is available for project '{scenario.project_name}'."
        )

    method_signature, left_summary, right_summary = parse_method_item(method_item)
    observations = method_item.get("observations", []) if isinstance(method_item, dict) else []
    observation_context = method_item.get("observationContext", "") if isinstance(method_item, dict) else ""
    if not isinstance(observations, list) or any(not isinstance(x, str) or not x.strip() for x in observations):
        raise ValueError("observations must be a list of non-empty expressions")
    if not isinstance(observation_context, str):
        raise ValueError("observationContext must be a string")
    method_name = method_signature.split("(")[0]
    try:
        source_paths = find_source_code_paths(jar_for_paths, scenario.jar_type, class_name)
    except FileNotFoundError:
        source_paths = {}

    branches: Dict[str, BranchSource] = {}
    for branch in BRANCHES:
        source_path = source_paths.get(branch, "")
        if not source_path:
            branches[branch] = BranchSource(
                branch=branch,
                error="source file not found",
            )
            continue

        try:
            fields, constructors, method_code = extract_java_class_info(
                source_path, method_signature, class_name, strict=True
            )
            branches[branch] = BranchSource(
                branch=branch,
                path=source_path,
                fields=fields,
                constructors=constructors,
                method_code=method_code,
                error=None if method_code.strip() else "target body not found",
            )
        except Exception as error:
            branches[branch] = BranchSource(
                branch=branch,
                path=source_path,
                error=str(error),
            )

    # The legacy resolver can reuse one generic file for both parents. Such a
    # fallback cannot establish the behavior of two independent source versions.
    for branch, source in branches.items():
        if source.path and any(other != branch and item.path == source.path
                               for other, item in branches.items()):
            source.error = "same source path reused for multiple versions"

    return LayaMethodState(
        project_name=scenario.project_name,
        class_name=class_name,
        method_name=method_name,
        method_signature=method_signature,
        jar_type=scenario.jar_type,
        left_changes_summary=left_summary,
        right_changes_summary=right_summary,
        branches=branches,
        observations=observations,
        observation_context=observation_context,
    )
