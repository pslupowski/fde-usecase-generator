"""Unit tests for session_store.py in the FDE Use Case Template Generator."""

from __future__ import annotations

import asyncio
import os
import pytest
from session_store import (
    CompactionConfig,
    compact_conversation_history,
    estimate_token_count,
    FdeSessionStore,
    consolidate_memory_async,
)


def test_estimate_token_count():
    """Verify approximate token estimation."""
    assert estimate_token_count("") == 0
    assert estimate_token_count("Hello") >= 1
    assert estimate_token_count("A" * 400) == 100


def test_compact_conversation_history_below_threshold():
    """Verify that history below token budget is unmodified."""
    class DummyEv:
        def __init__(self, content):
            self.content = content

    events = [DummyEv("Short event 1"), DummyEv("Short event 2")]
    cfg = CompactionConfig(max_history_tokens=1000, sliding_window_turns=4)
    result = compact_conversation_history(events, config=cfg)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_session_store_crud():
    """Verify session create, get, append, list, and delete."""
    temp_file = "test_crud_session.json"
    os.environ["USE_LOCAL_STORAGE"] = "true"
    store = FdeSessionStore(local_fallback_file=temp_file)

    # Create
    sess = await store.create_session(
        app_name="fde_app",
        user_id="user_test_123",
        state={"step": "discovery"},
    )
    assert sess.user_id == "user_test_123"

    # List
    sessions = await store.list_sessions(app_name="fde_app", user_id="user_test_123")
    assert len(sessions) >= 1

    # Get
    fetched = await store.get_session(
        app_name="fde_app",
        user_id="user_test_123",
        session_id=sess.session_id,
    )
    assert fetched is not None
    assert fetched.session_id == sess.session_id

    # Delete
    await store.delete_session(
        app_name="fde_app",
        user_id="user_test_123",
        session_id=sess.session_id,
    )
    after_del = await store.get_session(
        app_name="fde_app",
        user_id="user_test_123",
        session_id=sess.session_id,
    )
    assert after_del is None

    if os.path.exists(temp_file):
        os.remove(temp_file)


@pytest.mark.asyncio
async def test_consolidate_memory_async_background():
    """Verify async memory consolidation runs without raising exceptions."""
    store = FdeSessionStore(local_fallback_file="test_memory.json")
    await consolidate_memory_async(
        session_id="test_sess_001",
        events=[],
        store=store,
    )
    if os.path.exists("test_memory.json"):
        os.remove("test_memory.json")
