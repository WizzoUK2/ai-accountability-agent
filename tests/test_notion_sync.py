from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from src.models.integration import Integration, IntegrationType
from src.models.task import Task, TaskSource
from src.integrations.notion import NotionTask
from src.services.notion_sync import NotionSyncService


async def test_sync_creates_tasks(db, sample_user):
    """Test that syncing creates local tasks from Notion."""
    integration = Integration(
        user_id=sample_user.id,
        type=IntegrationType.NOTION,
        access_token="fake-token",
        account_email="test@example.com",
        is_active=True,
    )
    db.add(integration)
    await db.commit()

    mock_tasks = [
        NotionTask(page_id="p1", title="Design mockups", database_name="Project Alpha", due_date="2024-12-20"),
        NotionTask(page_id="p2", title="Write docs", database_name="Project Beta"),
    ]

    with patch("src.services.notion_sync.NotionService") as MockService:
        mock_instance = MockService.from_integration.return_value
        mock_instance.get_databases = AsyncMock(return_value=[
            {"id": "db1", "title": [{"plain_text": "My Tasks"}]},
        ])
        mock_instance.get_tasks_from_database = AsyncMock(return_value=mock_tasks)

        sync = NotionSyncService(db)
        result = await sync.sync_user_tasks(sample_user.id)

    assert result["created"] == 2
    assert result["synced"] == 2

    tasks = (await db.execute(select(Task).where(Task.user_id == sample_user.id))).scalars().all()
    assert len(tasks) == 2
    assert tasks[0].source == TaskSource.NOTION
    assert tasks[0].external_id == "notion:p1"


async def test_sync_updates_existing(db, sample_user):
    """Test that syncing updates existing tasks."""
    integration = Integration(
        user_id=sample_user.id,
        type=IntegrationType.NOTION,
        access_token="fake-token",
        is_active=True,
    )
    db.add(integration)

    existing = Task(
        user_id=sample_user.id,
        external_id="notion:p1",
        source=TaskSource.NOTION,
        title="Old title",
    )
    db.add(existing)
    await db.commit()

    mock_tasks = [
        NotionTask(page_id="p1", title="New title", database_name="Updated DB"),
    ]

    with patch("src.services.notion_sync.NotionService") as MockService:
        mock_instance = MockService.from_integration.return_value
        mock_instance.get_databases = AsyncMock(return_value=[
            {"id": "db1", "title": [{"plain_text": "DB"}]},
        ])
        mock_instance.get_tasks_from_database = AsyncMock(return_value=mock_tasks)

        sync = NotionSyncService(db)
        result = await sync.sync_user_tasks(sample_user.id)

    assert result["updated"] == 1
    assert result["created"] == 0

    tasks = (await db.execute(select(Task).where(Task.user_id == sample_user.id))).scalars().all()
    assert len(tasks) == 1
    assert tasks[0].title == "New title"


async def test_sync_skips_completed(db, sample_user):
    """Test that completed Notion tasks are skipped."""
    integration = Integration(
        user_id=sample_user.id,
        type=IntegrationType.NOTION,
        access_token="fake-token",
        is_active=True,
    )
    db.add(integration)
    await db.commit()

    mock_tasks = [
        NotionTask(page_id="p1", title="Done", status="Done"),
        NotionTask(page_id="p2", title="Active", status="In Progress"),
    ]

    with patch("src.services.notion_sync.NotionService") as MockService:
        mock_instance = MockService.from_integration.return_value
        mock_instance.get_databases = AsyncMock(return_value=[
            {"id": "db1", "title": [{"plain_text": "DB"}]},
        ])
        mock_instance.get_tasks_from_database = AsyncMock(return_value=mock_tasks)

        sync = NotionSyncService(db)
        result = await sync.sync_user_tasks(sample_user.id)

    assert result["synced"] == 1


async def test_sync_no_integrations(db, sample_user):
    """Test sync returns zeros when no Notion integrations exist."""
    sync = NotionSyncService(db)
    result = await sync.sync_user_tasks(sample_user.id)
    assert result == {"synced": 0, "created": 0, "updated": 0}
