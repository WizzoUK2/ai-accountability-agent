from src.integrations.asana import AsanaTask, AsanaService


def test_asana_task_to_dict():
    task = AsanaTask(
        gid="12345",
        name="Build feature",
        completed=False,
        due_on="2024-12-15",
        project_name="Client X",
        project_gid="proj1",
        tags=["urgent", "frontend"],
    )
    d = task.to_dict()
    assert d["gid"] == "12345"
    assert d["name"] == "Build feature"
    assert d["completed"] is False
    assert d["project_name"] == "Client X"
    assert d["tags"] == ["urgent", "frontend"]


def test_asana_task_due_date_parsing():
    # Date only
    task = AsanaTask(gid="1", name="T", due_on="2024-12-15")
    assert task.due_date is not None
    assert task.due_date.year == 2024
    assert task.due_date.month == 12
    assert task.due_date.day == 15

    # Datetime with Z
    task2 = AsanaTask(gid="2", name="T", due_at="2024-12-15T14:00:00.000Z")
    assert task2.due_date is not None
    assert task2.due_date.hour == 14

    # No due date
    task3 = AsanaTask(gid="3", name="T")
    assert task3.due_date is None

    # due_at takes precedence over due_on
    task4 = AsanaTask(gid="4", name="T", due_on="2024-12-15", due_at="2024-12-16T10:00:00.000Z")
    assert task4.due_date.day == 16


def test_asana_service_parse_task():
    service = AsanaService.__new__(AsanaService)
    data = {
        "gid": "999",
        "name": "Fix bug",
        "completed": False,
        "due_on": "2024-12-20",
        "due_at": None,
        "notes": "Important fix",
        "assignee": {"name": "Alice"},
        "projects": [{"name": "Client Z", "gid": "p1"}],
        "tags": [{"name": "bug"}, {"name": "p0"}],
        "permalink_url": "https://app.asana.com/0/task/999",
    }
    task = service._parse_task(data)
    assert task.gid == "999"
    assert task.name == "Fix bug"
    assert task.assignee_name == "Alice"
    assert task.project_name == "Client Z"
    assert task.tags == ["bug", "p0"]
    assert task.permalink_url == "https://app.asana.com/0/task/999"


def test_asana_service_parse_task_minimal():
    service = AsanaService.__new__(AsanaService)
    data = {"gid": "1", "name": "Simple task"}
    task = service._parse_task(data)
    assert task.gid == "1"
    assert task.name == "Simple task"
    assert task.project_name is None
    assert task.assignee_name is None
    assert task.tags == []


def test_from_integration():
    class FakeIntegration:
        access_token = "test-token-123"

    service = AsanaService.from_integration(FakeIntegration())
    assert service.access_token == "test-token-123"
    assert "Bearer test-token-123" in service.headers["Authorization"]
