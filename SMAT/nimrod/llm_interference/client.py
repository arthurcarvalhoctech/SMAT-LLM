"""LLM provider adapter for the interference analysis flow.

This client adds flow-specific model/output controls on top of SMAT's existing
provider abstraction:

- ``SMAT_LLM_INTERFERENCE_MODEL`` / fallback model;
- ``SMAT_LLM_INTERFERENCE_MAX_OUTPUT_TOKENS``;
- OpenAI-compatible JSON mode;
- one retry when the provider reports ``finish_reason=length``;
- structured error metadata (finish reason, usage, raw response, attempts).
"""

import logging
from dataclasses import replace
from typing import Any, Dict, List, Optional, Protocol, Tuple

from nimrod.llm_interference.config import LlmFlowConfig
from nimrod.llm_interference.criteria import (
    LlmResponseError,
    build_messages,
    parse_llm_analysis,
)


class LlmUnavailableError(RuntimeError):
    """Raised when the configured LLM provider cannot be used."""


class LlmClient(Protocol):
    def analyze(self, state: Any) -> Dict[str, Any]:
        ...


class ApiLlmClient:
    """Lazy adapter over SMAT's provider-agnostic LLM clients."""

    def __init__(self, config: LlmFlowConfig) -> None:
        self.config = config
        self._resolved = None
        self._load_error: Optional[str] = None

    def _resolve(self):
        if self._resolved is not None:
            return self._resolved
        if self._load_error is not None:
            raise LlmUnavailableError(self._load_error)

        try:
            from nimrod.test_suite_generation.generators.llm_config import (
                resolve_llm_config,
            )

            self._resolved = resolve_llm_config(
                model_key=self.config.model_key
            )
            return self._resolved
        except Exception as error:
            self._load_error = (
                "O provedor LLM não está disponível. Configure LLM_PROVIDER/"
                f"LLM_MODEL e a API key correspondente. Detalhe: {error}"
            )
            raise LlmUnavailableError(self._load_error) from error

    def describe(self) -> Dict[str, Any]:
        try:
            resolved = self._resolve()
            return {
                "provider": resolved.provider,
                "api_model": resolved.model,
                "model": self.config.model or resolved.model,
                "fallback_model": self.config.fallback_model,
                "api_kind": resolved.api_kind,
                "base_url": resolved.base_url,
                "temperature": resolved.temperature,
                "timeout_seconds": resolved.timeout_seconds,
                "max_output_tokens": self.config.max_output_tokens,
                "json_mode": self.config.json_mode,
                "retry_on_length": self.config.retry_on_length,
            }
        except Exception as error:
            return {"error": str(error)}

    def _make_api(self, model: str, max_output_tokens: int):
        resolved = self._resolve()
        effective_model = model or resolved.model
        effective_tokens = max_output_tokens or resolved.max_output_tokens

        try:
            from nimrod.test_suite_generation.generators.llm_api import (
                create_llm_api,
            )

            api_config = replace(
                resolved,
                model=effective_model,
                max_output_tokens=effective_tokens,
            )
            api = create_llm_api(api_config)
        except LlmUnavailableError:
            raise
        except Exception as error:
            raise LlmUnavailableError(
                "Não foi possível criar o cliente LLM para "
                f"model={effective_model}, max_output_tokens={effective_tokens}: "
                f"{error}"
            ) from error

        if self.config.json_mode and resolved.api_kind == "openai":
            # OpenAI-compatible providers (DeepSeek, OpenAI, Groq, ...).
            api.response_format = {"type": "json_object"}

        return api, api_config

    def _metadata(
        self,
        attempt: int,
        model: str,
        max_output_tokens: int,
        finish_reason: Optional[str],
        usage: Any,
        raw_response: str,
        reasoning_content: Optional[str],
    ) -> Dict[str, Any]:
        reasoning = reasoning_content or ""
        return {
            "attempt": attempt,
            "model": model,
            "max_output_tokens": max_output_tokens,
            "finish_reason": finish_reason,
            "usage": usage if isinstance(usage, dict) else {},
            "raw_response": raw_response,
            "raw_response_length": len(raw_response),
            "raw_response_preview": raw_response[:4000],
            "reasoning_content_preview": reasoning[:2000],
            "reasoning_content_length": len(reasoning),
        }

    def _metadata_from_error(
        self,
        error: Exception,
        attempt: int,
        model: str,
        max_output_tokens: int,
    ) -> Dict[str, Any]:
        return self._metadata(
            attempt=attempt,
            model=model,
            max_output_tokens=max_output_tokens,
            finish_reason=getattr(error, "finish_reason", None),
            usage=getattr(error, "usage", None),
            raw_response="",
            reasoning_content=getattr(error, "reasoning_content", None),
        ) | {
            "error": str(error),
        }

    def _should_retry_length(self, metadata: Dict[str, Any]) -> bool:
        if not self.config.retry_on_length:
            return False
        return metadata.get("finish_reason") == "length"

    def _next_attempt(
        self, model: str, max_output_tokens: int
    ) -> Tuple[str, int]:
        if (
            self.config.fallback_model
            and self.config.fallback_model != model
        ):
            return self.config.fallback_model, max_output_tokens

        return model, min(max_output_tokens * 2, 32768)

    def _error_context(
        self,
        metadata: Dict[str, Any],
        attempts: List[Dict[str, Any]],
        resolved,
        model: str,
    ) -> Dict[str, Any]:
        return {
            "provider": resolved.provider,
            "model": model,
            "api_kind": resolved.api_kind,
            "base_url": resolved.base_url,
            "configured_model": self.config.model,
            "fallback_model": self.config.fallback_model,
            "max_output_tokens": self.config.max_output_tokens,
            "json_mode": self.config.json_mode,
            "retry_on_length": self.config.retry_on_length,
            "finish_reason": metadata.get("finish_reason"),
            "usage": metadata.get("usage", {}),
            "raw_response": metadata.get("raw_response", ""),
            "reasoning_content_preview": metadata.get(
                "reasoning_content_preview", ""
            ),
            "attempts": attempts,
        }

    def analyze(self, state: Any) -> Dict[str, Any]:
        messages = build_messages(state, self.config.max_input_chars)
        resolved = self._resolve()
        model = self.config.model or resolved.model
        max_output_tokens = (
            self.config.max_output_tokens or resolved.max_output_tokens
        )
        max_attempts = 2 if self.config.retry_on_length else 1
        attempts: List[Dict[str, Any]] = []

        for attempt in range(1, max_attempts + 1):
            try:
                api, api_config = self._make_api(model, max_output_tokens)
                raw_result = api.generate_output(messages)
            except LlmUnavailableError:
                raise
            except Exception as error:
                metadata = self._metadata_from_error(
                    error, attempt, model, max_output_tokens
                )
                attempts.append(metadata)
                if (
                    self._should_retry_length(metadata)
                    and attempt < max_attempts
                ):
                    model, max_output_tokens = self._next_attempt(
                        model, max_output_tokens
                    )
                    logging.warning(
                        "LLM response hit the output limit; retrying with "
                        "model=%s max_output_tokens=%s.",
                        model,
                        max_output_tokens,
                    )
                    continue

                error.llm_metadata = self._error_context(
                    metadata, attempts, resolved, model
                )
                raise

            raw_response = str(raw_result.get("response", "") or "")
            finish_reason = raw_result.get("finish_reason")
            usage = raw_result.get("usage", {})
            reasoning_content = raw_result.get("reasoning_content")
            metadata = self._metadata(
                attempt=attempt,
                model=api_config.model,
                max_output_tokens=max_output_tokens,
                finish_reason=finish_reason,
                usage=usage,
                raw_response=raw_response,
                reasoning_content=reasoning_content,
            )
            attempts.append(metadata)

            try:
                analysis = parse_llm_analysis(
                    raw_response, self.config.threshold
                )
            except LlmResponseError as error:
                if (
                    self._should_retry_length(metadata)
                    and attempt < max_attempts
                ):
                    model, max_output_tokens = self._next_attempt(
                        model, max_output_tokens
                    )
                    logging.warning(
                        "LLM JSON was incomplete/truncated; retrying with "
                        "model=%s max_output_tokens=%s.",
                        model,
                        max_output_tokens,
                    )
                    continue

                error.llm_metadata = self._error_context(
                    metadata, attempts, resolved, model
                )
                raise

            return {
                "analysis": analysis,
                "raw_response": raw_response,
                "provider": resolved.provider,
                "model": api_config.model,
                "routing": {
                    "provider": resolved.provider,
                    "model": api_config.model,
                    "api_kind": resolved.api_kind,
                    "base_url": resolved.base_url,
                    "json_mode": self.config.json_mode,
                    "max_output_tokens": max_output_tokens,
                    "attempts": len(attempts),
                },
                "usage": usage if isinstance(usage, dict) else {},
                "finish_reason": finish_reason,
                "attempts": attempts,
            }

        raise LlmUnavailableError("LLM analysis exhausted all attempts.")
