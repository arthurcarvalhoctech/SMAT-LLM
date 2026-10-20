import os
import unittest
from unittest.mock import patch

from nimrod.test_suite_generation.generators import llm_api as llm_api_module
from nimrod.test_suite_generation.generators.codellama_test_suite_generator import (
    CodellamaTestSuiteGenerator,
    GeminiApi,
)


class GeminiApiTest(unittest.TestCase):
    def _api(self) -> GeminiApi:
        return GeminiApi(
            api_key="dummy",
            timeout_seconds=300,
            temperature=0.7,
            seed=123,
            model="gemini-2.5-flash",
            max_output_tokens=4096,
        )

    def test_separates_system_instruction_and_roles(self) -> None:
        contents, system_instruction = self._api()._convert_messages_to_gemini_format(
            [
                {"role": "system", "content": "You are a Java expert."},
                {"role": "user", "content": "Generate tests."},
                {"role": "assistant", "content": "@Test public void test00() {}"},
            ]
        )

        self.assertEqual(system_instruction, "You are a Java expert.")
        self.assertEqual([content.role for content in contents], ["user", "model"])
        self.assertEqual(contents[0].parts[0].text, "Generate tests.")
        self.assertEqual(contents[1].parts[0].text, "@Test public void test00() {}")

    def test_retries_and_returns_the_last_successful_response(self) -> None:
        api = self._api()

        class FakeModels:
            def __init__(self) -> None:
                self.calls = 0

            def generate_content(self, **kwargs):
                self.calls += 1
                if self.calls < 3:
                    raise RuntimeError("temporary failure")
                return type("FakeResponse", (), {"text": "generated test"})()

        fake_models = FakeModels()
        api.client = type("FakeClient", (), {"models": fake_models})()

        with patch.object(llm_api_module, "sleep", return_value=None):
            result = api.generate_output([{"role": "user", "content": "hi"}])

        self.assertEqual(result["response"], "generated test")
        self.assertEqual(fake_models.calls, 3)

    def test_raises_after_all_attempts_fail(self) -> None:
        api = self._api()

        class FailingModels:
            def __init__(self) -> None:
                self.calls = 0

            def generate_content(self, **kwargs):
                self.calls += 1
                raise RuntimeError("permanent failure")

        fake_models = FailingModels()
        api.client = type("FakeClient", (), {"models": fake_models})()

        with patch.object(llm_api_module, "sleep", return_value=None):
            with self.assertRaises(RuntimeError):
                api.generate_output([{"role": "user", "content": "hi"}])

        self.assertEqual(fake_models.calls, GeminiApi.MAX_ATTEMPTS)

    def test_reads_seed_temperature_and_timeout_from_config(self) -> None:
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "dummy", "LLM_API_KEY": ""},
            clear=False,
        ):
            generator = CodellamaTestSuiteGenerator(
                object(),
                "gemini",
                {
                    "provider": "gemini",
                    "model": "gemini-2.5-flash",
                    "temperature": 0.7,
                    "seed": 123,
                    "timeout_seconds": 300,
                    "max_output_tokens": 4096,
                },
            )
            generator._ensure_api_initialized()

        self.assertEqual(generator.api.seed, 123)
        self.assertEqual(generator.api.temperature, 0.7)
        self.assertEqual(generator.api.timeout_seconds, 300)
        self.assertEqual(generator.api.max_output_tokens, 4096)
        self.assertIn("_T70_S123", generator._generate_config_suffix())

    def test_requires_an_api_key(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "gemini",
                "LLM_API_KEY": "",
                "GEMINI_API_KEY": "",
                "GOOGLE_API_KEY": "",
            },
            clear=False,
        ):
            generator = CodellamaTestSuiteGenerator(object(), "gemini", {"api_key": ""})
            with self.assertRaises(ValueError):
                generator._ensure_api_initialized()


if __name__ == "__main__":
    unittest.main()
