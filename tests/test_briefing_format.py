from src.services.briefing import BriefingService


def test_format_sms_empty_briefing():
    service = BriefingService.__new__(BriefingService)
    briefing = {
        "calendar_events": [],
        "email_summary": {"unread_count": 0, "important_unread_count": 0},
        "urgent_emails": [],
        "priorities": [],
    }
    result = service.format_sms_briefing(briefing)
    assert "Good morning" in result
    assert "Clear day" in result
    assert "0 unread" in result


def test_format_sms_with_events():
    service = BriefingService.__new__(BriefingService)
    briefing = {
        "calendar_events": [
            {"time_range": "9:00-10:00", "summary": "Team standup"},
            {"time_range": "14:00-15:00", "summary": "Client review meeting"},
        ],
        "email_summary": {"unread_count": 12, "important_unread_count": 3},
        "urgent_emails": [
            {"sender": "boss@company.com", "subject": "Q1 Report needed ASAP"},
        ],
        "priorities": [
            "Prepare Q1 report for boss",
            "Review client deliverables",
            "Follow up on hiring pipeline",
        ],
    }
    result = service.format_sms_briefing(briefing)
    assert "2 events" in result
    assert "Team standup" in result
    assert "12 unread" in result
    assert "3 important" in result
    assert "Q1 Report" in result
    assert "PRIORITIES" in result


def test_format_sms_truncates_long_events():
    service = BriefingService.__new__(BriefingService)
    briefing = {
        "calendar_events": [{"time_range": "9:00", "summary": f"Event {i}"} for i in range(8)],
        "email_summary": {"unread_count": 0, "important_unread_count": 0},
        "urgent_emails": [],
        "priorities": [],
    }
    result = service.format_sms_briefing(briefing)
    assert "+3 more" in result


def test_format_sms_character_limit():
    service = BriefingService.__new__(BriefingService)
    briefing = {
        "calendar_events": [
            {"time_range": f"{i}:00", "summary": f"Meeting about important topic {i}"}
            for i in range(5)
        ],
        "email_summary": {"unread_count": 50, "important_unread_count": 10},
        "urgent_emails": [
            {"sender": f"person{i}@example.com", "subject": f"Important subject {i}"}
            for i in range(3)
        ],
        "priorities": [f"Priority item number {i} with details" for i in range(5)],
    }
    result = service.format_sms_briefing(briefing)
    assert len(result) < 1600
