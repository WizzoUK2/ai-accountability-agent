import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.models.integration import Integration, IntegrationType
from src.models.task import Task, TaskSource, TaskPriority
from src.integrations.asana import AsanaService, AsanaTask

logger = structlog.get_logger()


class AsanaSyncService:
    """Service for syncing Asana tasks into the local task database."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def sync_user_tasks(self, user_id: int) -> dict:
        """Sync all Asana tasks for a user. Returns sync summary."""
        result = await self.db.execute(
            select(Integration).where(
                Integration.user_id == user_id,
                Integration.type == IntegrationType.ASANA,
                Integration.is_active,
            )
        )
        integrations = result.scalars().all()

        if not integrations:
            logger.info("No active Asana integrations", user_id=user_id)
            return {"synced": 0, "created": 0, "updated": 0}

        total_created = 0
        total_updated = 0
        total_synced = 0

        for integration in integrations:
            try:
                service = AsanaService.from_integration(integration)
                workspaces = await service.get_workspaces()

                for workspace in workspaces:
                    tasks = await service.get_my_tasks(workspace["gid"])
                    for asana_task in tasks:
                        if asana_task.completed:
                            continue
                        created = await self._upsert_task(user_id, asana_task)
                        if created:
                            total_created += 1
                        else:
                            total_updated += 1
                        total_synced += 1

                logger.info(
                    "Asana sync complete for integration",
                    user_id=user_id,
                    account=integration.account_email,
                    synced=total_synced,
                )
            except Exception as e:
                logger.error(
                    "Failed to sync Asana tasks",
                    user_id=user_id,
                    error=str(e),
                )

        await self.db.commit()
        return {"synced": total_synced, "created": total_created, "updated": total_updated}

    async def _upsert_task(self, user_id: int, asana_task: AsanaTask) -> bool:
        """Create or update a local Task from an Asana task. Returns True if created."""
        external_id = f"asana:{asana_task.gid}"

        result = await self.db.execute(
            select(Task).where(
                Task.user_id == user_id,
                Task.external_id == external_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.title = asana_task.name
            existing.description = asana_task.notes
            existing.due_date = asana_task.due_date
            existing.client_name = asana_task.project_name
            existing.is_completed = asana_task.completed
            existing.raw_data = json.dumps(asana_task.to_dict())
            return False
        else:
            task = Task(
                user_id=user_id,
                external_id=external_id,
                source=TaskSource.ASANA,
                title=asana_task.name,
                description=asana_task.notes,
                client_name=asana_task.project_name,
                priority=TaskPriority.MEDIUM,
                due_date=asana_task.due_date,
                is_completed=asana_task.completed,
                raw_data=json.dumps(asana_task.to_dict()),
            )
            self.db.add(task)
            return True
