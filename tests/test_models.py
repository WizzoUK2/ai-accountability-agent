from sqlalchemy import select

from src.models.user import User
from src.models.integration import Integration, IntegrationType
from src.models.task import Task, TaskSource, TaskPriority


async def test_create_user(db):
    user = User(email="alice@example.com", name="Alice", timezone="UTC")
    db.add(user)
    await db.commit()

    result = await db.execute(select(User).where(User.email == "alice@example.com"))
    fetched = result.scalar_one()
    assert fetched.name == "Alice"
    assert fetched.timezone == "UTC"
    assert fetched.morning_briefing_time == "07:00"


async def test_user_email_unique(db):
    user1 = User(email="dup@example.com", name="First")
    db.add(user1)
    await db.commit()

    user2 = User(email="dup@example.com", name="Second")
    db.add(user2)

    import sqlalchemy.exc
    import pytest

    with pytest.raises(sqlalchemy.exc.IntegrityError):
        await db.commit()


async def test_create_integration(db, sample_user):
    integration = Integration(
        user_id=sample_user.id,
        type=IntegrationType.GOOGLE,
        account_email="test@gmail.com",
        access_token="token123",
        refresh_token="refresh456",
        scopes="calendar.readonly,gmail.readonly",
        is_active=True,
    )
    db.add(integration)
    await db.commit()

    result = await db.execute(
        select(Integration).where(Integration.user_id == sample_user.id)
    )
    fetched = result.scalar_one()
    assert fetched.type == IntegrationType.GOOGLE
    assert fetched.access_token == "token123"
    assert fetched.is_active is True


async def test_create_task(db, sample_user):
    task = Task(
        user_id=sample_user.id,
        source=TaskSource.MANUAL,
        title="Write weekly report",
        client_name="Acme Corp",
        priority=TaskPriority.HIGH,
    )
    db.add(task)
    await db.commit()

    result = await db.execute(select(Task).where(Task.user_id == sample_user.id))
    fetched = result.scalar_one()
    assert fetched.title == "Write weekly report"
    assert fetched.source == TaskSource.MANUAL
    assert fetched.priority == TaskPriority.HIGH
    assert fetched.is_completed is False
    assert fetched.client_name == "Acme Corp"


async def test_task_ai_scoring(db, sample_user):
    task = Task(
        user_id=sample_user.id,
        source=TaskSource.ASANA,
        title="Deploy v2",
        external_id="asana-12345",
        ai_priority_score=85,
        ai_priority_reason="High-impact release with deadline",
    )
    db.add(task)
    await db.commit()

    result = await db.execute(select(Task).where(Task.external_id == "asana-12345"))
    fetched = result.scalar_one()
    assert fetched.ai_priority_score == 85
    assert "deadline" in fetched.ai_priority_reason


async def test_user_cascade_delete(db, sample_user):
    task = Task(
        user_id=sample_user.id,
        source=TaskSource.MANUAL,
        title="Some task",
    )
    integration = Integration(
        user_id=sample_user.id,
        type=IntegrationType.GOOGLE,
        access_token="token",
    )
    db.add_all([task, integration])
    await db.commit()

    await db.delete(sample_user)
    await db.commit()

    tasks = (await db.execute(select(Task))).scalars().all()
    integrations = (await db.execute(select(Integration))).scalars().all()
    assert len(tasks) == 0
    assert len(integrations) == 0
