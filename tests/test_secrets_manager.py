"""Unit tests for secrets_manager.py in the FDE Use Case Template Generator."""

from __future__ import annotations

import os
import pytest
from secrets_manager import (
    get_secret,
    get_gemini_api_key,
    clear_secret_cache,
)


def test_get_secret_with_mock_environment():
    """Verify secrets manager returns mock secret in CI/mock mode."""
    clear_secret_cache()
    os.environ["MOCK_SECRETS"] = "true"
    secret = get_secret("TEST_SECRET_KEY", project_id="patrice-fde-agent-l200")
    assert secret == "mock-secret-key-for-testing-only"


def test_get_secret_from_env_fallback():
    """Verify secrets manager falls back to environment variable when configured."""
    clear_secret_cache()
    os.environ.pop("MOCK_SECRETS", None)
    os.environ["CUSTOM_TEST_API_KEY"] = "sk-gcp-test-token-xyz"
    try:
        secret = get_secret("CUSTOM_TEST_API_KEY", project_id="patrice-fde-agent-l200")
        assert secret == "sk-gcp-test-token-xyz"
    finally:
        os.environ.pop("CUSTOM_TEST_API_KEY", None)


def test_get_gemini_api_key_helper():
    """Verify get_gemini_api_key helper delegates properly."""
    clear_secret_cache()
    os.environ["MOCK_SECRETS"] = "true"
    key = get_gemini_api_key(project_id="patrice-fde-agent-l200")
    assert key is not None
