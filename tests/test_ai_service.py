from src.services.ai_prioritization import AIPrioritizationService


async def test_unconfigured_returns_empty_priorities():
    service = AIPrioritizationService.__new__(AIPrioritizationService)
    service.client = None
    service.is_configured = False

    result = await service.generate_daily_priorities(
        calendar_events=[{"summary": "Meeting"}],
        urgent_emails=[],
        email_summary={"unread_count": 5, "important_unread_count": 1},
    )
    assert result == []


async def test_unconfigured_returns_emails_unchanged():
    service = AIPrioritizationService.__new__(AIPrioritizationService)
    service.client = None
    service.is_configured = False

    emails = [
        {"sender": "alice@example.com", "subject": "Hello"},
        {"sender": "bob@example.com", "subject": "Urgent"},
    ]
    result = await service.analyze_email_urgency(emails)
    assert result == emails
    assert "urgency_score" not in result[0]


async def test_unconfigured_returns_tasks_unchanged():
    service = AIPrioritizationService.__new__(AIPrioritizationService)
    service.client = None
    service.is_configured = False

    tasks = [{"title": "Deploy v2", "due_date": "2024-12-10"}]
    result = await service.generate_task_priorities(tasks)
    assert result == tasks
    assert "ai_priority_score" not in result[0]


async def test_empty_inputs():
    service = AIPrioritizationService.__new__(AIPrioritizationService)
    service.client = None
    service.is_configured = False

    assert await service.analyze_email_urgency([]) == []
    assert await service.generate_task_priorities([]) == []


def test_prepare_context_with_all_data():
    service = AIPrioritizationService.__new__(AIPrioritizationService)
    service.client = None
    service.is_configured = False

    context = service._prepare_context(
        calendar_events=[{"time_range": "9:00-10:00", "summary": "Standup"}],
        urgent_emails=[{"sender": "boss@co.com", "subject": "Review needed"}],
        email_summary={"unread_count": 10, "important_unread_count": 2},
        tasks=[{"title": "Ship feature", "due_date": "2024-12-15"}],
    )
    assert "CALENDAR:" in context
    assert "Standup" in context
    assert "10 unread" in context
    assert "IMPORTANT EMAILS:" in context
    assert "boss@co.com" in context
    assert "TASKS:" in context
    assert "Ship feature" in context


def test_prepare_context_empty():
    service = AIPrioritizationService.__new__(AIPrioritizationService)
    service.client = None
    service.is_configured = False

    context = service._prepare_context(
        calendar_events=[],
        urgent_emails=[],
        email_summary={"unread_count": 0, "important_unread_count": 0},
        tasks=None,
    )
    assert "No events today" in context
    assert "0 unread" in context
    assert "TASKS:" not in context
