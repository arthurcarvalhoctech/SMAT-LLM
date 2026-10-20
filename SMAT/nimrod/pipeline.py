"""Orchestration of the independent interference-detection flows."""

import logging
from typing import Iterable, Optional, Protocol

from nimrod.core.merge_scenario_under_analysis import MergeScenarioUnderAnalysis


class LayaFlow(Protocol):
    def run_for_scenario(self, scenario: MergeScenarioUnderAnalysis) -> object:
        ...


class DynamicFlow(Protocol):
    def run_tool_for_semmantic_conflict_detection(
        self, scenario: MergeScenarioUnderAnalysis
    ) -> None:
        ...


def run_scenarios(
    scenarios: Iterable[MergeScenarioUnderAnalysis],
    laya_flow: Optional[LayaFlow] = None,
    dynamic_flow: Optional[DynamicFlow] = None,
) -> None:
    """Run the enabled flows for every scenario.

    The Laya pre-analysis always runs before the execution-based dynamic
    detection. Either flow may be ``None`` so the user can run neither, only
    one, or both.
    """
    for scenario in scenarios:
        if not scenario.run_analysis:
            logging.info(
                "Skipping tool execution for project %s", scenario.project_name
            )
            continue

        if laya_flow is not None:
            laya_flow.run_for_scenario(scenario)

        if dynamic_flow is not None:
            dynamic_flow.run_tool_for_semmantic_conflict_detection(scenario)
