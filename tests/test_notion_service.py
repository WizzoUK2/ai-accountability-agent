from src.integrations.notion import NotionTask, NotionService


def test_notion_task_to_dict():
    task = NotionTask(
        page_id="abc-123",
        title="Design system",
        status="In Progress",
        due_date="2024-12-20",
        database_name="Project Board",
        tags=["design", "Q4"],
    )
    d = task.to_dict()
    assert d["page_id"] == "abc-123"
    assert d["title"] == "Design system"
    assert d["status"] == "In Progress"
    assert d["tags"] == ["design", "Q4"]


def test_notion_task_due_date_parsing():
    task = NotionTask(page_id="1", title="T", due_date="2024-12-15")
    assert task.due_date is not None
    assert task.due_date.day == 15

    task2 = NotionTask(page_id="2", title="T", due_date="2024-12-15T14:00:00Z")
    assert task2.due_date is not None
    assert task2.due_date.hour == 14

    task3 = NotionTask(page_id="3", title="T")
    assert task3.due_date is None


def test_notion_task_is_completed():
    assert NotionTask(page_id="1", title="T", status="Done").is_completed is True
    assert NotionTask(page_id="2", title="T", status="Complete").is_completed is True
    assert NotionTask(page_id="3", title="T", status="Completed").is_completed is True
    assert NotionTask(page_id="4", title="T", status="Closed").is_completed is True
    assert NotionTask(page_id="5", title="T", status="In Progress").is_completed is False
    assert NotionTask(page_id="6", title="T", status=None).is_completed is False


def test_notion_service_extract_title():
    service = NotionService.__new__(NotionService)

    # Standard Name property
    props = {"Name": {"type": "title", "title": [{"plain_text": "My Task"}]}}
    assert service._extract_title(props) == "My Task"

    # Title property instead of Name
    props2 = {"Title": {"type": "title", "title": [{"plain_text": "Other Task"}]}}
    assert service._extract_title(props2) == "Other Task"

    # No title property
    assert service._extract_title({}) is None


def test_notion_service_extract_status():
    service = NotionService.__new__(NotionService)

    # Status type
    props = {"Status": {"type": "status", "status": {"name": "In Progress"}}}
    assert service._extract_status(props) == "In Progress"

    # Select type
    props2 = {"Status": {"type": "select", "select": {"name": "Done"}}}
    assert service._extract_status(props2) == "Done"

    # No status
    assert service._extract_status({}) is None


def test_notion_service_extract_date():
    service = NotionService.__new__(NotionService)

    props = {"Due": {"type": "date", "date": {"start": "2024-12-15"}}}
    assert service._extract_date(props) == "2024-12-15"

    props2 = {"Due Date": {"type": "date", "date": {"start": "2024-12-20T14:00:00"}}}
    assert service._extract_date(props2) == "2024-12-20T14:00:00"

    assert service._extract_date({}) is None


def test_notion_service_parse_page():
    service = NotionService.__new__(NotionService)
    page = {
        "id": "page-abc",
        "url": "https://notion.so/page-abc",
        "properties": {
            "Name": {"type": "title", "title": [{"plain_text": "Ship feature"}]},
            "Status": {"type": "status", "status": {"name": "In Progress"}},
            "Due": {"type": "date", "date": {"start": "2024-12-25"}},
            "Assignee": {"type": "people", "people": [{"name": "Bob"}]},
            "Tags": {"type": "multi_select", "multi_select": [{"name": "eng"}, {"name": "p1"}]},
        },
    }
    task = service._parse_page_as_task(page, "Sprint Board", "db1")
    assert task.page_id == "page-abc"
    assert task.title == "Ship feature"
    assert task.status == "In Progress"
    assert task.due_date_str == "2024-12-25"
    assert task.assignee == "Bob"
    assert task.database_name == "Sprint Board"
    assert task.tags == ["eng", "p1"]


def test_from_integration():
    class FakeIntegration:
        access_token = "ntn_test123"

    service = NotionService.from_integration(FakeIntegration())
    assert service.api_key == "ntn_test123"
    assert "Bearer ntn_test123" in service.headers["Authorization"]
