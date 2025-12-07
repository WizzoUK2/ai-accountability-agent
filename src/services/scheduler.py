from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
import structlog

from config import settings
from src.models.database import async_session
from src.models.user import User
from src.services.briefing import BriefingService

logger = structlog.get_logger()

scheduler = AsyncIOScheduler()


async def send_morning_briefings() -> None:
    """Send morning briefings to all users scheduled for this time."""
    logger.info("Running morning briefing job")

    async with async_session() as db:
        # Get current time in different timezones and find users due for briefing
        # For simplicity, we'll check all users and send to those whose briefing time matches
        result = await db.execute(select(User))
        users = result.scalars().all()

        for user in users:
            try:
                user_tz = ZoneInfo(user.timezone)
                now = datetime.now(user_tz)
                current_time = now.strftime("%H:%M")

                # Check if it's time for this user's briefing (within 5 min window)
                briefing_hour, briefing_min = map(int, user.morning_briefing_time.split(":"))
                current_hour, current_min = now.hour, now.minute

                # Simple time window check
                if current_hour == briefing_hour and abs(current_min - briefing_min) <= 5:
                    logger.info(
                        "Sending briefing to user",
                        user_email=user.email,
                        scheduled_time=user.morning_briefing_time,
                        current_time=current_time,
                    )

                    briefing_service = BriefingService(db)
                    briefing = await briefing_service.generate_morning_briefing(user)
                    await briefing_service.send_briefing(user, briefing)

            except Exception as e:
                logger.error(
                    "Failed to send briefing to user",
                    user_email=user.email,
                    error=str(e),
                )


async def check_urgent_items() -> None:
    """Check for urgent items and send alerts if needed."""
    logger.info("Running urgent items check")

    async with async_session() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()

        for user in users:
            try:
                # This will be expanded to check for:
                # - Calendar events starting soon
                # - Overdue tasks
                # - High-priority emails received
                pass
            except Exception as e:
                logger.error(
                    "Failed to check urgent items for user",
                    user_email=user.email,
                    error=str(e),
                )


async def start_scheduler() -> None:
    """Start the background scheduler."""
    # Morning briefing job - runs every 5 minutes to catch users in different timezones
    scheduler.add_job(
        send_morning_briefings,
        CronTrigger(minute="*/5"),
        id="morning_briefings",
        name="Send morning briefings",
        replace_existing=True,
    )

    # Urgent items check - runs every 15 minutes
    scheduler.add_job(
        check_urgent_items,
        CronTrigger(minute="*/15"),
        id="urgent_check",
        name="Check for urgent items",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with jobs", jobs=[j.id for j in scheduler.get_jobs()])


async def shutdown_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    scheduler.shutdown(wait=True)
    logger.info("Scheduler shutdown complete")


def get_scheduler() -> AsyncIOScheduler:
    """Get the scheduler instance."""
    return scheduler
