import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.models.integration import Integration, IntegrationType
from src.models.task import Task, TaskSource, TaskPriority
from src.integrations.notion import NotionService, NotionTask

logger = structlog.get_logger()


class NotionSyncService:
    """Service for syncing Notion tasks into the local task database."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def sync_user_tasks(self, user_id: int) -> dict:
        """Sync all Notion tasks for a user. Returns sync summary."""
        result = await self.db.execute(
            select(Integration).where(
                Integration.user_id == user_id,
                Integration.type == IntegrationType.NOTION,
                Integration.is_active,
            )
        )
        integrations = result.scalars().all()

        if not integrations:
            logger.info("No active Notion integrations", user_id=user_id)
            return {"synced": 0, "created": 0, "updated": 0}

        total_created = 0
        total_updated = 0
        total_synced = 0

        for integration in integrations:
            try:
                service = NotionService.from_integration(integration)
                databases = await service.get_databases()

                for db_info in databases:
                    db_id = db_info["id"]
                    db_name = db_info.get("title", [{}])
                    if isinstance(db_name, list) and db_name:
                        db_name = db_name[0].get("plain_text", "Untitled")
                    else:
                        db_name = "Untitled"

                    tasks = await service.get_tasks_from_database(db_id, db_name)
                    for notion_task in tasks:
                        if notion_task.is_completed:
                            continue
                        created = await self._upsert_task(user_id, notion_task)
                        if created:
                            total_created += 1
                        else:
                            total_updated += 1
                        total_synced += 1

                logger.info(
                    "Notion sync complete for integration",
                    user_id=user_id,
                    synced=total_synced,
                )
            except Exception as e:
                logger.error(
                    "Failed to sync Notion tasks",
                    user_id=user_id,
                    error=str(e),
                )

        await self.db.commit()
        return {"synced": total_synced, "created": total_created, "updated": total_updated}

    async def _upsert_task(self, user_id: int, notion_task: NotionTask) -> bool:
        """Create or update a local Task from a Notion task. Returns True if created."""
        external_id = f"notion:{notion_task.page_id}"

        result = await self.db.execute(
            select(Task).where(
                Task.user_id == user_id,
                Task.external_id == external_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.title = notion_task.title
            existing.due_date = notion_task.due_date
            existing.client_name = notion_task.database_name
            existing.is_completed = notion_task.is_completed
            existing.raw_data = json.dumps(notion_task.to_dict())
            return False
        else:
            task = Task(
                user_id=user_id,
                external_id=external_id,
                source=TaskSource.NOTION,
                title=notion_task.title,
                client_name=notion_task.database_name,
                priority=TaskPriority.MEDIUM,
                due_date=notion_task.due_date,
                is_completed=notion_task.is_completed,
                raw_data=json.dumps(notion_task.to_dict()),
            )
            self.db.add(task)
            return True
