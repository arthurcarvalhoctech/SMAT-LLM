import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from nimrod.core.feature_flags import (
    LAYA_INTERFERENCE_DETECTION_ENV_VAR,
    is_laya_interference_detection_enabled,
)
from nimrod.core.merge_scenario_under_analysis import (
    MergeScenarioUnderAnalysis,
    ScenarioInformation,
)
from nimrod.laya_interference.client import (
    LayaUnavailableError,
    RouterLayaClient,
)
from nimrod.laya_interference.config import LayaFlowConfig
from nimrod.laya_interference.criteria import (
    AFFECTED_BRANCH_QUESTION_ID,
    CONFIDENCE_QUESTION_ID,
    CRITERIA,
    PRIMARY_CRITERION_QUESTION_ID,
    build_questions,
    choice_label,
    noul_probability,
    score_label,
    score_value,
)
from nimrod.laya_interference.flow import LayaInterferenceFlow
from nimrod.laya_interference.source_context import (
    BranchSource,
    LayaMethodState,
    build_method_state,
)


class FakeLayaClient:
    def __init__(self, result=None, error=None):
        self.result = result or {}
        self.error = error
        self.calls = []

    def predict(self, state, questions):
        self.calls.append((state, questions))
        if self.error is not None:
            raise self.error
        return self.result

    def describe(self):
        return {"package": "fake-laya", "model": "english", "max_len": 512}


def make_result(
    c1=0.91,
    c2=0.42,
    c3=0.12,
    primary="criterion_1_global_divergence",
    branch="left",
    confidence=3.2,
):
    return {
        "answers": {
            "criterion_1_global_divergence": {"type": "noul", "noul": c1},
            "criterion_2_parent_change_loss": {"type": "noul", "noul": c2},
            "criterion_3_merge_new_effect": {"type": "noul", "noul": c3},
            "primary_criterion": {
                "type": "choice",
                "choice": primary,
                "confidence": 0.77,
            },
            "affected_branch": {
                "type": "choice",
                "choice": branch,
                "confidence": 0.66,
            },
            "analysis_confidence": {"type": "score", "score": confidence},
        },
        "routing": {"model": "english"},
        "usage": {"state_tokens": 120, "truncated": False},
    }


def make_state():
    return LayaMethodState(
        project_name="Project",
        class_name="example.Foo",
        method_name="value",
        method_signature="value()",
        jar_type="transformed",
        left_changes_summary="Left changes the return value.",
        right_changes_summary="Right changes a field.",
        branches={
            branch: BranchSource(
                branch=branch,
                path=f"/tmp/{branch}.java",
                fields=["private int x;"],
                constructors=["public Foo() {}"],
                method_code="public int value() { return 1; }",
            )
            for branch in ("base", "left", "right", "merge")
        },
    )


class LayaCriteriaTest(unittest.TestCase):
    def test_builds_three_noul_criteria_plus_choice_and_score(self):
        questions = build_questions()

        for criterion in CRITERIA:
            self.assertEqual(questions[criterion.id]["type"], "noul")

        self.assertEqual(len(CRITERIA), 3)
        self.assertEqual(questions[PRIMARY_CRITERION_QUESTION_ID]["type"], "choice")
        self.assertEqual(questions[AFFECTED_BRANCH_QUESTION_ID]["type"], "choice")
        self.assertEqual(questions[CONFIDENCE_QUESTION_ID]["type"], "score")

    def test_extracts_answers_from_laya_payload(self):
        result = make_result()

        self.assertAlmostEqual(
            noul_probability(result, "criterion_1_global_divergence"), 0.91
        )
        self.assertEqual(
            choice_label(result, PRIMARY_CRITERION_QUESTION_ID),
            "criterion_1_global_divergence",
        )
        self.assertAlmostEqual(score_value(result, CONFIDENCE_QUESTION_ID), 3.2)
        self.assertEqual(score_label(result, CONFIDENCE_QUESTION_ID), "high")


class LayaFlowTest(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = self._temp_dir.name
        self.config = LayaFlowConfig(
            model="english",
            threshold=0.5,
            max_len=512,
            log_dir=self.log_dir,
        )
        self.scenario = MergeScenarioUnderAnalysis(
            project_name="Project",
            run_analysis=True,
            scenario_commits=ScenarioInformation("b", "l", "r", "m"),
            targets={
                "example.Foo": [
                    {
                        "method": "value()",
                        "leftChangesSummary": "Left changes the return value.",
                        "rightChangesSummary": "Right changes a field.",
                    }
                ]
            },
            scenario_jars=ScenarioInformation(
                "/tmp/base.jar", "/tmp/left.jar", "/tmp/right.jar", "/tmp/merge.jar"
            ),
            jar_type="transformed",
        )

    def tearDown(self):
        self._temp_dir.cleanup()

    def test_runs_real_laya_and_writes_readable_log_and_jsonl(self):
        client = FakeLayaClient(result=make_result())

        with patch(
            "nimrod.laya_interference.flow.build_method_state",
            return_value=make_state(),
        ):
            flow = LayaInterferenceFlow(self.config, client=client, log_dir=self.log_dir)
            assessments = flow.run_for_scenario(self.scenario)

        self.assertEqual(len(assessments), 1)
        self.assertEqual(len(client.calls), 1)
        assessment = assessments[0]

        self.assertTrue(assessment.criteria["criterion_1_global_divergence"].triggered)
        self.assertFalse(assessment.criteria["criterion_2_parent_change_loss"].triggered)
        self.assertFalse(assessment.criteria["criterion_3_merge_new_effect"].triggered)
        self.assertEqual(
            assessment.primary_criterion, "criterion_1_global_divergence"
        )
        self.assertEqual(assessment.affected_branch, "left")
        self.assertEqual(assessment.confidence_label, "high")

        log_content = Path(flow.log_path).read_text(encoding="utf-8")
        self.assertIn("Laya interference pre-analysis", log_content)
        self.assertIn("criterion_1_global_divergence", log_content)
        self.assertIn("TRIGGERED", log_content)
        self.assertIn("not-triggered", log_content)
        self.assertIn("primary_criterion: criterion_1_global_divergence", log_content)

        jsonl_lines = Path(flow.jsonl_path).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(jsonl_lines), 1)
        record = json.loads(jsonl_lines[0])
        self.assertEqual(record["project"], "Project")
        self.assertEqual(record["method"], "value")
        self.assertEqual(record["triggered_criteria"], ["criterion_1_global_divergence"])
        self.assertFalse(record["usage"]["truncated"])

    def test_handles_unavailable_laya_without_crashing(self):
        client = FakeLayaClient(error=LayaUnavailableError("laya not installed"))

        with patch(
            "nimrod.laya_interference.flow.build_method_state",
            return_value=make_state(),
        ):
            with self.assertLogs(level="ERROR") as logs:
                flow = LayaInterferenceFlow(
                    self.config, client=client, log_dir=self.log_dir
                )
                assessments = flow.run_for_scenario(self.scenario)

        self.assertEqual(len(assessments), 1)
        self.assertIn("laya not installed", assessments[0].error)
        self.assertIn("Laya pre-analysis is unavailable", "\n".join(logs.output))
        self.assertIn("Traceback", assessments[0].error_traceback or "")
        log_content = Path(flow.log_path).read_text(encoding="utf-8")
        self.assertIn("error: laya not installed", log_content)
        self.assertIn("traceback:", log_content)

    def test_handles_source_state_errors_without_crashing(self):
        with patch(
            "nimrod.laya_interference.flow.build_method_state",
            side_effect=FileNotFoundError("source missing"),
        ):
            with self.assertLogs(level="ERROR") as logs:
                flow = LayaInterferenceFlow(
                    self.config,
                    client=FakeLayaClient(result=make_result()),
                    log_dir=self.log_dir,
                )
                assessments = flow.run_for_scenario(self.scenario)

        self.assertEqual(len(assessments), 1)
        self.assertIn("source missing", assessments[0].error)
        self.assertIn("Traceback", assessments[0].error_traceback or "")
        self.assertIn("could not build the source state", "\n".join(logs.output))
        self.assertEqual(
            assessments[0].missing_branches,
            ["base", "left", "right", "merge"],
        )

    def test_repeated_generic_error_logs_traceback_only_once(self):
        self.scenario.targets = {
            "example.Foo": [{"method": "value()"}, {"method": "other()"}]
        }
        client = FakeLayaClient(error=ValueError("same failure"))

        with patch(
            "nimrod.laya_interference.flow.build_method_state",
            return_value=make_state(),
        ):
            with self.assertLogs(level="ERROR"):
                flow = LayaInterferenceFlow(
                    self.config, client=client, log_dir=self.log_dir
                )
                assessments = flow.run_for_scenario(self.scenario)

        self.assertEqual(len(assessments), 2)
        self.assertIn("Traceback", assessments[0].error_traceback or "")
        self.assertIsNone(assessments[1].error_traceback)

    def test_build_method_state_uses_scenario_sources(self):
        scenario_root = Path(self._temp_dir.name) / "dataset" / "Project" / "abc123"
        for branch in ("base", "left", "right", "merge"):
            branch_dir = scenario_root / "transformed" / branch
            branch_dir.mkdir(parents=True)
            (branch_dir / "app.jar").write_text("")

        source_dir = scenario_root / "source"
        source_dir.mkdir()
        for branch, value in (("base", 0), ("left", 1), ("right", 2), ("merge", 3)):
            (source_dir / f"Foo_{branch}.java").write_text(
                "package example;\n"
                "public class Foo {\n"
                "    private int x;\n"
                "    public Foo() {}\n"
                f"    public int value() {{ return {value}; }}\n"
                "}\n"
            )

        scenario = MergeScenarioUnderAnalysis(
            project_name="Project",
            run_analysis=True,
            scenario_commits=ScenarioInformation("b", "l", "r", "m"),
            targets={"example.Foo": [{"method": "value()"}]},
            scenario_jars=ScenarioInformation(
                str(scenario_root / "transformed" / "base" / "app.jar"),
                str(scenario_root / "transformed" / "left" / "app.jar"),
                str(scenario_root / "transformed" / "right" / "app.jar"),
                str(scenario_root / "transformed" / "merge" / "app.jar"),
            ),
            jar_type="transformed",
        )

        state = build_method_state(scenario, "example.Foo", {"method": "value()"})

        self.assertEqual(state.missing_branches, [])
        self.assertIn("return 1;", state.branches["left"].method_code)
        self.assertIn("return 2;", state.branches["right"].method_code)
        self.assertIn("return 3;", state.branches["merge"].method_code)


class LayaFeatureFlagTest(unittest.TestCase):
    def test_laya_flow_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_laya_interference_detection_enabled())

    def test_laya_flow_can_be_enabled(self):
        with patch.dict(
            os.environ, {LAYA_INTERFERENCE_DETECTION_ENV_VAR: "true"}, clear=True
        ):
            self.assertTrue(is_laya_interference_detection_enabled())


class RouterLayaClientTest(unittest.TestCase):
    def test_calls_laya_router_with_model_and_max_len(self):
        calls = []

        class FakeRouter:
            def predict(self, state, questions, model=None, max_len=None):
                calls.append((state, questions, model, max_len))
                return {"answers": {}}

        fake_module = types.ModuleType("laya")
        fake_module.Router = FakeRouter

        with patch.dict(sys.modules, {"laya": fake_module}):
            client = RouterLayaClient(model="english", max_len=512)
            result = client.predict({"x": 1}, {"q": {}})

        self.assertEqual(result, {"answers": {}})
        self.assertEqual(calls[0][2], "english")
        self.assertEqual(calls[0][3], 512)

    def test_raises_laya_unavailable_when_package_is_missing(self):
        with patch.dict(sys.modules, {"laya": None}):
            client = RouterLayaClient()
            with self.assertRaises(LayaUnavailableError):
                client.predict({}, {})

    def test_rejects_python_311_rc1_missing_int_max_str_digits(self):
        with patch(
            "nimrod.laya_interference.client.sys.version_info",
            (3, 11, 0, "candidate", 1),
        ), patch(
            "nimrod.laya_interference.client._has_int_max_str_digits",
            return_value=False,
        ):
            client = RouterLayaClient()
            with self.assertRaises(LayaUnavailableError) as context:
                client.predict({}, {})

        self.assertIn("get_int_max_str_digits", str(context.exception))
        self.assertIn("3.11.0rc1", str(context.exception))


class LayaLiveSmokeTest(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("SMAT_LAYA_LIVE_TEST") == "1",
        "set SMAT_LAYA_LIVE_TEST=1 to run against the real Laya checkpoint",
    )
    def test_live_laya_router_smoke(self):
        try:
            from laya import Router
        except ImportError:
            self.skipTest("laya package is not installed")

        router = Router()
        result = router.predict(
            "This is a short state used by the live smoke test.",
            {
                "is_test": {
                    "type": "noul",
                    "instructions": "Is this a test?",
                }
            },
            model=os.environ.get("SMAT_LAYA_MODEL", "multilingual"),
            max_len=1024,
        )

        self.assertIn("answers", result)
        self.assertIn("noul", result["answers"]["is_test"])


if __name__ == "__main__":
    unittest.main()
