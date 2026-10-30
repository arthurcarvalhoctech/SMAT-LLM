"""Configuration for the LLM-based interference pre-analysis flow."""

import logging
import os
from dataclasses import dataclass
from typing import Optional


LLM_MODEL_ENV_VAR = "SMAT_LLM_INTERFERENCE_MODEL"
LLM_FALLBACK_MODEL_ENV_VAR = "SMAT_LLM_INTERFERENCE_FALLBACK_MODEL"
LLM_MAX_OUTPUT_TOKENS_ENV_VAR = "SMAT_LLM_INTERFERENCE_MAX_OUTPUT_TOKENS"
LLM_JSON_MODE_ENV_VAR = "SMAT_LLM_INTERFERENCE_JSON_MODE"
LLM_RETRY_ON_LENGTH_ENV_VAR = "SMAT_LLM_INTERFERENCE_RETRY_ON_LENGTH"
LLM_THRESHOLD_ENV_VAR = "SMAT_LLM_INTERFERENCE_THRESHOLD"
LLM_MAX_INPUT_CHARS_ENV_VAR = "SMAT_LLM_INTERFERENCE_MAX_INPUT_CHARS"
LLM_LOG_DIR_ENV_VAR = "SMAT_LLM_INTERFERENCE_LOG_DIR"

DEFAULT_LLM_THRESHOLD = 0.5
DEFAULT_LLM_MAX_INPUT_CHARS = 24000
DEFAULT_LLM_MAX_OUTPUT_TOKENS = 8192
DEFAULT_LLM_JSON_MODE = True
DEFAULT_LLM_RETRY_ON_LENGTH = True


def _parse_float(
    value: Optional[str], default: float, name: str, minimum: float, maximum: float
) -> float:
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError:
        logging.warning(
            "Valor inválido para %s: %r. Usando o padrão: %s.",
            name,
            value,
            default,
        )
        return default
    if parsed < minimum or parsed > maximum:
        logging.warning(
            "Valor fora do intervalo para %s: %r. Usando o padrão: %s.",
            name,
            value,
            default,
        )
        return default
    return parsed


def _parse_positive_int(value: Optional[str], default: int, name: str) -> int:
    if value is None or not value.strip():
        return default
    try:
        parsed = int(value)
    except ValueError:
        logging.warning(
            "Valor inválido para %s: %r. Usando o padrão: %s.",
            name,
            value,
            default,
        )
        return default
    if parsed < 256:
        logging.warning(
            "Valor deve ser pelo menos 256 para %s: %r. Usando o padrão: %s.",
            name,
            value,
            default,
        )
        return default
    return parsed


def _parse_bool(value: Optional[str], default: bool, name: str) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled", "sim"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled", "nao", "não"}:
        return False
    logging.warning(
        "Valor inválido para %s: %r. Usando o padrão: %s.",
        name,
        value,
        default,
    )
    return default


def _optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@dataclass(frozen=True)
class LlmFlowConfig:
    threshold: float = DEFAULT_LLM_THRESHOLD
    max_input_chars: int = DEFAULT_LLM_MAX_INPUT_CHARS
    log_dir: Optional[str] = None
    model: Optional[str] = None
    fallback_model: Optional[str] = None
    max_output_tokens: int = DEFAULT_LLM_MAX_OUTPUT_TOKENS
    json_mode: bool = DEFAULT_LLM_JSON_MODE
    retry_on_length: bool = DEFAULT_LLM_RETRY_ON_LENGTH
    model_key: str = "llm_interference"

    @classmethod
    def from_env(cls, default_log_dir: str) -> "LlmFlowConfig":
        threshold = _parse_float(
            os.environ.get(LLM_THRESHOLD_ENV_VAR),
            DEFAULT_LLM_THRESHOLD,
            LLM_THRESHOLD_ENV_VAR,
            minimum=0.0,
            maximum=1.0,
        )
        max_input_chars = _parse_positive_int(
            os.environ.get(LLM_MAX_INPUT_CHARS_ENV_VAR),
            DEFAULT_LLM_MAX_INPUT_CHARS,
            LLM_MAX_INPUT_CHARS_ENV_VAR,
        )
        max_output_tokens = _parse_positive_int(
            os.environ.get(LLM_MAX_OUTPUT_TOKENS_ENV_VAR),
            DEFAULT_LLM_MAX_OUTPUT_TOKENS,
            LLM_MAX_OUTPUT_TOKENS_ENV_VAR,
        )
        log_dir = os.environ.get(LLM_LOG_DIR_ENV_VAR) or default_log_dir
        return cls(
            threshold=threshold,
            max_input_chars=max_input_chars,
            log_dir=log_dir,
            model=_optional(os.environ.get(LLM_MODEL_ENV_VAR)),
            fallback_model=_optional(
                os.environ.get(LLM_FALLBACK_MODEL_ENV_VAR)
            ),
            max_output_tokens=max_output_tokens,
            json_mode=_parse_bool(
                os.environ.get(LLM_JSON_MODE_ENV_VAR),
                DEFAULT_LLM_JSON_MODE,
                LLM_JSON_MODE_ENV_VAR,
            ),
            retry_on_length=_parse_bool(
                os.environ.get(LLM_RETRY_ON_LENGTH_ENV_VAR),
                DEFAULT_LLM_RETRY_ON_LENGTH,
                LLM_RETRY_ON_LENGTH_ENV_VAR,
            ),
        )
