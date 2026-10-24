"""Secure Secret Management module for the FDE Use Case Template Generator.

Retrieves credentials dynamically from Google Cloud Secret Manager for project
`patrice-fde-agent-l200` with local environment fallback. Enforces zero hardcoded
API keys or tokens across the entire codebase.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger("fde_agent.secrets")

# Default GCP project identifier from architecture specification
DEFAULT_GCP_PROJECT_ID: str = "patrice-fde-agent-l200"
DEFAULT_SECRET_ID: str = "GEMINI_API_KEY"

# In-memory secret cache with TTL to eliminate unnecessary Secret Manager RPCs
_SECRET_CACHE: dict[str, tuple[str, float]] = {}
CACHE_TTL_SECONDS: float = 300.0  # 5 minutes TTL


def get_secret(
    secret_id: str,
    project_id: str = DEFAULT_GCP_PROJECT_ID,
    version_id: str = "latest",
    use_cache: bool = True,
) -> str:
    """Retrieve a secret payload from Google Cloud Secret Manager with fallback.

    Args:
        secret_id: The ID/name of the secret in Secret Manager.
        project_id: The Google Cloud project ID (default: 'patrice-fde-agent-l200').
        version_id: The secret version string (default: 'latest').
        use_cache: Whether to return cached value if within TTL.

    Returns:
        The secret payload string.

    Raises:
        RuntimeError: If the secret cannot be retrieved from Secret Manager and
            no local environment fallback exists.
    """
    cache_key = f"{project_id}:{secret_id}:{version_id}"
    now = time.time()

    if use_cache and cache_key in _SECRET_CACHE:
        val, expiry = _SECRET_CACHE[cache_key]
        if now < expiry:
            return val

    # 1. Attempt retrieval from Google Cloud Secret Manager
    try:
        from google.cloud import secretmanager  # pylint: disable=import-outside-toplevel

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        secret_val = response.payload.data.decode("UTF-8").strip()

        if secret_val:
            _SECRET_CACHE[cache_key] = (secret_val, now + CACHE_TTL_SECONDS)
            logger.info(
                "Successfully accessed secret from GCP Secret Manager",
                extra={
                    "secret_id": secret_id,
                    "project_id": project_id,
                    "source": "secret_manager",
                },
            )
            return secret_val
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "Secret Manager access failed, attempting environment fallback",
            extra={
                "secret_id": secret_id,
                "project_id": project_id,
                "error": str(exc),
            },
        )

    # 2. Graceful fallback to environment variable (for local development or CI)
    env_val = os.environ.get(secret_id) or os.environ.get(secret_id.upper())
    if env_val:
        logger.info(
            "Resolved secret from local environment variable fallback",
            extra={"secret_id": secret_id, "source": "environment_variable"},
        )
        _SECRET_CACHE[cache_key] = (env_val, now + CACHE_TTL_SECONDS)
        return env_val

    # 3. In testing/CI dry-run mode, provide an explicit mock key if configured
    if os.environ.get("CI") or os.environ.get("MOCK_SECRETS") == "true":
        mock_val = "mock-secret-key-for-testing-only"
        logger.info(
            "Resolved secret using test mock key in CI/mock environment",
            extra={"secret_id": secret_id, "source": "mock_ci"},
        )
        return mock_val

    raise RuntimeError(
        f"Unable to resolve required secret '{secret_id}' for project '{project_id}'. "
        "Neither Google Cloud Secret Manager nor local environment variable was accessible. "
        "Ensure Secret Manager API is enabled and 'roles/secretmanager.secretAccessor' is granted."
    )


def get_gemini_api_key(project_id: str = DEFAULT_GCP_PROJECT_ID) -> str:
    """Retrieve the GEMINI_API_KEY for authenticating with Gemini 2.5 models.

    Args:
        project_id: The target Google Cloud project (default: 'patrice-fde-agent-l200').

    Returns:
        The Gemini API key string.
    """
    return get_secret(secret_id=DEFAULT_SECRET_ID, project_id=project_id)


def clear_secret_cache() -> None:
    """Clear in-memory cache for secrets."""
    _SECRET_CACHE.clear()
