"""Secure credential storage for API keys.

Prefers OS-level credential stores via the ``keyring`` library (macOS Keychain,
Windows Credential Manager, Linux SecretService/kwallet). Falls back to
environment variable lookup when keyring is unavailable or fails.

Keys are NEVER stored in QSettings (plaintext INI/registry). The only
persistent indicator in QSettings is a boolean flag per backend:
``translation/remember_key_<backend>`` = "1".
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

LOGGER = logging.getLogger(__name__)

_SERVICE_NAME = "SalesforceTranslationManager"

# Mapping from backend key to environment variable name
_ENV_VARS = {
    "deepl": "DEEPL_API_KEY",
    "azure": "AZURE_TRANSLATOR_KEY",
    "openai": "OPENAI_API_KEY",
}


def _keyring_available() -> bool:
    """Check if keyring is importable and functional."""
    try:
        import keyring

        # Some keyring backends (like the null backend) are non-functional
        backend = keyring.get_keyring()
        # The fail backend name contains "Fail" or "null"
        name = type(backend).__name__.lower()
        if "fail" in name or "null" in name:
            return False
        return True
    except Exception:
        return False


def store_api_key(backend: str, key: str) -> bool:
    """Store an API key securely. Returns True on success."""
    if not key:
        return False
    try:
        import keyring

        keyring.set_password(_SERVICE_NAME, f"api_key_{backend}", key)
        return True
    except Exception as exc:
        LOGGER.debug("Failed to store key in keyring: %s", exc)
        return False


def retrieve_api_key(backend: str) -> Optional[str]:
    """Retrieve an API key. Checks keyring first, then environment variable."""
    # Try keyring
    try:
        import keyring

        stored = keyring.get_password(_SERVICE_NAME, f"api_key_{backend}")
        if stored:
            return stored
    except Exception as exc:
        LOGGER.debug("Keyring lookup failed: %s", exc)

    # Fall back to environment variable
    env_var = _ENV_VARS.get(backend)
    if env_var:
        value = os.environ.get(env_var)
        if value:
            return value

    return None


def delete_api_key(backend: str) -> None:
    """Remove a stored API key from keyring."""
    try:
        import keyring

        keyring.delete_password(_SERVICE_NAME, f"api_key_{backend}")
    except Exception:
        pass


def mask_key(key: Optional[str]) -> str:
    """Mask an API key for display purposes: show first 4 chars only."""
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return key[:4] + "*" * (len(key) - 4)


def keyring_status() -> str:
    """Return a human-readable status of the keyring backend."""
    try:
        import keyring

        backend = keyring.get_keyring()
        name = type(backend).__name__
        if "fail" in name.lower() or "null" in name.lower():
            return "No secure storage available (keys stored in session only)"
        return f"Secure storage: {name}"
    except ImportError:
        return "keyring not installed (keys stored in session only)"
    except Exception as exc:
        return f"Keyring error: {exc}"


def sanitize_error_message(message: str) -> str:
    """Mask anything that looks like an API key in an error message."""
    # Mask long alphanumeric strings (>20 chars) that might be keys
    return re.sub(
        r"(?<=['\"\s=:])[A-Za-z0-9_\-]{20,}",
        lambda m: mask_key(m.group()),
        message,
    )
