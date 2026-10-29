"""Adapter for the optional Laya decision-model package.

Laya is a local, weights-based decision engine. Importing the package is
deliberately lazy so SMAT keeps working when the optional dependency is not
installed. The flow treats Laya as a hypothesis generator, never as the
authoritative conflict detector.
"""

import inspect
import logging
import os
import sys
from typing import Any, Dict, Optional, Protocol


class LayaUnavailableError(RuntimeError):
    """Raised when the optional Laya package or its checkpoint cannot be used."""


class LayaClient(Protocol):
    def predict(self, state: Any, questions: Dict[str, Any]) -> Dict[str, Any]:
        ...


def _has_int_max_str_digits() -> bool:
    return hasattr(sys, "get_int_max_str_digits")


def _validate_python_runtime() -> None:
    """Fail early on the broken Python 3.11.0rc1 shipped by Ubuntu 22.04.

    That interpreter lacks ``sys.get_int_max_str_digits``. ``torch._dynamo``
    registers ``sys.intern`` before failing on the missing attribute, and a
    later import then reports the misleading "Duplicate dispatch rule" error.
    """
    if sys.version_info >= (3, 11) and not _has_int_max_str_digits():
        raise LayaUnavailableError(
            "Python %s não possui sys.get_int_max_str_digits. Isso é típico do "
            "python3.11 3.11.0rc1 do Ubuntu 22.04 e quebra o torch._dynamo com "
            "'Duplicate dispatch rule ...'. Use Python 3.11.x final (o Dockerfile "
            "atualizado instala via deadsnakes) ou Python 3.10."
            % sys.version.split()[0]
        )


class _LocalCheckpointRouter:
    """Serves one local checkpoint directory (e.g. a fine-tuned run) with the Router's predict shape.

    ``laya.Router`` only knows the named checkpoints, so a directory is loaded with ``laya.load``.
    ``model`` is accepted and ignored, because there is only one model. ``max_len`` is passed to
    the agent, so ``SMAT_LAYA_MAX_LEN`` is applied; without it the checkpoint's own config value
    (1024 for the fine-tuned model) would be used.
    """

    def __init__(self, checkpoint_dir: str) -> None:
        from laya import load

        self._agent = load(checkpoint_dir)

    def predict(self, state: Any, questions: Dict[str, Any], model: Optional[str] = None,
                max_len: Optional[int] = None) -> Dict[str, Any]:
        return self._agent.predict(state, questions, max_len=max_len)


class RouterLayaClient:
    """Thin wrapper around ``laya.Router`` with a lazy import."""

    def __init__(self, model: str = "english", max_len: int = 512) -> None:
        self.model = model
        self.max_len = max_len
        self._router = None
        self._load_error: Optional[str] = None

    def _ensure_router(self) -> None:
        if self._router is not None:
            return
        if self._load_error is not None:
            raise LayaUnavailableError(self._load_error)

        _validate_python_runtime()

        try:
            from laya import Router
        except ImportError as error:
            self._load_error = (
                "O pacote opcional 'laya' não está instalado. "
                "Instale com 'pip install laya' (Python >= 3.10) e tente novamente."
            )
            raise LayaUnavailableError(self._load_error) from error

        try:
            if os.path.isdir(self.model):
                self._router = _LocalCheckpointRouter(self.model)
            else:
                self._router = Router()
        except Exception as error:
            self._load_error = f"Não foi possível inicializar o Laya: {error}"
            raise LayaUnavailableError(self._load_error) from error

    def predict(self, state: Any, questions: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_router()

        kwargs: Dict[str, Any] = {}
        try:
            parameters = inspect.signature(self._router.predict).parameters
        except (TypeError, ValueError):
            parameters = {}

        if not parameters or "model" in parameters:
            kwargs["model"] = self.model
        if not parameters or "max_len" in parameters:
            kwargs["max_len"] = self.max_len

        return self._router.predict(state, questions, **kwargs)

    def describe(self) -> Dict[str, Any]:
        return {
            "package": "laya",
            "model": self.model,
            "max_len": self.max_len,
        }


def log_laya_install_hint(error: Exception) -> None:
    logging.error(
        "Laya pre-analysis is unavailable: %s", error
    )
