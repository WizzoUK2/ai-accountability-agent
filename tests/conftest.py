import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models.database import Base
from src.models.user import User  # noqa: F401
from src.models.integration import Integration  # noqa: F401
from src.models.task import Task  # noqa: F401


@pytest.fixture
async def engine():
    """Create an async in-memory SQLite engine for tests."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db(engine):
    """Provide an async database session for tests."""
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def sample_user(db):
    """Create a sample user for tests."""
    user = User(
        email="test@example.com",
        name="Test User",
        phone_number="+61400000000",
        slack_user_id="U12345",
        timezone="Australia/Sydney",
        morning_briefing_time="07:00",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
