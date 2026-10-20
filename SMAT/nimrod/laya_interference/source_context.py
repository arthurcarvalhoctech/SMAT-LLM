"""Build the source-code state sent to Laya for a target method."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from nimrod.core.merge_scenario_under_analysis import MergeScenarioUnderAnalysis
from nimrod.source_code import extract_java_class_info, find_source_code_paths


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
        return bool(self.path)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "fields": self.fields,
            "constructors": self.constructors,
            "method": self.method_code,
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
            "project": self.project_name,
            "class": self.class_name,
            "method": self.method_name,
            "method_signature": self.method_signature,
            "jar_type": self.jar_type,
            "left_changes_summary": self.left_changes_summary,
            "right_changes_summary": self.right_changes_summary,
            "versions": {
                branch: self.branches[branch].to_payload()
                if branch in self.branches
                else {"path": "", "fields": [], "constructors": [], "method": ""}
                for branch in BRANCHES
            },
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
    method_item: Union[str, Dict[str, str]],
) -> LayaMethodState:
    """Extract the base/left/right/merge snippets for one target method."""
    jar_for_paths = scenario.scenario_jars.left or scenario.scenario_jars.right
    if not jar_for_paths:
        raise ValueError(
            f"No scenario jar is available for project '{scenario.project_name}'."
        )

    method_signature, left_summary, right_summary = parse_method_item(method_item)
    method_name = method_signature.split("(")[0]
    source_paths = find_source_code_paths(
        jar_for_paths, scenario.jar_type, class_name
    )

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
                source_path, method_signature, class_name
            )
            branches[branch] = BranchSource(
                branch=branch,
                path=source_path,
                fields=fields,
                constructors=constructors,
                method_code=method_code,
            )
        except Exception as error:
            branches[branch] = BranchSource(
                branch=branch,
                path=source_path,
                error=str(error),
            )

    return LayaMethodState(
        project_name=scenario.project_name,
        class_name=class_name,
        method_name=method_name,
        method_signature=method_signature,
        jar_type=scenario.jar_type,
        left_changes_summary=left_summary,
        right_changes_summary=right_summary,
        branches=branches,
    )
