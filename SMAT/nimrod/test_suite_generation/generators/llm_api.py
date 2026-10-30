"""Provider-agnostic LLM clients used by the test suite generator."""

import json
import logging
from abc import ABC, abstractmethod
from time import sleep, time
from typing import Any, Dict, List, Optional

import requests

from nimrod.test_suite_generation.generators.llm_config import (
    LlmConfig,
    PROVIDER_KEY_ENVS,
    api_key_required,
)


class LlmApi(ABC):
    MAX_ATTEMPTS = 3

    def __init__(
        self,
        api_key: Optional[str],
        timeout_seconds: int,
        temperature: float,
        seed: int,
        model: str,
        max_output_tokens: int = 8192,
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.seed = seed
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.base_url = base_url
        self.branch: Optional[str] = None

    def set_branch(self, branch: str) -> None:
        self.branch = branch

    def _with_retry(self, operation, description: str):
        last_error: Optional[Exception] = None
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            start_time = time()
            try:
                result = operation()
                return result, int((time() - start_time) * 1_000_000_000)
            except Exception as error:
                last_error = error
                if attempt == self.MAX_ATTEMPTS:
                    break
                wait_seconds = 2 ** (attempt - 1)
                logging.warning(
                    "%s failed (attempt %d/%d): %s. Retrying in %ds.",
                    description,
                    attempt,
                    self.MAX_ATTEMPTS,
                    error,
                    wait_seconds,
                )
                sleep(wait_seconds)

        final_error = RuntimeError(
            f"{description} failed after {self.MAX_ATTEMPTS} attempts: {last_error}"
        )
        for attribute in (
            "finish_reason",
            "reasoning_content",
            "usage",
            "raw_data",
        ):
            if hasattr(last_error, attribute):
                setattr(final_error, attribute, getattr(last_error, attribute))
        raise final_error from last_error

    @abstractmethod
    def generate_output(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        raise NotImplementedError


class GeminiApi(LlmApi):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self.api_key:
            raise ValueError(
                "Gemini API key not configured. Set GEMINI_API_KEY or LLM_API_KEY."
            )

        from google import genai
        from google.genai import types as genai_types

        self._genai_types = genai_types
        self.client = genai.Client(
            api_key=self.api_key,
            http_options=genai_types.HttpOptions(timeout=self.timeout_seconds * 1000),
        )
        logging.debug(
            "Gemini API initialized with model=%s, temperature=%s, seed=%s, timeout=%ss",
            self.model,
            self.temperature,
            self.seed,
            self.timeout_seconds,
        )

    def generate_output(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        contents, system_instruction = self._convert_messages_to_gemini_format(messages)
        if not contents:
            raise ValueError("No user/assistant messages to send to Gemini.")

        generation_config = self._genai_types.GenerateContentConfig(
            temperature=self.temperature,
            seed=self.seed,
            max_output_tokens=self.max_output_tokens,
            system_instruction=system_instruction or None,
        )

        def call() -> str:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=generation_config,
            )
            response_text = getattr(response, "text", None)
            return response_text or str(response)

        response_text, duration = self._with_retry(call, "Gemini request")
        return {"response": response_text, "total_duration": duration}

    def _convert_messages_to_gemini_format(
        self, messages: List[Dict[str, str]]
    ) -> tuple[List[Any], str]:
        genai_types = self._genai_types
        system_parts: List[str] = []
        contents: List[Any] = []

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")

            if role == "system":
                system_parts.append(content)
            elif role == "assistant":
                contents.append(
                    genai_types.Content(
                        role="model",
                        parts=[genai_types.Part(text=content)],
                    )
                )
            else:
                contents.append(
                    genai_types.Content(
                        role="user",
                        parts=[genai_types.Part(text=content)],
                    )
                )

        return contents, "\n\n".join(system_parts)


class OpenAICompatibleApi(LlmApi):
    """Client for OpenAI-compatible ``/chat/completions`` endpoints."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        base_url = (self.base_url or "").rstrip("/")
        if not base_url:
            raise ValueError(
                "Base URL not configured. Set LLM_BASE_URL (for example "
                "https://api.deepseek.com or https://api.openai.com/v1)."
            )
        if base_url.endswith("/chat/completions"):
            self.endpoint = base_url
        else:
            self.endpoint = f"{base_url}/chat/completions"

        logging.debug(
            "OpenAI-compatible API initialized with endpoint=%s, model=%s, seed=%s",
            self.endpoint,
            self.model,
            self.seed,
        )

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
            "stream": False,
        }
        if self.seed is not None:
            payload["seed"] = self.seed
        response_format = getattr(self, "response_format", None)
        if response_format:
            payload["response_format"] = response_format
        return payload

    def generate_output(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        payload = self._payload(messages)
        call_metadata: Dict[str, Any] = {}

        def call() -> str:
            response = requests.post(
                self.endpoint,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout_seconds,
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"HTTP {response.status_code}: {response.text[:1000]}"
                )

            data = response.json()
            choice = data["choices"][0]
            message = choice.get("message", {}) or {}
            content = message.get("content")
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict)
                )
            if content is None:
                content = choice.get("text", "")

            finish_reason = choice.get("finish_reason")
            reasoning_content = message.get("reasoning_content")
            usage = data.get("usage", {})
            call_metadata.update(
                {
                    "finish_reason": finish_reason,
                    "reasoning_content": reasoning_content,
                    "usage": usage,
                }
            )

            if not content:
                error = RuntimeError(f"Empty response from provider: {data}")
                error.finish_reason = finish_reason
                error.reasoning_content = reasoning_content
                error.usage = usage
                error.raw_data = data
                raise error
            return content

        content, duration = self._with_retry(call, "OpenAI-compatible request")
        return {
            "response": content,
            "total_duration": duration,
            **call_metadata,
        }


class OllamaApi(LlmApi):
    """Client for Ollama's native ``/api/chat`` endpoint."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        base_url = (self.base_url or "http://localhost:11434/api/chat").rstrip("/")
        if base_url.endswith("/api/chat"):
            self.endpoint = base_url
        elif base_url.endswith("/api"):
            self.endpoint = f"{base_url}/chat"
        else:
            self.endpoint = f"{base_url}/api/chat"

        logging.debug(
            "Ollama API initialized with endpoint=%s, model=%s, seed=%s",
            self.endpoint,
            self.model,
            self.seed,
        )

    def _payload(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "seed": self.seed,
                "num_predict": self.max_output_tokens,
            },
        }

    def generate_output(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        payload = self._payload(messages)

        def call() -> str:
            response = requests.post(
                self.endpoint,
                json=payload,
                timeout=self.timeout_seconds,
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"HTTP {response.status_code}: {response.text[:1000]}"
                )

            data = response.json()
            content = data.get("message", {}).get("content")
            if content is None:
                content = data.get("response", "")
            if not content:
                raise RuntimeError(f"Empty response from Ollama: {data}")
            return content

        content, duration = self._with_retry(call, "Ollama request")
        return {"response": content, "total_duration": duration}


class AnthropicApi(LlmApi):
    """Client for Anthropic's native Messages API."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self.api_key:
            raise ValueError(
                "Anthropic API key not configured. Set ANTHROPIC_API_KEY or LLM_API_KEY."
            )

        base_url = (self.base_url or "https://api.anthropic.com/v1/messages").rstrip("/")
        if base_url.endswith("/messages"):
            self.endpoint = base_url
        elif base_url.endswith("/v1"):
            self.endpoint = f"{base_url}/messages"
        else:
            self.endpoint = f"{base_url}/v1/messages"

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
        }

    def _payload(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        system_parts = [
            message.get("content", "")
            for message in messages
            if message.get("role") == "system"
        ]
        chat_messages = [
            message for message in messages if message.get("role") != "system"
        ]
        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "messages": chat_messages,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        return payload

    def generate_output(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        payload = self._payload(messages)

        def call() -> str:
            response = requests.post(
                self.endpoint,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout_seconds,
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"HTTP {response.status_code}: {response.text[:1000]}"
                )

            data = response.json()
            blocks = data.get("content", [])
            content = "".join(
                block.get("text", "")
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )
            if not content:
                raise RuntimeError(f"Empty response from Anthropic: {data}")
            return content

        content, duration = self._with_retry(call, "Anthropic request")
        return {"response": content, "total_duration": duration}


def create_llm_api(config: LlmConfig) -> LlmApi:
    """Create the concrete client for the configured provider."""
    if api_key_required(config.provider) and not config.api_key:
        env_names = PROVIDER_KEY_ENVS.get(config.provider, ())
        hint = ", ".join(env_names) if env_names else "LLM_API_KEY"
        raise ValueError(
            f"API key not configured for provider '{config.provider}'. "
            f"Set LLM_API_KEY or one of: {hint}."
        )

    kwargs = {
        "api_key": config.api_key,
        "timeout_seconds": config.timeout_seconds,
        "temperature": config.temperature,
        "seed": config.seed,
        "model": config.model,
        "max_output_tokens": config.max_output_tokens,
        "base_url": config.base_url,
    }

    if config.api_kind == "gemini":
        return GeminiApi(**kwargs)
    if config.api_kind == "ollama":
        return OllamaApi(**kwargs)
    if config.api_kind == "anthropic":
        return AnthropicApi(**kwargs)
    return OpenAICompatibleApi(**kwargs)
