"""Unit tests for observability.py in the FDE Use Case Template Generator."""

from __future__ import annotations

import logging
import pytest
from observability import (
    scrub_pii,
    setup_structured_logging,
    log_agent_intent,
    log_agent_outcome,
    setup_telemetry,
    get_tracer,
    get_current_trace_id,
    trace_agent_action,
)


def test_scrub_pii_entities():
    """Verify regex and rule-based scrubbing for all standard PII types."""
    assert scrub_pii("Contact me at user.name+tag@sub.domain.org") == "Contact me at [REDACTED_EMAIL]"
    assert scrub_pii("Call 1-800-555-0199 today") == "Call [REDACTED_PHONE] today"
    assert scrub_pii("SSN: 987-65-4321") == "SSN: [REDACTED_SSN]"
    assert scrub_pii("Card 4532-1111-2222-3333") == "Card [REDACTED_CREDIT_CARD]"
    assert scrub_pii("Host at 10.0.0.1") == "Host at [REDACTED_IP]"


def test_structured_json_logger_creation():
    """Verify structured logger instantiates with level and formatting."""
    log = setup_structured_logging(service_name="test-fde-service", log_level=logging.INFO)
    assert log is not None
    assert log.name == "fde_agent"


def test_trace_agent_action_decorator_sync():
    """Verify @trace_agent_action works on synchronous functions."""
    @trace_agent_action(span_name="test_sync_action")
    def compute(a: int, b: int) -> int:
        return a + b

    result = compute(3, 7)
    assert result == 10


@pytest.mark.asyncio
async def test_trace_agent_action_decorator_async():
    """Verify @trace_agent_action works on asynchronous functions."""
    @trace_agent_action(span_name="test_async_action")
    async def compute_async(val: str) -> str:
        return val.upper()

    res = await compute_async("fde")
    assert res == "FDE"
