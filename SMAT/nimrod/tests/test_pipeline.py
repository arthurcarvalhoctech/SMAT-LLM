import os
import unittest
from unittest.mock import Mock, patch

from nimrod import __main__ as smat_main
from nimrod.pipeline import run_scenarios


def make_scenario(run_analysis=True):
    scenario = Mock()
    scenario.project_name = "Project"
    scenario.run_analysis = run_analysis
    return scenario


class PipelineOrchestrationTest(unittest.TestCase):
    def test_laya_runs_before_dynamic_detection(self):
        call_order = []
        laya_flow = Mock()
        laya_flow.run_for_scenario.side_effect = lambda scenario: call_order.append(
            "laya"
        )
        dynamic_flow = Mock()
        dynamic_flow.run_tool_for_semmantic_conflict_detection.side_effect = (
            lambda scenario: call_order.append("dynamic")
        )

        run_scenarios(
            [make_scenario()],
            laya_flow=laya_flow,
            dynamic_flow=dynamic_flow,
        )

        self.assertEqual(call_order, ["laya", "dynamic"])

    def test_can_run_only_laya(self):
        laya_flow = Mock()
        scenario = make_scenario()

        run_scenarios([scenario], laya_flow=laya_flow, dynamic_flow=None)

        laya_flow.run_for_scenario.assert_called_once_with(scenario)

    def test_can_run_only_dynamic_detection(self):
        dynamic_flow = Mock()
        scenario = make_scenario()

        run_scenarios([scenario], laya_flow=None, dynamic_flow=dynamic_flow)

        dynamic_flow.run_tool_for_semmantic_conflict_detection.assert_called_once_with(
            scenario
        )

    def test_can_run_neither_flow(self):
        laya_flow = Mock()
        dynamic_flow = Mock()

        run_scenarios([make_scenario()], laya_flow=None, dynamic_flow=None)

        laya_flow.run_for_scenario.assert_not_called()
        dynamic_flow.run_tool_for_semmantic_conflict_detection.assert_not_called()

    def test_skips_scenarios_with_run_analysis_false(self):
        laya_flow = Mock()
        dynamic_flow = Mock()

        run_scenarios(
            [make_scenario(run_analysis=False)],
            laya_flow=laya_flow,
            dynamic_flow=dynamic_flow,
        )

        laya_flow.run_for_scenario.assert_not_called()
        dynamic_flow.run_tool_for_semmantic_conflict_detection.assert_not_called()


class LayaFlowBuilderTest(unittest.TestCase):
    def test_build_laya_flow_uses_reports_laya_directory(self):
        with patch.dict(os.environ, {}, clear=True):
            flow = smat_main._build_laya_flow()

        self.assertTrue(
            flow.log_dir.endswith(os.path.join("reports", "laya")),
            flow.log_dir,
        )


if __name__ == "__main__":
    unittest.main()
