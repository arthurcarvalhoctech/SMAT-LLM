"""LLM provider configuration resolved from environment variables.

Environment variables take precedence over ``env-config.json``. The provider
abstraction supports native Gemini, OpenAI-compatible APIs (DeepSeek, OpenAI,
OpenRouter, Groq, Together, vLLM, LM Studio, ...), Ollama and Anthropic.
"""

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv

    # Loads a .env from the current directory or one of its parents.
    load_dotenv()
except ImportError:  # pragma: no cover - python-dotenv is optional
    pass


PROVIDER_ALIASES = {
    "google": "gemini",
    "google-genai": "gemini",
    "google_genai": "gemini",
    "openai-compatible": "openai",
    "openai_compatible": "openai",
    "claude": "anthropic",
}

DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-flash",
    "ollama": "llama3.1:8b",
    "anthropic": "claude-3-5-sonnet-latest",
}

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "groq": "https://api.groq.com/openai/v1",
    "ollama": "http://localhost:11434/api/chat",
    "anthropic": "https://api.anthropic.com/v1/messages",
}

PROVIDER_KEY_ENVS = {
    "deepseek": ("DEEPSEEK_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "together": ("TOGETHER_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "ollama": (),
}

LOCAL_PROVIDERS = {"ollama", "vllm", "lmstudio", "custom"}
LLM_ENV_VARS = (
    "LLM_PROVIDER",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_API_URL",
    "LLM_API_KEY",
    "LLM_MODEL_KEY",
)


def _env(name: str) -> Optional[str]:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _first_env(names: tuple[str, ...]) -> Optional[str]:
    for name in names:
        value = _env(name)
        if value:
            return value
    return None


def normalize_provider(provider: Optional[str]) -> str:
    provider = (provider or "gemini").strip().lower()
    return PROVIDER_ALIASES.get(provider, provider)


def infer_provider_from_env() -> Optional[str]:
    for provider, names in PROVIDER_KEY_ENVS.items():
        if names and _first_env(names):
            return provider
    return None


def llm_env_configured() -> bool:
    if any(_env(name) for name in LLM_ENV_VARS):
        return True
    return infer_provider_from_env() is not None


def api_kind(provider: str) -> str:
    provider = normalize_provider(provider)
    if provider == "gemini":
        return "gemini"
    if provider == "ollama":
        return "ollama"
    if provider == "anthropic":
        return "anthropic"
    return "openai"


def api_key_required(provider: str) -> bool:
    return normalize_provider(provider) not in LOCAL_PROVIDERS


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _prompt_keys(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        keys = [key.strip() for key in value.split(",") if key.strip()]
        return keys or None
    if isinstance(value, (list, tuple)):
        keys = [str(key).strip() for key in value if str(key).strip()]
        return keys or None
    return None


@dataclass
class LlmConfig:
    provider: str
    model: str
    api_key: Optional[str]
    base_url: Optional[str]
    temperature: float = 0.0
    seed: int = 42
    timeout_seconds: int = 300
    max_output_tokens: int = 8192
    num_outputs: int = 1
    prompt_keys: Optional[List[str]] = None
    model_key: str = "llm"
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def api_kind(self) -> str:
        return api_kind(self.provider)

    @property
    def output_label(self) -> str:
        label = self.model_key or self.provider
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or "llm"


def resolve_llm_config(
    model_key: str = "llm",
    model_config: Optional[Dict[str, Any]] = None,
) -> LlmConfig:
    """Resolve provider settings with environment variables taking precedence."""
    config = dict(model_config or {})

    provider = normalize_provider(
        _env("LLM_PROVIDER")
        or config.get("provider")
        or infer_provider_from_env()
        or "gemini"
    )

    model = (
        _env("LLM_MODEL")
        or config.get("model")
        or DEFAULT_MODELS.get(provider, "")
    )

    base_url = (
        _env("LLM_BASE_URL")
        or _env("LLM_API_URL")
        or config.get("base_url")
        or config.get("api_url")
        or DEFAULT_BASE_URLS.get(provider)
    )

    api_key = _env("LLM_API_KEY") or config.get("api_key")
    if not api_key:
        api_key = _first_env(PROVIDER_KEY_ENVS.get(provider, ()))

    temperature = _as_float(
        _env("LLM_TEMPERATURE")
        if _env("LLM_TEMPERATURE") is not None
        else config.get("temperature", 0.0),
        0.0,
    )
    seed = _as_int(
        _env("LLM_SEED")
        if _env("LLM_SEED") is not None
        else config.get("seed", 42),
        42,
    )
    timeout_seconds = _as_int(
        _env("LLM_TIMEOUT_SECONDS")
        if _env("LLM_TIMEOUT_SECONDS") is not None
        else config.get("timeout_seconds", 300),
        300,
    )
    max_output_tokens = _as_int(
        _env("LLM_MAX_OUTPUT_TOKENS")
        if _env("LLM_MAX_OUTPUT_TOKENS") is not None
        else config.get("max_output_tokens", 8192),
        8192,
    )
    num_outputs = _as_int(
        _env("LLM_NUM_OUTPUTS")
        if _env("LLM_NUM_OUTPUTS") is not None
        else config.get("num_outputs", 1),
        1,
    )

    prompt_keys = _prompt_keys(_env("LLM_PROMPT_KEYS"))
    if prompt_keys is None:
        prompt_keys = _prompt_keys(config.get("prompt_keys"))

    return LlmConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        seed=seed,
        timeout_seconds=timeout_seconds,
        max_output_tokens=max_output_tokens,
        num_outputs=num_outputs,
        prompt_keys=prompt_keys,
        model_key=_env("LLM_MODEL_KEY") or config.get("model_key") or model_key,
        extra=dict(config.get("extra", {})),
    )
