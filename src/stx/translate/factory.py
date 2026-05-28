"""Construct translator backends by name.

Used by both the CLI (``--backend google``) and the GUI (Backend
dropdown) so the available backend list is centralised in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional

from .base import Translator
from .google_free import GoogleFreeTranslator


@dataclass(frozen=True)
class BackendInfo:
    """Display metadata for a translator backend."""

    key: str
    label: str
    requires_api_key: bool
    env_var: Optional[str]
    description: str


# Mapping of backend key -> info + factory.  We register the cheaper
# backends first so they're preferred in dropdowns / docs.
_REGISTRY: Dict[str, "tuple[BackendInfo, Callable[..., Translator]]"] = {}


def register(info: BackendInfo, factory: Callable[..., Translator]) -> None:
    _REGISTRY[info.key] = (info, factory)


def list_backends() -> list[BackendInfo]:
    """Return every registered backend's info, in registration order."""
    return [info for info, _ in _REGISTRY.values()]


def make_backend(key: str, **kwargs) -> Translator:
    """Construct the translator backend identified by ``key``.

    Extra keyword arguments are forwarded to the backend constructor
    (used by the GUI to pass API keys / region without touching env
    variables).
    """
    if key not in _REGISTRY:
        available = ", ".join(_REGISTRY.keys())
        raise ValueError(f"Unknown translator backend {key!r}.  Available: {available}")
    _, factory = _REGISTRY[key]
    return factory(**kwargs)


# ---------------------------------------------------------------------------
# Default registrations
# ---------------------------------------------------------------------------

register(
    BackendInfo(
        key="google",
        label="Google Translate (free)",
        requires_api_key=False,
        env_var=None,
        description="Free, rate-limited.  No API key required.",
    ),
    lambda **kwargs: GoogleFreeTranslator(**kwargs),
)


def _make_deepl(**kwargs) -> Translator:
    from .deepl_paid import DeepLTranslator

    return DeepLTranslator(**kwargs)


register(
    BackendInfo(
        key="deepl",
        label="DeepL",
        requires_api_key=True,
        env_var="DEEPL_API_KEY",
        description="High-quality European + Japanese.  Free tier available.",
    ),
    _make_deepl,
)


def _make_azure(**kwargs) -> Translator:
    from .azure import AzureTranslator

    return AzureTranslator(**kwargs)


register(
    BackendInfo(
        key="azure",
        label="Microsoft Azure Translator",
        requires_api_key=True,
        env_var="AZURE_TRANSLATOR_KEY",
        description="Enterprise backend with high quotas.",
    ),
    _make_azure,
)


def _make_openai(**kwargs) -> Translator:
    from .openai_llm import OpenAITranslator

    return OpenAITranslator(**kwargs)


register(
    BackendInfo(
        key="openai",
        label="OpenAI (GPT)",
        requires_api_key=True,
        env_var="OPENAI_API_KEY",
        description="LLM-based translation.  Slower but glossary-aware.",
    ),
    _make_openai,
)
