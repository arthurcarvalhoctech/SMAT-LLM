import os
import unittest
from unittest.mock import patch

from nimrod.test_suite_generation.generators.llm_config import (
    api_kind,
    infer_provider_from_env,
    llm_env_configured,
    resolve_llm_config,
)


class LlmConfigTest(unittest.TestCase):
    def test_deepseek_from_environment(self) -> None:
        env = {
            "LLM_PROVIDER": "deepseek",
            "LLM_MODEL": "deepseek-flash",
            "DEEPSEEK_API_KEY": "secret",
        }
        with patch.dict(os.environ, env, clear=True):
            config = resolve_llm_config("deepseek", {})

        self.assertEqual(config.provider, "deepseek")
        self.assertEqual(config.api_kind, "openai")
        self.assertEqual(config.model, "deepseek-flash")
        self.assertEqual(config.base_url, "https://api.deepseek.com")
        self.assertEqual(config.api_key, "secret")
        self.assertEqual(config.output_label, "deepseek")

    def test_environment_overrides_json_config(self) -> None:
        env = {
            "LLM_PROVIDER": "openai",
            "LLM_MODEL": "gpt-4o-mini",
            "OPENAI_API_KEY": "secret",
            "LLM_TEMPERATURE": "0.2",
            "LLM_SEED": "123",
        }
        json_config = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "temperature": 0.7,
            "seed": 42,
        }
        with patch.dict(os.environ, env, clear=True):
            config = resolve_llm_config("gemini", json_config)

        self.assertEqual(config.provider, "openai")
        self.assertEqual(config.model, "gpt-4o-mini")
        self.assertEqual(config.base_url, "https://api.openai.com/v1")
        self.assertEqual(config.api_key, "secret")
        self.assertEqual(config.temperature, 0.2)
        self.assertEqual(config.seed, 123)

    def test_ollama_does_not_require_a_key(self) -> None:
        env = {"LLM_PROVIDER": "ollama", "LLM_MODEL": "llama3.1:8b"}
        with patch.dict(os.environ, env, clear=True):
            config = resolve_llm_config("ollama", {})

        self.assertEqual(config.api_kind, "ollama")
        self.assertEqual(config.base_url, "http://localhost:11434/api/chat")
        self.assertIsNone(config.api_key)

    def test_infers_provider_from_a_provider_specific_key(self) -> None:
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=True):
            self.assertTrue(llm_env_configured())
            self.assertEqual(infer_provider_from_env(), "deepseek")
            config = resolve_llm_config("llm", {})

        self.assertEqual(config.provider, "deepseek")
        self.assertEqual(config.model, "deepseek-flash")

    def test_prompt_keys_from_environment(self) -> None:
        env = {
            "LLM_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "secret",
            "LLM_PROMPT_KEYS": "prompt1, prompt3",
        }
        with patch.dict(os.environ, env, clear=True):
            config = resolve_llm_config("deepseek", {})

        self.assertEqual(config.prompt_keys, ["prompt1", "prompt3"])

    def test_falls_back_to_json_config_without_environment(self) -> None:
        json_config = {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "api_key": "secret",
            "temperature": 0.7,
        }
        with patch.dict(os.environ, {}, clear=True):
            config = resolve_llm_config("gemini", json_config)

        self.assertEqual(config.provider, "gemini")
        self.assertEqual(config.api_kind, "gemini")
        self.assertEqual(config.api_key, "secret")
        self.assertEqual(config.temperature, 0.7)

    def test_provider_aliases_and_sanitized_label(self) -> None:
        self.assertEqual(api_kind("google"), "gemini")
        self.assertEqual(api_kind("openai-compatible"), "openai")
        self.assertEqual(api_kind("claude"), "anthropic")

        with patch.dict(
            os.environ,
            {
                "LLM_PROVIDER": "deepseek",
                "LLM_API_KEY": "secret",
                "LLM_MODEL_KEY": "deepseek/v4 flash",
            },
            clear=True,
        ):
            config = resolve_llm_config("llm", {})

        self.assertEqual(config.output_label, "deepseek_v4_flash")


if __name__ == "__main__":
    unittest.main()
