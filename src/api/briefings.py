from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.models.database import get_db
from src.models.user import User
from src.services.briefing import BriefingService

router = APIRouter()
logger = structlog.get_logger()


@router.get("/{user_id}")
async def get_briefing(user_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Generate and return a briefing for a user (without sending)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    briefing_service = BriefingService(db)
    briefing = await briefing_service.generate_morning_briefing(user)

    return briefing


@router.post("/{user_id}/send")
async def send_briefing(user_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Generate and send a briefing to a user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    briefing_service = BriefingService(db)
    briefing = await briefing_service.generate_morning_briefing(user)
    results = await briefing_service.send_briefing(user, briefing)

    return {
        "status": "sent",
        "channels": results,
        "briefing": briefing,
    }


@router.get("/{user_id}/preview/sms")
async def preview_sms_briefing(user_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Preview what the SMS briefing would look like."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    briefing_service = BriefingService(db)
    briefing = await briefing_service.generate_morning_briefing(user)
    sms_text = briefing_service.format_sms_briefing(briefing)

    return {
        "sms_text": sms_text,
        "character_count": len(sms_text),
    }
