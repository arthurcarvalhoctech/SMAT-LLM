import os
from unittest import TestCase
from unittest.mock import Mock, patch

from nimrod.core.feature_flags import (
    DYNAMIC_INTERFERENCE_DETECTION_ENV_VAR,
    is_dynamic_interference_detection_enabled,
)
from nimrod.smat import SMAT


class TestDynamicInterferenceDetectionFlag(TestCase):
    def test_is_enabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(is_dynamic_interference_detection_enabled())

    def test_is_disabled_for_false_like_values(self):
        for value in ("false", "FALSE", "0", "no", "off", "disabled", "nao", "não"):
            with self.subTest(value=value):
                with patch.dict(
                    os.environ,
                    {DYNAMIC_INTERFERENCE_DETECTION_ENV_VAR: value},
                    clear=True,
                ):
                    self.assertFalse(is_dynamic_interference_detection_enabled())

    def test_is_enabled_for_true_like_values(self):
        for value in ("true", "TRUE", "1", "yes", "on", "enabled", "sim"):
            with self.subTest(value=value):
                with patch.dict(
                    os.environ,
                    {DYNAMIC_INTERFERENCE_DETECTION_ENV_VAR: value},
                    clear=True,
                ):
                    self.assertTrue(is_dynamic_interference_detection_enabled())

    def test_invalid_value_defaults_to_enabled_with_warning(self):
        with patch.dict(
            os.environ,
            {DYNAMIC_INTERFERENCE_DETECTION_ENV_VAR: "maybe"},
            clear=True,
        ):
            with self.assertLogs(level="WARNING") as logs:
                self.assertTrue(is_dynamic_interference_detection_enabled())

        self.assertIn("Valor inválido", "\n".join(logs.output))

    def test_smat_skips_pipeline_when_disabled(self):
        generation = Mock()
        execution = Mock()
        dynamic_analysis = Mock()
        smat = SMAT(generation, execution, dynamic_analysis, [])
        scenario = Mock()
        scenario.project_name = "example"

        with patch.dict(
            os.environ,
            {DYNAMIC_INTERFERENCE_DETECTION_ENV_VAR: "false"},
            clear=True,
        ):
            with self.assertLogs(level="WARNING") as logs:
                smat.run_tool_for_semmantic_conflict_detection(scenario)

        generation.generate_test_suites.assert_not_called()
        execution.execute_test_suites.assert_not_called()
        dynamic_analysis.check_for_semantic_conflicts.assert_not_called()
        dynamic_analysis.check_for_behavior_changes.assert_not_called()
        self.assertIn("não está ativo", "\n".join(logs.output))

    def test_smat_runs_pipeline_when_enabled(self):
        generation = Mock()
        generation.generate_test_suites.return_value = []
        execution = Mock()
        execution.execute_test_suites.return_value = []
        dynamic_analysis = Mock()
        dynamic_analysis.check_for_semantic_conflicts.return_value = []
        dynamic_analysis.check_for_behavior_changes.return_value = []
        smat = SMAT(generation, execution, dynamic_analysis, [])
        scenario = Mock()
        scenario.scenario_jars = Mock()

        with patch.dict(
            os.environ,
            {DYNAMIC_INTERFERENCE_DETECTION_ENV_VAR: "true"},
            clear=True,
        ):
            smat.run_tool_for_semmantic_conflict_detection(scenario)

        self.assertEqual(generation.generate_test_suites.call_count, 2)
        execution.execute_test_suites.assert_called_once_with(
            [], scenario.scenario_jars
        )
        dynamic_analysis.check_for_semantic_conflicts.assert_called_once_with([])
        dynamic_analysis.check_for_behavior_changes.assert_called_once_with([])
