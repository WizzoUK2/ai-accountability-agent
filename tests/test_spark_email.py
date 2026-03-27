from unittest.mock import AsyncMock, patch, MagicMock

from src.integrations.spark_email import SparkEmailService


def test_unconfigured_service():
    service = SparkEmailService(server_command="", server_args=[])
    assert service.is_configured is False


def test_configured_service():
    service = SparkEmailService(server_command="python", server_args=["server.py"])
    assert service.is_configured is True
    assert service.server_command == "python"


async def test_unconfigured_returns_empty():
    service = SparkEmailService(server_command="", server_args=[])
    assert await service.list_accounts() == []
    assert await service.get_recent_emails() == []
    assert await service.read_email(uid="123") == {}
    assert await service.search_all_accounts(query="test") == []
    assert await service.get_unread_across_accounts() == []
    assert await service.get_inbox_summary() == {"total_unread": 0, "accounts": []}
    assert await service.find_urgent_emails() == []


async def test_list_accounts():
    service = SparkEmailService(server_command="python", server_args=["server.py"])

    mock_accounts = [
        {"name": "Work Gmail", "email": "craig@work.com", "provider": "gmail"},
        {"name": "Personal", "email": "craig@personal.com", "provider": "outlook"},
    ]

    with patch.object(service, "_call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_accounts
        result = await service.list_accounts()

    assert len(result) == 2
    assert result[0]["name"] == "Work Gmail"
    mock_call.assert_called_once_with("spark_list_accounts", {"response_format": "json"})


async def test_search_all_accounts():
    service = SparkEmailService(server_command="python", server_args=["server.py"])

    mock_results = [
        {
            "account": "Work Gmail",
            "total": 3,
            "emails": [
                {"uid": "1", "subject": "Urgent: deadline", "from": "boss@work.com"},
                {"uid": "2", "subject": "Project update", "from": "team@work.com"},
            ],
        },
    ]

    with patch.object(service, "_call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_results
        result = await service.search_all_accounts(query="urgent", since="15-Jan-2025")

    assert len(result) == 1
    assert result[0]["account"] == "Work Gmail"
    assert len(result[0]["emails"]) == 2
    mock_call.assert_called_once_with("spark_search_all_accounts", {
        "query": "urgent",
        "folder": "INBOX",
        "limit": 10,
        "since": "15-Jan-2025",
        "response_format": "json",
    })


async def test_get_recent_emails():
    service = SparkEmailService(server_command="python", server_args=["server.py"])

    mock_result = {
        "total": 50,
        "emails": [
            {"uid": "1", "subject": "Hello", "is_read": True},
            {"uid": "2", "subject": "Meeting", "is_read": False},
        ],
    }

    with patch.object(service, "_call_tool", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_result
        result = await service.get_recent_emails(account="Work", limit=5)

    assert len(result) == 2
    assert result[0]["subject"] == "Hello"
    mock_call.assert_called_once_with("spark_list_emails", {
        "account": "Work",
        "folder": "INBOX",
        "limit": 5,
        "response_format": "json",
    })


async def test_find_urgent_emails():
    service = SparkEmailService(server_command="python", server_args=["server.py"])

    mock_results = [
        {
            "account": "Work",
            "emails": [
                {"uid": "1", "subject": "URGENT", "from": "boss@co.com", "is_read": False},
                {"uid": "2", "subject": "FYI", "from": "info@co.com", "is_read": True},
            ],
        },
        {
            "account": "Personal",
            "emails": [
                {"uid": "3", "subject": "Action needed", "from": "bank@example.com", "is_read": False},
            ],
        },
    ]

    with patch.object(service, "search_all_accounts", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_results
        result = await service.find_urgent_emails(hours=24, limit=10)

    # Only unread emails (uid 1 and 3, not uid 2 which is read)
    assert len(result) == 2
    assert result[0]["subject"] == "URGENT"
    assert result[0]["account"] == "Work"
    assert result[1]["subject"] == "Action needed"
    assert result[1]["account"] == "Personal"


async def test_get_inbox_summary():
    service = SparkEmailService(server_command="python", server_args=["server.py"])

    call_count = 0

    async def mock_call(name, args):
        nonlocal call_count
        if name == "spark_list_accounts":
            return [{"name": "Work", "email": "craig@work.com"}]
        if name == "spark_list_emails":
            return {
                "total": 100,
                "emails": [
                    {"is_read": True},
                    {"is_read": False},
                    {"is_read": False},
                ],
            }
        return {}

    with patch.object(service, "_call_tool", side_effect=mock_call):
        result = await service.get_inbox_summary()

    assert result["total_unread"] == 2
    assert len(result["accounts"]) == 1
    assert result["accounts"][0]["account"] == "Work"
    assert result["accounts"][0]["unread"] == 2
    assert result["accounts"][0]["total"] == 100


async def test_error_handling_returns_empty():
    service = SparkEmailService(server_command="python", server_args=["server.py"])

    with patch.object(service, "_call_tool", new_callable=AsyncMock, side_effect=Exception("Connection failed")):
        assert await service.list_accounts() == []
        assert await service.get_recent_emails() == []
        assert await service.search_all_accounts() == []
        assert await service.find_urgent_emails() == []
