"""Configuration for the Laya interference pre-analysis flow."""

import logging
import math
import os
from dataclasses import dataclass, field
from typing import Dict, Optional

from nimrod.laya_interference.criteria import CRITERIA, QUESTION_FORMATS


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
    if not math.isfinite(parsed) or parsed < minimum or parsed > maximum:
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
    question_format: str = "noul"
    criterion_thresholds: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.question_format not in QUESTION_FORMATS:
            raise ValueError(f"Invalid question_format: {self.question_format}")
        if not isinstance(self.max_len, int) or isinstance(self.max_len, bool) or self.max_len <= 0:
            raise ValueError("max_len must be a positive integer")
        if set(self.criterion_thresholds) - {c.id for c in CRITERIA}:
            raise ValueError("Unknown criterion threshold")
        for value in [self.threshold, *self.criterion_thresholds.values()]:
            if isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Thresholds must be finite numbers in [0, 1]")

    def threshold_for(self, criterion_id: str) -> float:
        return self.criterion_thresholds.get(criterion_id, self.threshold)

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
        question_format = os.environ.get("SMAT_LAYA_QUESTION_FORMAT", "noul").strip() or "noul"
        if question_format not in QUESTION_FORMATS:
            logging.warning("Invalid SMAT_LAYA_QUESTION_FORMAT: %r; using noul", question_format)
            question_format = "noul"
        criterion_thresholds = {}
        for criterion in CRITERIA:
            name = f"SMAT_LAYA_THRESHOLD_C{criterion.number}"
            if os.environ.get(name, "").strip():
                criterion_thresholds[criterion.id] = _parse_float(
                    os.environ[name], threshold, name, 0.0, 1.0
                )
        return cls(
            model=model or DEFAULT_LAYA_MODEL,
            threshold=threshold,
            max_len=max_len,
            log_dir=log_dir,
            question_format=question_format,
            criterion_thresholds=criterion_thresholds,
        )
