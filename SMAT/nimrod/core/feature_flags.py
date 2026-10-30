"""Environment-based feature flags for SMAT."""

import logging
import os
from typing import Optional


DYNAMIC_INTERFERENCE_DETECTION_ENV_VAR = "SMAT_DYNAMIC_INTERFERENCE_DETECTION"

DYNAMIC_INTERFERENCE_DETECTION_DISABLED_MESSAGE = (
    "O fluxo de detecção de interferências baseado em testes não está ativo."
)

LAYA_INTERFERENCE_DETECTION_ENV_VAR = "SMAT_LAYA_INTERFERENCE_DETECTION"

LAYA_INTERFERENCE_DETECTION_DISABLED_MESSAGE = (
    "O fluxo de detecção de interferências com Laya não está ativo."
)

LLM_INTERFERENCE_DETECTION_ENV_VAR = "SMAT_LLM_INTERFERENCE_DETECTION"

LLM_INTERFERENCE_DETECTION_DISABLED_MESSAGE = (
    "O fluxo de detecção de interferências com LLM não está ativo."
)

NO_INTERFERENCE_FLOW_ENABLED_MESSAGE = (
    "Nenhum fluxo de detecção de interferências está ativo."
)

_FALSE_VALUES = {"0", "false", "no", "off", "disabled", "nao", "não"}
_TRUE_VALUES = {"1", "true", "yes", "on", "enabled", "sim"}


def _parse_bool(value: Optional[str], default: bool, env_var: str) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()
    if not normalized:
        return default
    if normalized in _FALSE_VALUES:
        return False
    if normalized in _TRUE_VALUES:
        return True

    logging.warning(
        "Valor inválido para %s: %r. Usando o padrão: %s.",
        env_var,
        value,
        "habilitado" if default else "desabilitado",
    )
    return default


def is_dynamic_interference_detection_enabled() -> bool:
    """Return whether the test-based dynamic interference pipeline is enabled.

    The pipeline is enabled by default to preserve the previous behavior.
    Set ``SMAT_DYNAMIC_INTERFERENCE_DETECTION`` to a false-like value
    (``false``, ``0``, ``no``, ``off``, ``disabled``) to disable it.
    """
    return _parse_bool(
        os.environ.get(DYNAMIC_INTERFERENCE_DETECTION_ENV_VAR),
        default=True,
        env_var=DYNAMIC_INTERFERENCE_DETECTION_ENV_VAR,
    )


def is_laya_interference_detection_enabled() -> bool:
    """Return whether the Laya pre-analysis interference flow is enabled.

    It is disabled by default because it requires the optional ``laya``
    package and downloads model weights on first use. Set
    ``SMAT_LAYA_INTERFERENCE_DETECTION`` to a true-like value to enable it.
    """
    return _parse_bool(
        os.environ.get(LAYA_INTERFERENCE_DETECTION_ENV_VAR),
        default=False,
        env_var=LAYA_INTERFERENCE_DETECTION_ENV_VAR,
    )


def is_llm_interference_detection_enabled() -> bool:
    """Return whether the LLM-based interference pre-analysis is enabled.

    It is disabled by default because it calls an external LLM provider (and
    may incur cost). Configure the provider with ``LLM_PROVIDER``,
    ``LLM_MODEL`` and the corresponding API key, then set
    ``SMAT_LLM_INTERFERENCE_DETECTION`` to a true-like value.
    """
    return _parse_bool(
        os.environ.get(LLM_INTERFERENCE_DETECTION_ENV_VAR),
        default=False,
        env_var=LLM_INTERFERENCE_DETECTION_ENV_VAR,
    )
