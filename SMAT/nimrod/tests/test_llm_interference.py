import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nimrod.core.feature_flags import (
    LLM_INTERFERENCE_DETECTION_ENV_VAR,
    is_llm_interference_detection_enabled,
)
from nimrod.core.merge_scenario_under_analysis import (
    MergeScenarioUnderAnalysis,
    ScenarioInformation,
)
from nimrod.llm_interference.client import ApiLlmClient, LlmUnavailableError
from nimrod.llm_interference.config import (
    LLM_FALLBACK_MODEL_ENV_VAR,
    LLM_JSON_MODE_ENV_VAR,
    LLM_MAX_OUTPUT_TOKENS_ENV_VAR,
    LLM_MODEL_ENV_VAR,
    LLM_RETRY_ON_LENGTH_ENV_VAR,
    LlmFlowConfig,
)
from nimrod.llm_interference.criteria import (
    LlmResponseError,
    parse_llm_analysis,
)
from nimrod.llm_interference.flow import LlmInterferenceFlow
from nimrod.llm_interference.source_context import BranchSource, MethodState
from nimrod.laya_interference.criteria import CRITERIA
from nimrod.test_suite_generation.generators.llm_config import LlmConfig


def make_state():
    return MethodState(
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


def make_result():
    return {
        "analysis": {
            "criteria": {
                CRITERIA[0].id: {
                    "probability": 0.9,
                    "triggered": True,
                    "evidence": "Base, left and right diverge.",
                },
                CRITERIA[1].id: {
                    "probability": 0.2,
                    "triggered": False,
                    "evidence": "No lost parent change.",
                },
                CRITERIA[2].id: {
                    "probability": 0.1,
                    "triggered": False,
                    "evidence": "Merge does not add an unrelated effect.",
                },
            },
            "primary_criterion": CRITERIA[0].id,
            "affected_branch": "left",
            "confidence": "high",
            "summary": "Possible interference in the return value.",
            "reasoning": "The left change is not preserved.",
        },
        "raw_response": '{"criteria": {}}',
        "provider": "fake",
        "model": "fake-model",
        "routing": {"provider": "fake"},
        "usage": {"total_duration": 10},
    }


class FakeLlmClient:
    def __init__(self, result=None, error=None):
        self.result = result or make_result()
        self.error = error
        self.calls = []

    def analyze(self, state):
        self.calls.append(state)
        if self.error is not None:
            raise self.error
        return self.result

    def describe(self):
        return {"provider": "fake", "model": "fake-model", "api_kind": "openai"}


def make_scenario():
    return MergeScenarioUnderAnalysis(
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


class LlmCriteriaParsingTest(unittest.TestCase):
    def test_parses_fenced_json_and_criteria(self):
        payload = make_result()["analysis"]
        text = "```json\n" + json.dumps(payload) + "\n```"

        analysis = parse_llm_analysis(text, threshold=0.5)

        self.assertTrue(analysis["criteria"][CRITERIA[0].id]["triggered"])
        self.assertAlmostEqual(
            analysis["criteria"][CRITERIA[0].id]["probability"], 0.9
        )
        self.assertEqual(analysis["primary_criterion"], CRITERIA[0].id)
        self.assertEqual(analysis["affected_branch"], "left")
        self.assertEqual(analysis["confidence"], "high")
        self.assertIn("return value", analysis["summary"])

    def test_ignores_extra_data_after_first_object(self):
        payload = make_result()["analysis"]
        text = json.dumps(payload) + '\n{"extra": "second object"}'
        analysis = parse_llm_analysis(text, threshold=0.5)
        self.assertEqual(analysis["primary_criterion"], CRITERIA[0].id)

    def test_rejects_invalid_json(self):
        with self.assertRaises(LlmResponseError):
            parse_llm_analysis("not json", threshold=0.5)

    def test_derives_triggered_from_probability_when_absent(self):
        payload = make_result()["analysis"]
        payload["criteria"][CRITERIA[0].id].pop("triggered")
        analysis = parse_llm_analysis(json.dumps(payload), threshold=0.5)
        self.assertTrue(analysis["criteria"][CRITERIA[0].id]["triggered"])


class LlmFlowTest(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.log_dir = self._temp_dir.name
        self.config = LlmFlowConfig(
            threshold=0.5,
            max_input_chars=24000,
            log_dir=self.log_dir,
        )
        self.scenario = make_scenario()

    def tearDown(self):
        self._temp_dir.cleanup()

    def test_writes_log_jsonl_and_classification(self):
        client = FakeLlmClient()

        with patch(
            "nimrod.llm_interference.flow.build_method_state",
            return_value=make_state(),
        ):
            flow = LlmInterferenceFlow(
                self.config, client=client, log_dir=self.log_dir
            )
            assessments = flow.run_for_scenario(self.scenario)

        self.assertEqual(len(assessments), 1)
        self.assertEqual(len(client.calls), 1)
        assessment = assessments[0]
        self.assertEqual(assessment.classification, "possible_interference")
        self.assertEqual(assessment.triggered_criteria, [CRITERIA[0].id])
        self.assertEqual(assessment.primary_criterion, CRITERIA[0].id)
        self.assertEqual(assessment.affected_branch, "left")
        self.assertEqual(assessment.confidence, "high")

        log_content = Path(flow.log_path).read_text(encoding="utf-8")
        self.assertIn("LLM interference pre-analysis", log_content)
        self.assertIn(CRITERIA[0].id, log_content)
        self.assertIn("TRIGGERED", log_content)
        self.assertIn("evidence: Base, left and right diverge.", log_content)
        self.assertIn("summary: Possible interference", log_content)

        jsonl_lines = Path(flow.jsonl_path).read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(jsonl_lines), 1)
        record = json.loads(jsonl_lines[0])
        self.assertEqual(record["run_id"], flow.run_id)
        self.assertEqual(record["project"], "Project")
        self.assertEqual(record["triggered_criteria"], [CRITERIA[0].id])
        self.assertEqual(record["criteria"][CRITERIA[0].id]["probability"], 0.9)

        classification_files = list(
            Path(flow.classification_dir).glob("*.json")
        )
        self.assertEqual(len(classification_files), 1)
        classification = json.loads(
            classification_files[0].read_text(encoding="utf-8")
        )
        self.assertEqual(classification["run_id"], flow.run_id)
        self.assertEqual(classification["classification"], "possible_interference")
        self.assertEqual(
            classification["triggered_criteria"], [CRITERIA[0].id]
        )
        self.assertEqual(classification["probabilities"][CRITERIA[0].id], 0.9)

    def test_handles_unavailable_llm_without_crashing(self):
        client = FakeLlmClient(error=LlmUnavailableError("api key missing"))

        with patch(
            "nimrod.llm_interference.flow.build_method_state",
            return_value=make_state(),
        ):
            with self.assertLogs(level="ERROR") as logs:
                flow = LlmInterferenceFlow(
                    self.config, client=client, log_dir=self.log_dir
                )
                assessments = flow.run_for_scenario(self.scenario)

        self.assertEqual(len(assessments), 1)
        self.assertIn("api key missing", assessments[0].error)
        self.assertIn(
            "LLM interference pre-analysis is unavailable",
            "\n".join(logs.output),
        )
        self.assertIn("Traceback", assessments[0].error_traceback or "")
        log_content = Path(flow.log_path).read_text(encoding="utf-8")
        self.assertIn("error: api key missing", log_content)
        self.assertIn("traceback:", log_content)

    def test_handles_source_state_errors_without_crashing(self):
        with patch(
            "nimrod.llm_interference.flow.build_method_state",
            side_effect=FileNotFoundError("source missing"),
        ):
            with self.assertLogs(level="ERROR") as logs:
                flow = LlmInterferenceFlow(
                    self.config,
                    client=FakeLlmClient(),
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


    def test_records_llm_error_metadata(self):
        error = RuntimeError("truncated JSON")
        error.llm_metadata = {
            "provider": "deepseek",
            "model": "deepseek-flash",
            "finish_reason": "length",
            "usage": {"completion_tokens": 8192, "reasoning_tokens": 8192},
            "raw_response": '{"criteria":',
            "reasoning_content_preview": "long reasoning",
            "attempts": [
                {
                    "attempt": 1,
                    "model": "deepseek-flash",
                    "max_output_tokens": 8192,
                    "finish_reason": "length",
                },
                {
                    "attempt": 2,
                    "model": "deepseek-chat",
                    "max_output_tokens": 8192,
                    "finish_reason": "length",
                },
            ],
        }

        with patch(
            "nimrod.llm_interference.flow.build_method_state",
            return_value=make_state(),
        ):
            with self.assertLogs(level="ERROR"):
                flow = LlmInterferenceFlow(
                    self.config,
                    client=FakeLlmClient(error=error),
                    log_dir=self.log_dir,
                )
                assessments = flow.run_for_scenario(self.scenario)

        self.assertEqual(len(assessments), 1)
        assessment = assessments[0]
        self.assertEqual(assessment.finish_reason, "length")
        self.assertEqual(len(assessment.attempts), 2)
        self.assertEqual(assessment.raw_response, '{"criteria":')
        self.assertEqual(assessment.error_metadata["model"], "deepseek-flash")

        log_content = Path(flow.log_path).read_text(encoding="utf-8")
        self.assertIn("finish_reason: length", log_content)
        self.assertIn("raw_response_preview", log_content)
        self.assertIn("attempts: 2", log_content)

        classification_files = list(
            Path(flow.classification_dir).glob("*.json")
        )
        self.assertEqual(len(classification_files), 1)
        classification = json.loads(
            classification_files[0].read_text(encoding="utf-8")
        )
        self.assertEqual(classification["finish_reason"], "length")
        self.assertEqual(len(classification["attempts"]), 2)
        self.assertEqual(
            classification["raw_response_preview"], '{"criteria":'
        )
        self.assertEqual(classification["classification"], "error")


class LlmFlagTest(unittest.TestCase):
    def test_defaults_to_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_llm_interference_detection_enabled())

    def test_true_like_values_enable(self):
        with patch.dict(
            os.environ, {LLM_INTERFERENCE_DETECTION_ENV_VAR: "true"}, clear=True
        ):
            self.assertTrue(is_llm_interference_detection_enabled())

    def test_false_like_values_disable(self):
        with patch.dict(
            os.environ, {LLM_INTERFERENCE_DETECTION_ENV_VAR: "off"}, clear=True
        ):
            self.assertFalse(is_llm_interference_detection_enabled())


class FakeApi:
    def __init__(self, responses):
        self.responses = list(responses)
        self.response_format = None
        self.calls = 0

    def generate_output(self, messages):
        self.calls += 1
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_length_error():
    error = RuntimeError("Empty response from provider")
    error.finish_reason = "length"
    error.usage = {"completion_tokens": 8192, "reasoning_tokens": 8192}
    error.reasoning_content = "long reasoning that consumed the budget"
    return error


def make_valid_api_response():
    return {
        "response": json.dumps(make_result()["analysis"]),
        "finish_reason": "stop",
        "usage": {"completion_tokens": 100},
        "reasoning_content": "",
    }


def make_resolved_config(model="deepseek-flash"):
    return LlmConfig(
        provider="deepseek",
        model=model,
        api_key="test-key",
        base_url="https://api.deepseek.com",
        max_output_tokens=8192,
    )


def run_client(config, responses):
    api = FakeApi(responses)
    configs = []

    def create_api(api_config):
        configs.append(api_config)
        return api

    with patch(
        "nimrod.test_suite_generation.generators.llm_config.resolve_llm_config",
        return_value=make_resolved_config(),
    ), patch(
        "nimrod.test_suite_generation.generators.llm_api.create_llm_api",
        side_effect=create_api,
    ):
        result = ApiLlmClient(config).analyze(make_state())

    return result, configs, api


class LlmClientRetryTest(unittest.TestCase):
    def test_retries_length_with_fallback_model_and_json_mode(self):
        config = LlmFlowConfig(
            model="deepseek-flash",
            fallback_model="deepseek-chat",
            max_output_tokens=8192,
            json_mode=True,
            retry_on_length=True,
        )

        result, configs, api = run_client(
            config, [make_length_error(), make_valid_api_response()]
        )

        self.assertEqual(len(configs), 2)
        self.assertEqual(configs[0].model, "deepseek-flash")
        self.assertEqual(configs[1].model, "deepseek-chat")
        self.assertEqual(api.response_format, {"type": "json_object"})
        self.assertEqual(result["finish_reason"], "stop")
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(result["attempts"][0]["finish_reason"], "length")
        self.assertEqual(result["attempts"][1]["finish_reason"], "stop")
        self.assertTrue(
            result["analysis"]["criteria"][CRITERIA[0].id]["triggered"]
        )

    def test_retries_length_with_larger_budget_without_fallback(self):
        config = LlmFlowConfig(
            model="deepseek-flash",
            max_output_tokens=8192,
            retry_on_length=True,
        )

        result, configs, _ = run_client(
            config, [make_length_error(), make_valid_api_response()]
        )

        self.assertEqual(len(configs), 2)
        self.assertEqual(configs[0].max_output_tokens, 8192)
        self.assertEqual(configs[1].max_output_tokens, 16384)
        self.assertEqual(len(result["attempts"]), 2)

    def test_attaches_metadata_when_length_persists(self):
        config = LlmFlowConfig(
            model="deepseek-flash",
            fallback_model="deepseek-chat",
            max_output_tokens=8192,
            retry_on_length=True,
        )

        with self.assertRaises(RuntimeError) as context:
            run_client(config, [make_length_error(), make_length_error()])

        error = context.exception
        metadata = error.llm_metadata
        self.assertEqual(metadata["finish_reason"], "length")
        self.assertEqual(len(metadata["attempts"]), 2)
        self.assertEqual(metadata["usage"]["completion_tokens"], 8192)
        self.assertIn("reasoning_content_preview", metadata)

    def test_attaches_raw_response_on_invalid_json(self):
        config = LlmFlowConfig(
            model="deepseek-chat",
            max_output_tokens=8192,
            json_mode=True,
            retry_on_length=True,
        )
        response = {
            "response": '{"criteria":',
            "finish_reason": "stop",
            "usage": {"completion_tokens": 10},
            "reasoning_content": "",
        }

        with self.assertRaises(LlmResponseError) as context:
            run_client(config, [response])

        metadata = context.exception.llm_metadata
        self.assertEqual(metadata["raw_response"], '{"criteria":')
        self.assertEqual(metadata["finish_reason"], "stop")
        self.assertEqual(len(metadata["attempts"]), 1)


class LlmClientConfigTest(unittest.TestCase):
    def test_env_overrides_model_budget_json_and_retry(self):
        with patch.dict(
            os.environ,
            {
                LLM_MODEL_ENV_VAR: "deepseek-chat",
                LLM_FALLBACK_MODEL_ENV_VAR: "deepseek-flash",
                LLM_MAX_OUTPUT_TOKENS_ENV_VAR: "16384",
                LLM_JSON_MODE_ENV_VAR: "false",
                LLM_RETRY_ON_LENGTH_ENV_VAR: "false",
            },
            clear=True,
        ):
            config = LlmFlowConfig.from_env("/tmp/logs")

        self.assertEqual(config.model, "deepseek-chat")
        self.assertEqual(config.fallback_model, "deepseek-flash")
        self.assertEqual(config.max_output_tokens, 16384)
        self.assertFalse(config.json_mode)
        self.assertFalse(config.retry_on_length)


if __name__ == "__main__":
    unittest.main()

