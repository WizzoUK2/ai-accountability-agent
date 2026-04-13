"""Tests for the Digital Twin API client.

Covers: successful twin calls, fallback to generic AI, timeout/error handling,
and data adaptation between agent and twin API shapes.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.services.twin_client import TwinClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


SAMPLE_EMAILS = [
    {"sender": "sarah@modiphius.net", "subject": "Contract renewal", "snippet": "Please review", "date": "2026-04-13T09:00:00Z", "uid": "abc123"},
    {"sender": "newsletter@techcrunch.com", "subject": "Weekly digest", "snippet": "Top stories"},
]

SAMPLE_TASKS = [
    {"title": "Review FUTWIZ Q1 financials", "due_date": "2026-04-15", "client_name": "FUTWIZ", "id": "task-1"},
    {"title": "Update LinkedIn profile", "due_date": None, "client_name": None},
]

SAMPLE_CALENDAR = [
    {"id": "evt-1", "summary": "FUTWIZ board call", "time_range": "2:00 PM - 3:00 PM", "start": "2026-04-13T14:00:00"},
]


def _make_client(configured: bool = True) -> TwinClient:
    """Create a TwinClient with mocked settings."""
    client = TwinClient.__new__(TwinClient)
    client.is_configured = configured
    return client


# ---------------------------------------------------------------------------
# Fallback when twin is not configured
# ---------------------------------------------------------------------------


async def test_priorities_fallback_when_not_configured():
    client = _make_client(configured=False)
    with patch("src.services.twin_client.ai_service") as mock_ai:
        mock_ai.generate_daily_priorities = AsyncMock(return_value=["Generic priority 1"])
        result = await client.generate_daily_priorities(
            calendar_events=SAMPLE_CALENDAR,
            urgent_emails=SAMPLE_EMAILS,
            email_summary={"unread_count": 5, "important_unread_count": 1},
            tasks=SAMPLE_TASKS,
        )
        assert result == ["Generic priority 1"]
        mock_ai.generate_daily_priorities.assert_awaited_once()


async def test_email_scoring_fallback_when_not_configured():
    client = _make_client(configured=False)
    with patch("src.services.twin_client.ai_service") as mock_ai:
        mock_ai.analyze_email_urgency = AsyncMock(return_value=SAMPLE_EMAILS)
        result = await client.analyze_email_urgency(SAMPLE_EMAILS)
        assert result == SAMPLE_EMAILS
        mock_ai.analyze_email_urgency.assert_awaited_once()


async def test_task_scoring_fallback_when_not_configured():
    client = _make_client(configured=False)
    with patch("src.services.twin_client.ai_service") as mock_ai:
        mock_ai.generate_task_priorities = AsyncMock(return_value=SAMPLE_TASKS)
        result = await client.generate_task_priorities(SAMPLE_TASKS)
        assert result == SAMPLE_TASKS
        mock_ai.generate_task_priorities.assert_awaited_once()


# ---------------------------------------------------------------------------
# Fallback when twin API errors or times out
# ---------------------------------------------------------------------------


async def test_priorities_fallback_on_timeout():
    client = _make_client(configured=True)
    with (
        patch.object(client, "_post", return_value=None) as mock_post,
        patch("src.services.twin_client.ai_service") as mock_ai,
    ):
        mock_ai.generate_daily_priorities = AsyncMock(return_value=["Fallback priority"])
        result = await client.generate_daily_priorities(
            calendar_events=[], urgent_emails=[], email_summary={"unread_count": 0, "important_unread_count": 0},
        )
        assert result == ["Fallback priority"]
        mock_post.assert_awaited_once()


async def test_email_scoring_fallback_on_error():
    client = _make_client(configured=True)
    with (
        patch.object(client, "_post", return_value=None),
        patch("src.services.twin_client.ai_service") as mock_ai,
    ):
        mock_ai.analyze_email_urgency = AsyncMock(return_value=SAMPLE_EMAILS)
        result = await client.analyze_email_urgency(SAMPLE_EMAILS)
        assert result == SAMPLE_EMAILS


async def test_task_scoring_fallback_on_error():
    client = _make_client(configured=True)
    with (
        patch.object(client, "_post", return_value=None),
        patch("src.services.twin_client.ai_service") as mock_ai,
    ):
        mock_ai.generate_task_priorities = AsyncMock(return_value=SAMPLE_TASKS)
        result = await client.generate_task_priorities(SAMPLE_TASKS)
        assert result == SAMPLE_TASKS


# ---------------------------------------------------------------------------
# Successful twin API calls
# ---------------------------------------------------------------------------


async def test_priorities_from_twin():
    client = _make_client(configured=True)

    twin_response = {
        "items": [
            {"id": "evt-1", "urgency": 90, "reasoning": "Board call needs prep", "suggested_action": "Review Q1 financials before the FUTWIZ call"},
            {"id": "abc123", "urgency": 70, "reasoning": "Sarah is a key partner", "suggested_action": "Reply to Sarah's contract email"},
        ],
        "craig_note": "Focus on the board call — everything else can wait.",
        "retrieved_context_count": 5,
    }

    with patch.object(client, "_post", return_value=twin_response):
        result = await client.generate_daily_priorities(
            calendar_events=SAMPLE_CALENDAR,
            urgent_emails=SAMPLE_EMAILS,
            email_summary={"unread_count": 47, "important_unread_count": 3},
            tasks=SAMPLE_TASKS,
        )
        assert len(result) >= 2
        assert "board call" in result[0].lower() or "focus" in result[0].lower()


async def test_email_scoring_from_twin():
    client = _make_client(configured=True)

    # We need the second email's adapted ID since it has no uid
    adapted_newsletter = TwinClient._adapt_email(SAMPLE_EMAILS[1], 1)
    newsletter_id = adapted_newsletter["id"]

    twin_response = {
        "emails": [
            {"id": "abc123", "urgency": 85, "category": "client", "reasoning": "Key partner — Modiphius contract"},
            {"id": newsletter_id, "urgency": 10, "category": "noise", "reasoning": "Newsletter, no action needed"},
        ],
        "retrieved_context_count": 3,
    }

    with patch.object(client, "_post", return_value=twin_response):
        emails = [dict(e) for e in SAMPLE_EMAILS]  # copy to avoid mutation
        result = await client.analyze_email_urgency(emails)
        # First email (sarah) should have high urgency
        sarah = next(e for e in result if "modiphius" in e.get("sender", ""))
        assert sarah["urgency_score"] >= 8
        assert sarah.get("twin_category") == "client"
        # Newsletter should have low urgency
        newsletter = next(e for e in result if "techcrunch" in e.get("sender", ""))
        assert newsletter["urgency_score"] <= 2


async def test_task_scoring_from_twin():
    client = _make_client(configured=True)

    twin_response = {
        "tasks": [
            {"id": "task-1", "priority": 92, "reasoning": "Board meeting soon, active investment", "defer": False},
            {"id": "1", "priority": 15, "reasoning": "No deadline, not aligned with priorities", "defer": True},
        ],
        "retrieved_context_count": 4,
    }

    with patch.object(client, "_post", return_value=twin_response):
        tasks = [dict(t) for t in SAMPLE_TASKS]  # copy
        result = await client.generate_task_priorities(tasks)
        # FUTWIZ task should be first (highest priority)
        assert result[0]["title"] == "Review FUTWIZ Q1 financials"
        assert result[0]["ai_priority_score"] == 92
        assert result[0]["twin_defer"] is False
        # LinkedIn task should be lower
        assert result[1]["ai_priority_score"] == 15
        assert result[1]["twin_defer"] is True


# ---------------------------------------------------------------------------
# Data adaptation
# ---------------------------------------------------------------------------


def test_adapt_email_with_uid():
    email = {"uid": "msg-42", "sender": "alice@co.com", "subject": "Hi", "snippet": "Hello there", "date": "2026-04-13T10:00:00Z"}
    adapted = TwinClient._adapt_email(email, 0)
    assert adapted["id"] == "msg-42"
    assert adapted["sender"] == "alice@co.com"
    assert adapted["preview"] == "Hello there"
    assert adapted["received_at"] == "2026-04-13T10:00:00Z"


def test_adapt_email_without_uid_generates_id():
    email = {"sender": "bob@co.com", "subject": "Test"}
    adapted = TwinClient._adapt_email(email, 0)
    assert len(adapted["id"]) == 12  # md5 truncated
    assert adapted["sender"] == "bob@co.com"


def test_adapt_email_uses_from_field():
    email = {"from": "carol@co.com", "subject": "Hey", "preview": "Preview text"}
    adapted = TwinClient._adapt_email(email, 0)
    assert adapted["sender"] == "carol@co.com"
    assert adapted["preview"] == "Preview text"


def test_adapt_task_with_id():
    task = {"id": "asana-123", "title": "Ship feature", "client_name": "FUTWIZ", "due_date": "2026-04-20"}
    adapted = TwinClient._adapt_task(task, 0)
    assert adapted["id"] == "asana-123"
    assert adapted["name"] == "Ship feature"
    assert adapted["project"] == "FUTWIZ"
    assert adapted["due_on"] == "2026-04-20"


def test_adapt_task_without_id():
    task = {"title": "Do something"}
    adapted = TwinClient._adapt_task(task, 3)
    assert adapted["id"] == "3"
    assert adapted["name"] == "Do something"


# ---------------------------------------------------------------------------
# Empty inputs
# ---------------------------------------------------------------------------


async def test_email_scoring_empty_list():
    client = _make_client(configured=True)
    with patch("src.services.twin_client.ai_service") as mock_ai:
        mock_ai.analyze_email_urgency = AsyncMock(return_value=[])
        result = await client.analyze_email_urgency([])
        assert result == []


async def test_task_scoring_empty_list():
    client = _make_client(configured=True)
    with patch("src.services.twin_client.ai_service") as mock_ai:
        mock_ai.generate_task_priorities = AsyncMock(return_value=[])
        result = await client.generate_task_priorities([])
        assert result == []
