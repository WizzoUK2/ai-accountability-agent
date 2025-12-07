from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.models.database import get_db
from src.models.user import User
from src.models.task import Task, TaskPriority
from src.services.ai_prioritization import ai_service

router = APIRouter()
logger = structlog.get_logger()


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    client_name: str | None = None
    due_date: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    client_name: str | None = None
    due_date: str | None = None
    priority: TaskPriority | None = None
    is_completed: bool | None = None


@router.get("/{user_id}")
async def get_user_tasks(
    user_id: int,
    include_completed: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get all tasks for a user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    query = select(Task).where(Task.user_id == user_id)
    if not include_completed:
        query = query.where(Task.is_completed == False)

    query = query.order_by(Task.due_date.asc().nullslast(), Task.priority.desc())

    result = await db.execute(query)
    tasks = result.scalars().all()

    return {
        "user_id": user_id,
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "client_name": t.client_name,
                "source": t.source.value,
                "priority": t.priority.value,
                "ai_priority_score": t.ai_priority_score,
                "ai_priority_reason": t.ai_priority_reason,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "is_completed": t.is_completed,
                "is_urgent": t.is_urgent,
            }
            for t in tasks
        ],
    }


@router.post("/{user_id}/prioritize")
async def prioritize_tasks(user_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Use AI to prioritize all tasks for a user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get incomplete tasks
    result = await db.execute(
        select(Task).where(Task.user_id == user_id, Task.is_completed == False)
    )
    tasks = result.scalars().all()

    if not tasks:
        return {"message": "No tasks to prioritize", "tasks": []}

    # Convert to dicts for AI processing
    task_dicts = [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "client_name": t.client_name,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "source": t.source.value,
        }
        for t in tasks
    ]

    # Get AI priorities
    prioritized = await ai_service.generate_task_priorities(task_dicts)

    # Update tasks with AI scores
    task_map = {t.id: t for t in tasks}
    for p in prioritized:
        task_id = p.get("id")
        if task_id in task_map:
            task_map[task_id].ai_priority_score = p.get("ai_priority_score")
            task_map[task_id].ai_priority_reason = p.get("ai_priority_reason")

    await db.commit()

    return {
        "message": f"Prioritized {len(tasks)} tasks",
        "tasks": prioritized,
    }


@router.get("/{user_id}/by-client")
async def get_tasks_by_client(user_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Get tasks grouped by client."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = await db.execute(
        select(Task).where(Task.user_id == user_id, Task.is_completed == False)
    )
    tasks = result.scalars().all()

    # Group by client
    by_client: dict[str, list] = {}
    for task in tasks:
        client = task.client_name or "No Client"
        if client not in by_client:
            by_client[client] = []
        by_client[client].append(
            {
                "id": task.id,
                "title": task.title,
                "priority": task.priority.value,
                "due_date": task.due_date.isoformat() if task.due_date else None,
            }
        )

    return {
        "user_id": user_id,
        "clients": by_client,
        "client_count": len(by_client),
        "total_tasks": len(tasks),
    }
