"""Configuration for the Laya interference pre-analysis flow."""

import logging
import os
from dataclasses import dataclass
from typing import Optional


LAYA_MODEL_ENV_VAR = "SMAT_LAYA_MODEL"
LAYA_THRESHOLD_ENV_VAR = "SMAT_LAYA_THRESHOLD"
LAYA_MAX_LEN_ENV_VAR = "SMAT_LAYA_MAX_LEN"
LAYA_LOG_DIR_ENV_VAR = "SMAT_LAYA_LOG_DIR"

DEFAULT_LAYA_MODEL = "english"
DEFAULT_LAYA_THRESHOLD = 0.5
DEFAULT_LAYA_MAX_LEN = 512


def _parse_float(value: Optional[str], default: float, name: str, minimum: float, maximum: float) -> float:
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
    if parsed <= 0:
        logging.warning(
            "Valor deve ser positivo para %s: %r. Usando o padrão: %s.",
            name,
            value,
            default,
        )
        return default
    return parsed


@dataclass(frozen=True)
class LayaFlowConfig:
    model: str = DEFAULT_LAYA_MODEL
    threshold: float = DEFAULT_LAYA_THRESHOLD
    max_len: int = DEFAULT_LAYA_MAX_LEN
    log_dir: Optional[str] = None

    @classmethod
    def from_env(cls, default_log_dir: str) -> "LayaFlowConfig":
        model = (os.environ.get(LAYA_MODEL_ENV_VAR) or DEFAULT_LAYA_MODEL).strip()
        threshold = _parse_float(
            os.environ.get(LAYA_THRESHOLD_ENV_VAR),
            DEFAULT_LAYA_THRESHOLD,
            LAYA_THRESHOLD_ENV_VAR,
            minimum=0.0,
            maximum=1.0,
        )
        max_len = _parse_positive_int(
            os.environ.get(LAYA_MAX_LEN_ENV_VAR),
            DEFAULT_LAYA_MAX_LEN,
            LAYA_MAX_LEN_ENV_VAR,
        )
        log_dir = os.environ.get(LAYA_LOG_DIR_ENV_VAR) or default_log_dir
        return cls(
            model=model or DEFAULT_LAYA_MODEL,
            threshold=threshold,
            max_len=max_len,
            log_dir=log_dir,
        )
