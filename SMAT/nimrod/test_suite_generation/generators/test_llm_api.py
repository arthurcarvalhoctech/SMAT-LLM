import unittest
from unittest.mock import patch

import requests

from nimrod.test_suite_generation.generators import llm_api as llm_api_module
from nimrod.test_suite_generation.generators.llm_api import (
    AnthropicApi,
    GeminiApi,
    OllamaApi,
    OpenAICompatibleApi,
    create_llm_api,
)
from nimrod.test_suite_generation.generators.llm_config import LlmConfig


class FakeResponse:
    def __init__(self, payload, status_code=200, text="") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload


def openai_response(content: str) -> FakeResponse:
    return FakeResponse({"choices": [{"message": {"content": content}}]})


class OpenAICompatibleApiTest(unittest.TestCase):
    def _api(self) -> OpenAICompatibleApi:
        return OpenAICompatibleApi(
            api_key="secret",
            timeout_seconds=30,
            temperature=0.1,
            seed=7,
            model="deepseek-flash",
            max_output_tokens=1024,
            base_url="https://api.deepseek.com",
        )

    def test_builds_endpoint_headers_and_payload(self) -> None:
        api = self._api()
        self.assertEqual(
            api.endpoint, "https://api.deepseek.com/chat/completions"
        )

        with patch.object(
            llm_api_module.requests, "post", return_value=openai_response("ok")
        ) as post:
            result = api.generate_output(
                [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "user"},
                ]
            )

        self.assertEqual(result["response"], "ok")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.deepseek.com/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")
        self.assertEqual(kwargs["json"]["model"], "deepseek-flash")
        self.assertEqual(kwargs["json"]["messages"][1]["content"], "user")
        self.assertEqual(kwargs["json"]["temperature"], 0.1)
        self.assertEqual(kwargs["json"]["seed"], 7)
        self.assertEqual(kwargs["json"]["max_tokens"], 1024)

    def test_retries_transient_failures(self) -> None:
        api = self._api()
        side_effect = [
            requests.exceptions.RequestException("temporary"),
            openai_response("ok"),
        ]

        with patch.object(
            llm_api_module.requests, "post", side_effect=side_effect
        ) as post, patch.object(llm_api_module, "sleep", return_value=None):
            result = api.generate_output([{"role": "user", "content": "hi"}])

        self.assertEqual(result["response"], "ok")
        self.assertEqual(post.call_count, 2)

    def test_raises_after_repeated_http_errors(self) -> None:
        api = self._api()
        error = FakeResponse({}, status_code=400, text="bad request")

        with patch.object(
            llm_api_module.requests, "post", return_value=error
        ) as post, patch.object(llm_api_module, "sleep", return_value=None):
            with self.assertRaises(RuntimeError):
                api.generate_output([{"role": "user", "content": "hi"}])

        self.assertEqual(post.call_count, 3)

    def test_accepts_a_full_chat_completions_url(self) -> None:
        api = OpenAICompatibleApi(
            api_key="secret",
            timeout_seconds=30,
            temperature=0.0,
            seed=1,
            model="model",
            base_url="https://example.test/v1/chat/completions",
        )

        self.assertEqual(
            api.endpoint, "https://example.test/v1/chat/completions"
        )


class OllamaApiTest(unittest.TestCase):
    def test_builds_endpoint_and_options(self) -> None:
        api = OllamaApi(
            api_key=None,
            timeout_seconds=30,
            temperature=0.0,
            seed=42,
            model="llama3.1:8b",
            max_output_tokens=512,
            base_url="http://localhost:11434",
        )

        self.assertEqual(api.endpoint, "http://localhost:11434/api/chat")

        response = FakeResponse({"message": {"content": "ok"}})
        with patch.object(
            llm_api_module.requests, "post", return_value=response
        ) as post:
            result = api.generate_output([{"role": "user", "content": "hi"}])

        self.assertEqual(result["response"], "ok")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "llama3.1:8b")
        self.assertEqual(payload["options"]["seed"], 42)
        self.assertEqual(payload["options"]["num_predict"], 512)


class AnthropicApiTest(unittest.TestCase):
    def test_separates_system_message(self) -> None:
        api = AnthropicApi(
            api_key="secret",
            timeout_seconds=30,
            temperature=0.0,
            seed=42,
            model="claude-3-5-sonnet-latest",
            max_output_tokens=512,
            base_url="https://api.anthropic.com",
        )

        self.assertEqual(
            api.endpoint, "https://api.anthropic.com/v1/messages"
        )

        response = FakeResponse(
            {"content": [{"type": "text", "text": "ok"}]}
        )
        with patch.object(
            llm_api_module.requests, "post", return_value=response
        ) as post:
            result = api.generate_output(
                [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "user"},
                ]
            )

        self.assertEqual(result["response"], "ok")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["system"], "system")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "user"}])
        self.assertEqual(
            post.call_args.kwargs["headers"]["x-api-key"], "secret"
        )


class CreateLlmApiTest(unittest.TestCase):
    def test_selects_the_provider_client(self) -> None:
        deepseek = LlmConfig(
            provider="deepseek",
            model="deepseek-flash",
            api_key="secret",
            base_url="https://api.deepseek.com",
        )
        ollama = LlmConfig(
            provider="ollama",
            model="llama3.1:8b",
            api_key=None,
            base_url="http://localhost:11434/api/chat",
        )
        gemini = LlmConfig(
            provider="gemini",
            model="gemini-2.5-flash",
            api_key="secret",
            base_url=None,
        )

        self.assertIsInstance(create_llm_api(deepseek), OpenAICompatibleApi)
        self.assertIsInstance(create_llm_api(ollama), OllamaApi)
        self.assertIsInstance(create_llm_api(gemini), GeminiApi)

    def test_rejects_missing_key_for_remote_providers(self) -> None:
        config = LlmConfig(
            provider="deepseek",
            model="deepseek-flash",
            api_key=None,
            base_url="https://api.deepseek.com",
        )

        with self.assertRaises(ValueError):
            create_llm_api(config)


if __name__ == "__main__":
    unittest.main()
