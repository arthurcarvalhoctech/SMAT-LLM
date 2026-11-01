"""Configuration for the Laya interference pre-analysis flow."""

import logging
import os
from dataclasses import dataclass
from typing import Optional, Tuple


LAYA_MODEL_ENV_VAR = "SMAT_LAYA_MODEL"
LAYA_THRESHOLD_ENV_VAR = "SMAT_LAYA_THRESHOLD"
LAYA_MAX_LEN_ENV_VAR = "SMAT_LAYA_MAX_LEN"
LAYA_LOG_DIR_ENV_VAR = "SMAT_LAYA_LOG_DIR"
LAYA_DECISION_RULE_ENV_VAR = "SMAT_LAYA_DECISION_RULE"
LAYA_STATE_FORMAT_ENV_VAR = "SMAT_LAYA_STATE_FORMAT"
LAYA_THRESHOLDS_ENV_VAR = "SMAT_LAYA_THRESHOLDS"
LAYA_WITNESS_ENV_VAR = "SMAT_LAYA_WITNESS"
LAYA_WITNESS_TWO_STAGE_ENV_VAR = "SMAT_LAYA_WITNESS_TWO_STAGE"
LAYA_NEGATIVE_INSTRUCTIONS_ENV_VAR = "SMAT_LAYA_NEGATIVE_INSTRUCTIONS"
LAYA_DIAGNOSTIC_QUESTIONS_ENV_VAR = "SMAT_LAYA_DIAGNOSTIC_QUESTIONS"
LAYA_ALLOW_BASELINE_WITH_WITNESS_ENV_VAR = (
    "SMAT_LAYA_ALLOW_BASELINE_WITH_WITNESS"
)

DEFAULT_LAYA_MODEL = "english"
DEFAULT_LAYA_THRESHOLD = 0.5
DEFAULT_LAYA_MAX_LEN = 512
DEFAULT_DECISION_RULE = "baseline"
DEFAULT_STATE_FORMAT = "json"
DEFAULT_WITNESS = False
DEFAULT_WITNESS_TWO_STAGE = False
VALID_DECISION_RULES = ("baseline", "consistent", "conservative")
VALID_STATE_FORMATS = ("json", "compact")
BASELINE_RULE = "baseline"


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


def _parse_thresholds(
    value: Optional[str],
    default: float,
) -> Tuple[float, float, float]:
    """Parse ``SMAT_LAYA_THRESHOLDS`` as three probabilities (C1,C2,C3)."""
    if value is None or not value.strip():
        return (default, default, default)
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        logging.warning(
            "SMAT_LAYA_THRESHOLDS deve ter três valores (C1,C2,C3); usando %s.",
            default,
        )
        return (default, default, default)
    parsed = []
    for part in parts:
        try:
            number = float(part)
        except ValueError:
            logging.warning(
                "Valor inválido em SMAT_LAYA_THRESHOLDS: %r; usando %s.",
                part,
                default,
            )
            return (default, default, default)
        if number < 0.0 or number > 1.0:
            logging.warning(
                "Threshold fora de [0,1] em SMAT_LAYA_THRESHOLDS: %r; usando %s.",
                part,
                default,
            )
            return (default, default, default)
        parsed.append(number)
    return (parsed[0], parsed[1], parsed[2])


def _parse_choice(
    value: Optional[str],
    default: str,
    valid: Tuple[str, ...],
    name: str,
) -> str:
    candidate = (value or default).strip().lower()
    if candidate not in valid:
        logging.warning(
            "Valor inválido para %s: %r. Usando o padrão: %s.",
            name,
            value,
            default,
        )
        return default
    return candidate


def _parse_bool(value: Optional[str], default: bool, name: str) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    logging.warning(
        "Valor inválido para %s: %r. Usando o padrão: %s.",
        name,
        value,
        default,
    )
    return default


@dataclass(frozen=True)
class LayaFlowConfig:
    model: str = DEFAULT_LAYA_MODEL
    threshold: float = DEFAULT_LAYA_THRESHOLD
    max_len: int = DEFAULT_LAYA_MAX_LEN
    log_dir: Optional[str] = None
    decision_rule: str = DEFAULT_DECISION_RULE
    state_format: str = DEFAULT_STATE_FORMAT
    witness: bool = DEFAULT_WITNESS
    witness_two_stage: bool = DEFAULT_WITNESS_TWO_STAGE
    # Reproduce pre-coercion runs: keep baseline even if witness is enabled.
    allow_baseline_with_witness: bool = False
    # Append the per-criterion negative instructions to the criteria prompts.
    negative_instructions: bool = True
    # Optional descriptive questions not used by the decision rules.
    diagnostic_questions: bool = False
    criterion_thresholds: Tuple[float, float, float] = (
        DEFAULT_LAYA_THRESHOLD,
        DEFAULT_LAYA_THRESHOLD,
        DEFAULT_LAYA_THRESHOLD,
    )

    def __post_init__(self) -> None:
        # The baseline rule ignores the witness entirely. Enabling a witness
        # with baseline would only skip the criteria call on ``none`` and
        # otherwise leave the permissive decision untouched.
        if self.witness_two_stage and not self.witness:
            object.__setattr__(self, "witness", True)
            logging.warning(
                "SMAT_LAYA_WITNESS_TWO_STAGE=true requires witness; enabling "
                "SMAT_LAYA_WITNESS automatically."
            )
        if (
            (self.witness or self.witness_two_stage)
            and self.decision_rule == BASELINE_RULE
            and not self.allow_baseline_with_witness
        ):
            object.__setattr__(self, "decision_rule", "consistent")
            logging.warning(
                "decision_rule=baseline ignores the witness; using "
                "decision_rule=consistent because witness/two-stage is enabled."
            )

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
        decision_rule = _parse_choice(
            os.environ.get(LAYA_DECISION_RULE_ENV_VAR),
            DEFAULT_DECISION_RULE,
            VALID_DECISION_RULES,
            LAYA_DECISION_RULE_ENV_VAR,
        )
        state_format = _parse_choice(
            os.environ.get(LAYA_STATE_FORMAT_ENV_VAR),
            DEFAULT_STATE_FORMAT,
            VALID_STATE_FORMATS,
            LAYA_STATE_FORMAT_ENV_VAR,
        )
        criterion_thresholds = _parse_thresholds(
            os.environ.get(LAYA_THRESHOLDS_ENV_VAR),
            threshold,
        )
        witness = _parse_bool(
            os.environ.get(LAYA_WITNESS_ENV_VAR),
            DEFAULT_WITNESS,
            LAYA_WITNESS_ENV_VAR,
        )
        witness_two_stage = _parse_bool(
            os.environ.get(LAYA_WITNESS_TWO_STAGE_ENV_VAR),
            DEFAULT_WITNESS_TWO_STAGE,
            LAYA_WITNESS_TWO_STAGE_ENV_VAR,
        )
        allow_baseline_with_witness = _parse_bool(
            os.environ.get(LAYA_ALLOW_BASELINE_WITH_WITNESS_ENV_VAR),
            False,
            LAYA_ALLOW_BASELINE_WITH_WITNESS_ENV_VAR,
        )
        negative_instructions = _parse_bool(
            os.environ.get(LAYA_NEGATIVE_INSTRUCTIONS_ENV_VAR),
            True,
            LAYA_NEGATIVE_INSTRUCTIONS_ENV_VAR,
        )
        diagnostic_questions = _parse_bool(
            os.environ.get(LAYA_DIAGNOSTIC_QUESTIONS_ENV_VAR),
            False,
            LAYA_DIAGNOSTIC_QUESTIONS_ENV_VAR,
        )
        log_dir = os.environ.get(LAYA_LOG_DIR_ENV_VAR) or default_log_dir
        return cls(
            model=model or DEFAULT_LAYA_MODEL,
            threshold=threshold,
            max_len=max_len,
            log_dir=log_dir,
            decision_rule=decision_rule,
            state_format=state_format,
            witness=witness,
            witness_two_stage=witness_two_stage,
            allow_baseline_with_witness=allow_baseline_with_witness,
            negative_instructions=negative_instructions,
            diagnostic_questions=diagnostic_questions,
            criterion_thresholds=criterion_thresholds,
        )
