from datetime import datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from src.models.integration import Integration, IntegrationType
from src.models.task import Task, TaskSource
from src.integrations.asana import AsanaTask
from src.services.asana_sync import AsanaSyncService


async def test_sync_creates_tasks(db, sample_user):
    """Test that syncing creates local tasks from Asana."""
    # Add Asana integration
    integration = Integration(
        user_id=sample_user.id,
        type=IntegrationType.ASANA,
        access_token="fake-token",
        account_email="test@example.com",
        is_active=True,
    )
    db.add(integration)
    await db.commit()

    mock_tasks = [
        AsanaTask(gid="1", name="Write proposal", project_name="Client A", due_on="2024-12-15"),
        AsanaTask(gid="2", name="Review PR", project_name="Client B"),
    ]

    with patch("src.services.asana_sync.AsanaService") as MockService:
        mock_instance = MockService.from_integration.return_value
        mock_instance.get_workspaces = AsyncMock(return_value=[{"gid": "ws1"}])
        mock_instance.get_my_tasks = AsyncMock(return_value=mock_tasks)

        sync = AsanaSyncService(db)
        result = await sync.sync_user_tasks(sample_user.id)

    assert result["created"] == 2
    assert result["synced"] == 2

    tasks = (await db.execute(select(Task).where(Task.user_id == sample_user.id))).scalars().all()
    assert len(tasks) == 2
    assert tasks[0].source == TaskSource.ASANA
    assert tasks[0].external_id == "asana:1"
    assert tasks[0].client_name == "Client A"


async def test_sync_updates_existing_tasks(db, sample_user):
    """Test that syncing updates existing tasks instead of duplicating."""
    integration = Integration(
        user_id=sample_user.id,
        type=IntegrationType.ASANA,
        access_token="fake-token",
        is_active=True,
    )
    db.add(integration)

    existing_task = Task(
        user_id=sample_user.id,
        external_id="asana:1",
        source=TaskSource.ASANA,
        title="Old title",
    )
    db.add(existing_task)
    await db.commit()

    mock_tasks = [
        AsanaTask(gid="1", name="Updated title", project_name="New Client"),
    ]

    with patch("src.services.asana_sync.AsanaService") as MockService:
        mock_instance = MockService.from_integration.return_value
        mock_instance.get_workspaces = AsyncMock(return_value=[{"gid": "ws1"}])
        mock_instance.get_my_tasks = AsyncMock(return_value=mock_tasks)

        sync = AsanaSyncService(db)
        result = await sync.sync_user_tasks(sample_user.id)

    assert result["updated"] == 1
    assert result["created"] == 0

    tasks = (await db.execute(select(Task).where(Task.user_id == sample_user.id))).scalars().all()
    assert len(tasks) == 1
    assert tasks[0].title == "Updated title"
    assert tasks[0].client_name == "New Client"


async def test_sync_skips_completed_tasks(db, sample_user):
    """Test that completed Asana tasks are not synced."""
    integration = Integration(
        user_id=sample_user.id,
        type=IntegrationType.ASANA,
        access_token="fake-token",
        is_active=True,
    )
    db.add(integration)
    await db.commit()

    mock_tasks = [
        AsanaTask(gid="1", name="Done task", completed=True),
        AsanaTask(gid="2", name="Active task", completed=False),
    ]

    with patch("src.services.asana_sync.AsanaService") as MockService:
        mock_instance = MockService.from_integration.return_value
        mock_instance.get_workspaces = AsyncMock(return_value=[{"gid": "ws1"}])
        mock_instance.get_my_tasks = AsyncMock(return_value=mock_tasks)

        sync = AsanaSyncService(db)
        result = await sync.sync_user_tasks(sample_user.id)

    assert result["synced"] == 1
    tasks = (await db.execute(select(Task).where(Task.user_id == sample_user.id))).scalars().all()
    assert len(tasks) == 1
    assert tasks[0].title == "Active task"


async def test_sync_no_integrations(db, sample_user):
    """Test sync returns zeros when no Asana integrations exist."""
    sync = AsanaSyncService(db)
    result = await sync.sync_user_tasks(sample_user.id)
    assert result == {"synced": 0, "created": 0, "updated": 0}
