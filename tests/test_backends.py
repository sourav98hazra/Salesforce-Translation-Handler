"""Tests for translator backend factory and mocked backend behavior."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from stx.translate import list_backends, make_backend
from stx.translate.factory import check_backend_available
from stx.translate.base import Translator
from stx.translate.google_free import GoogleFreeTranslator


def test_make_backend_google():
    translator = make_backend("google")
    assert isinstance(translator, GoogleFreeTranslator)
    assert isinstance(translator, Translator)


def test_make_backend_unknown_raises():
    with pytest.raises(ValueError, match="Unknown translator backend"):
        make_backend("nonexistent")


def test_list_backends_returns_four():
    backends = list_backends()
    assert len(backends) == 4
    keys = [b.key for b in backends]
    assert "google" in keys
    assert "deepl" in keys
    assert "azure" in keys
    assert "openai" in keys


def test_backend_info_requires_api_key():
    backends = {b.key: b for b in list_backends()}
    assert backends["google"].requires_api_key is False
    assert backends["deepl"].requires_api_key is True
    assert backends["azure"].requires_api_key is True
    assert backends["openai"].requires_api_key is True


def test_deepl_missing_key_raises():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="API key"):
            make_backend("deepl")


def test_azure_missing_key_raises():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="API key"):
            make_backend("azure")


def test_openai_missing_key_raises():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="API key"):
            make_backend("openai")


def test_check_backend_available_google():
    available, reason = check_backend_available("google")
    assert available is True
    assert reason == ""


def test_check_backend_available_unknown():
    available, reason = check_backend_available("nonexistent")
    assert available is False
    assert "Unknown" in reason


def test_deepl_with_key_constructs():
    """DeepL backend constructs successfully when api_key is provided."""
    translator = make_backend("deepl", api_key="fake-key-for-test")
    assert isinstance(translator, Translator)


def test_azure_with_key_constructs():
    """Azure backend constructs successfully when api_key is provided."""
    translator = make_backend("azure", api_key="fake-key-for-test")
    assert isinstance(translator, Translator)
