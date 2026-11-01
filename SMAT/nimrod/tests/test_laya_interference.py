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
    WITNESS_QUESTION_ID,
    build_questions,
    choice_label,
    choice_probability,
    noul_probability,
    score_label,
    score_value,
)
from nimrod.laya_interference.decision import (
    NO_SIGNAL,
    POSSIBLE_INTERFERENCE,
    UNCERTAIN,
    decide,
)
from nimrod.laya_interference.flow import LayaInterferenceFlow
from nimrod.laya_interference.source_context import (
    BranchSource,
    LayaMethodState,
    build_method_state,
)


class FakeLayaClient:
    def __init__(self, result=None, error=None, results=None):
        self.result = result or {}
        self.error = error
        self.results = list(results) if results is not None else None
        self.calls = []

    def predict(self, state, questions):
        self.calls.append((state, questions))
        if self.error is not None:
            raise self.error
        if self.results is not None:
            return self.results.pop(0)
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
    none_probability=0.2,
    witness=None,
):
    answers = {
        "criterion_1_global_divergence": {"type": "noul", "noul": c1},
        "criterion_2_parent_change_loss": {"type": "noul", "noul": c2},
        "criterion_3_merge_new_effect": {"type": "noul", "noul": c3},
        "primary_criterion": {
            "type": "choice",
            "choice": primary,
            "confidence": 0.77,
            "probabilities": {
                "criterion_1_global_divergence": 0.2,
                "criterion_2_parent_change_loss": 0.15,
                "criterion_3_merge_new_effect": 0.1,
                "none": none_probability,
            },
        },
        "affected_branch": {
            "type": "choice",
            "choice": branch,
            "confidence": 0.66,
        },
        "analysis_confidence": {"type": "score", "score": confidence},
    }
    if witness is not None:
        answers[WITNESS_QUESTION_ID] = {
            "type": "choice",
            "choice": witness,
            "confidence": 0.8,
            "probabilities": {witness: 0.8, "none": 0.2},
        }
    return {
        "answers": answers,
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
        self.assertAlmostEqual(
            choice_probability(result, PRIMARY_CRITERION_QUESTION_ID, "none"),
            0.2,
        )
        self.assertAlmostEqual(score_value(result, CONFIDENCE_QUESTION_ID), 3.2)
        self.assertEqual(score_label(result, CONFIDENCE_QUESTION_ID), "high")

    def test_witness_question_is_added_when_candidates_exist(self):
        questions = build_questions(
            {
                "return": "The returned value.",
                "none": "No concrete element.",
            }
        )
        self.assertIn(WITNESS_QUESTION_ID, questions)
        self.assertEqual(questions[WITNESS_QUESTION_ID]["type"], "choice")
        self.assertIn("return", questions[WITNESS_QUESTION_ID]["criteria"])

    def test_witness_only_questions_for_two_stage(self):
        questions = build_questions(
            {"return": "The returned value.", "none": "No concrete element."},
            include_criteria=False,
        )
        self.assertEqual(list(questions), [WITNESS_QUESTION_ID])

    def test_negative_instructions_can_be_toggled(self):
        with_negative = build_questions()
        without_negative = build_questions(negative_instructions=False)
        for criterion in CRITERIA:
            self.assertIn(
                criterion.negative_instruction,
                with_negative[criterion.id]["instructions"],
            )
            self.assertNotIn(
                criterion.negative_instruction,
                without_negative[criterion.id]["instructions"],
            )


class LayaDecisionTest(unittest.TestCase):
    THRESHOLDS = {
        "criterion_1_global_divergence": 0.5,
        "criterion_2_parent_change_loss": 0.5,
        "criterion_3_merge_new_effect": 0.5,
    }

    def test_baseline_matches_any_threshold(self):
        classification, _ = decide(
            "baseline",
            {"criterion_1_global_divergence": 0.91},
            self.THRESHOLDS,
            "none",
            0.99,
        )
        self.assertEqual(classification, POSSIBLE_INTERFERENCE)

    def test_consistent_abstains_when_primary_is_none(self):
        classification, _ = decide(
            "consistent",
            {
                "criterion_1_global_divergence": 0.91,
                "criterion_2_parent_change_loss": 0.88,
                "criterion_3_merge_new_effect": 0.92,
            },
            self.THRESHOLDS,
            "none",
            0.97,
        )
        self.assertEqual(classification, UNCERTAIN)

    def test_consistent_accepts_matching_primary_criterion(self):
        classification, _ = decide(
            "consistent",
            {
                "criterion_1_global_divergence": 0.91,
                "criterion_2_parent_change_loss": 0.2,
                "criterion_3_merge_new_effect": 0.1,
            },
            self.THRESHOLDS,
            "criterion_1_global_divergence",
            0.1,
        )
        self.assertEqual(classification, POSSIBLE_INTERFERENCE)

    def test_conservative_abstains_on_high_none_probability(self):
        classification, _ = decide(
            "conservative",
            {"criterion_1_global_divergence": 0.91},
            self.THRESHOLDS,
            "criterion_1_global_divergence",
            0.97,
        )
        self.assertEqual(classification, UNCERTAIN)

    def test_conservative_accepts_confident_primary(self):
        classification, _ = decide(
            "conservative",
            {"criterion_1_global_divergence": 0.91},
            self.THRESHOLDS,
            "criterion_1_global_divergence",
            0.1,
        )
        self.assertEqual(classification, POSSIBLE_INTERFERENCE)

    def test_witness_none_forces_abstention(self):
        classification, _ = decide(
            "consistent",
            {"criterion_1_global_divergence": 0.91},
            self.THRESHOLDS,
            "criterion_1_global_divergence",
            0.1,
            witness="none",
        )
        self.assertEqual(classification, UNCERTAIN)

    def test_no_signal_when_nothing_triggers(self):
        classification, _ = decide(
            "conservative",
            {"criterion_1_global_divergence": 0.1},
            self.THRESHOLDS,
            "none",
            0.1,
        )
        self.assertIn(classification, (NO_SIGNAL, UNCERTAIN))


class LayaCompactStateTest(unittest.TestCase):
    def test_compact_payload_contains_merge_and_is_smaller(self):
        state = make_state()

        compact = state.to_compact_payload(include_merge=True)
        compact_without_merge = state.to_compact_payload()
        as_json = json.dumps(state.to_payload())

        self.assertIn("Método: Foo.value()", compact)
        self.assertIn("Corpo de base (B):", compact)
        self.assertIn("Corpo do merge (M):", compact)
        self.assertIn("Resumo de Left:", compact)
        self.assertNotIn("Corpo do merge (M):", compact_without_merge)
        self.assertLess(len(compact), len(as_json))
        self.assertNotEqual(state.digest(compact), state.digest())

    def test_witness_candidates_include_return_and_none(self):
        candidates = make_state().witness_candidates()
        self.assertIn("return", candidates)
        self.assertIn("none", candidates)


class LayaConfigTest(unittest.TestCase):
    def test_reads_decision_rule_state_format_and_thresholds(self):
        with patch.dict(
            os.environ,
            {
                "SMAT_LAYA_DECISION_RULE": "consistent",
                "SMAT_LAYA_STATE_FORMAT": "compact",
                "SMAT_LAYA_THRESHOLDS": "0.8,0.7,0.6",
                "SMAT_LAYA_WITNESS": "true",
                "SMAT_LAYA_WITNESS_TWO_STAGE": "true",
            },
            clear=True,
        ):
            config = LayaFlowConfig.from_env("/tmp/laya")
        self.assertEqual(config.decision_rule, "consistent")
        self.assertEqual(config.state_format, "compact")
        self.assertTrue(config.witness)
        self.assertTrue(config.witness_two_stage)
        self.assertEqual(config.criterion_thresholds, (0.8, 0.7, 0.6))

    def test_witness_forces_consistent_rule(self):
        config = LayaFlowConfig(witness=True, decision_rule="baseline")
        self.assertEqual(config.decision_rule, "consistent")

    def test_two_stage_implies_witness_and_consistent(self):
        config = LayaFlowConfig(
            witness=False,
            witness_two_stage=True,
            decision_rule="baseline",
        )
        self.assertTrue(config.witness)
        self.assertEqual(config.decision_rule, "consistent")

    def test_allow_baseline_with_witness_keeps_baseline(self):
        config = LayaFlowConfig(
            witness=True,
            witness_two_stage=False,
            decision_rule="baseline",
            allow_baseline_with_witness=True,
        )
        self.assertEqual(config.decision_rule, "baseline")

    def test_negative_instructions_can_be_disabled_by_env(self):
        with patch.dict(
            os.environ,
            {"SMAT_LAYA_NEGATIVE_INSTRUCTIONS": "false"},
            clear=True,
        ):
            config = LayaFlowConfig.from_env("/tmp/laya")
        self.assertFalse(config.negative_instructions)

    def test_diagnostic_questions_can_be_enabled_by_env(self):
        with patch.dict(
            os.environ,
            {"SMAT_LAYA_DIAGNOSTIC_QUESTIONS": "true"},
            clear=True,
        ):
            config = LayaFlowConfig.from_env("/tmp/laya")
        self.assertTrue(config.diagnostic_questions)


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
        self.assertEqual(
            set(client.calls[0][1]),
            {criterion.id for criterion in CRITERIA},
        )
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
        self.assertIn("witness_two_stage=False", log_content)

        jsonl_lines = Path(flow.jsonl_path).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(jsonl_lines), 1)
        record = json.loads(jsonl_lines[0])
        self.assertEqual(record["project"], "Project")
        self.assertEqual(record["method"], "value")
        self.assertEqual(record["triggered_criteria"], ["criterion_1_global_divergence"])
        self.assertFalse(record["usage"]["truncated"])
        self.assertEqual(record["criterion_thresholds"], [0.5, 0.5, 0.5])
        self.assertFalse(record["witness_two_stage"])

    def test_consistent_compact_flow_returns_uncertain(self):
        config = LayaFlowConfig(
            model="english",
            threshold=0.5,
            max_len=512,
            log_dir=self.log_dir,
            decision_rule="consistent",
            state_format="compact",
            witness=True,
        )
        client = FakeLayaClient(
            result=make_result(
                c1=0.95,
                c2=0.92,
                c3=0.90,
                primary="none",
                none_probability=0.97,
                witness="none",
            )
        )
        with patch(
            "nimrod.laya_interference.flow.build_method_state",
            return_value=make_state(),
        ):
            flow = LayaInterferenceFlow(config, client=client, log_dir=self.log_dir)
            assessments = flow.run_for_scenario(self.scenario)

        assessment = assessments[0]
        self.assertEqual(assessment.classification, "uncertain")
        self.assertAlmostEqual(assessment.none_probability, 0.97)
        self.assertEqual(assessment.state_format, "compact")
        self.assertIsInstance(client.calls[0][0], str)
        self.assertIn("Corpo de base (B):", client.calls[0][0])

    def test_two_stage_witness_focuses_criteria_on_selected_element(self):
        config = LayaFlowConfig(
            model="english",
            threshold=0.5,
            max_len=512,
            log_dir=self.log_dir,
            decision_rule="consistent",
            state_format="compact",
            witness=True,
            witness_two_stage=True,
        )
        witness_result = {
            "answers": {
                WITNESS_QUESTION_ID: {
                    "type": "choice",
                    "choice": "return",
                    "confidence": 0.9,
                }
            }
        }
        criteria_result = make_result(
            c1=0.95,
            c2=0.2,
            c3=0.1,
            primary="criterion_1_global_divergence",
            none_probability=0.1,
        )
        client = FakeLayaClient(results=[witness_result, criteria_result])
        with patch(
            "nimrod.laya_interference.flow.build_method_state",
            return_value=make_state(),
        ):
            flow = LayaInterferenceFlow(config, client=client, log_dir=self.log_dir)
            assessments = flow.run_for_scenario(self.scenario)

        self.assertEqual(len(client.calls), 2)
        self.assertEqual(list(client.calls[0][1]), [WITNESS_QUESTION_ID])
        self.assertIn("Testemunha: return", client.calls[1][0])
        assessment = assessments[0]
        self.assertEqual(assessment.witness, "return")
        self.assertEqual(assessment.classification, "possible_interference")

    def test_two_stage_witness_none_skips_criteria(self):
        config = LayaFlowConfig(
            model="english",
            threshold=0.5,
            max_len=512,
            log_dir=self.log_dir,
            decision_rule="consistent",
            state_format="compact",
            witness=True,
            witness_two_stage=True,
        )
        witness_result = {
            "answers": {
                WITNESS_QUESTION_ID: {
                    "type": "choice",
                    "choice": "none",
                    "confidence": 0.8,
                }
            }
        }
        client = FakeLayaClient(results=[witness_result])
        with patch(
            "nimrod.laya_interference.flow.build_method_state",
            return_value=make_state(),
        ):
            flow = LayaInterferenceFlow(config, client=client, log_dir=self.log_dir)
            assessments = flow.run_for_scenario(self.scenario)

        self.assertEqual(len(client.calls), 1)
        self.assertEqual(assessments[0].witness, "none")
        self.assertEqual(assessments[0].classification, "uncertain")

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
