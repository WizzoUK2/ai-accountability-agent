from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
import structlog

from config import settings
from src.models.database import async_session
from src.models.user import User
from src.models.task import Task
from src.models.integration import Integration, IntegrationType
from src.integrations.google_calendar import GoogleCalendarService
from src.integrations.google_gmail import GoogleGmailService
from src.integrations.spark_email import SparkEmailService
from src.integrations.twilio_sms import sms_service
from src.integrations.slack import slack_service
from src.services.briefing import BriefingService

spark_email = SparkEmailService()

logger = structlog.get_logger()

scheduler = AsyncIOScheduler()

# Alert deduplication: {user_id: {item_key: last_alert_datetime}}
_alert_history: dict[int, dict[str, datetime]] = {}
ALERT_COOLDOWN = timedelta(minutes=60)


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


def _should_alert(user_id: int, item_key: str) -> bool:
    """Check if we should send an alert (respects cooldown)."""
    now = datetime.now()
    user_history = _alert_history.get(user_id, {})
    last_sent = user_history.get(item_key)
    if last_sent and (now - last_sent) < ALERT_COOLDOWN:
        return False
    return True


def _record_alert(user_id: int, item_key: str) -> None:
    """Record that an alert was sent."""
    if user_id not in _alert_history:
        _alert_history[user_id] = {}
    _alert_history[user_id][item_key] = datetime.now()


async def check_urgent_items() -> None:
    """Check for urgent items and send alerts if needed."""
    logger.info("Running urgent items check")

    async with async_session() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()

        for user in users:
            try:
                urgent_items = []
                user_tz = user.timezone or "UTC"

                # Check calendar events starting within 15 minutes
                integrations_result = await db.execute(
                    select(Integration).where(
                        Integration.user_id == user.id,
                        Integration.type == IntegrationType.GOOGLE,
                        Integration.is_active,
                    )
                )
                google_integrations = integrations_result.scalars().all()

                for integration in google_integrations:
                    try:
                        cal_service = GoogleCalendarService.from_integration(integration)
                        upcoming = cal_service.get_upcoming_events(hours=1, timezone=user_tz)
                        now = datetime.now(ZoneInfo(user_tz))
                        for event in upcoming:
                            if event.start and not event.is_all_day:
                                minutes_until = (event.start - now).total_seconds() / 60
                                if 0 < minutes_until <= 15:
                                    item_key = f"cal:{event.id}"
                                    if _should_alert(user.id, item_key):
                                        urgent_items.append({
                                            "type": "calendar",
                                            "title": event.summary,
                                            "detail": f"Starts in {int(minutes_until)} min",
                                            "meeting_link": event.meeting_link,
                                            "key": item_key,
                                        })
                    except Exception as e:
                        logger.warning(
                            "Failed to check calendar for urgent items",
                            account=integration.account_email,
                            error=str(e),
                        )

                # Check overdue tasks
                now_utc = datetime.utcnow()
                tasks_result = await db.execute(
                    select(Task).where(
                        Task.user_id == user.id,
                        Task.is_completed == False,  # noqa: E712
                        Task.due_date < now_utc,
                    )
                )
                overdue_tasks = tasks_result.scalars().all()
                for task in overdue_tasks:
                    item_key = f"task:{task.id}"
                    if _should_alert(user.id, item_key):
                        urgent_items.append({
                            "type": "overdue_task",
                            "title": task.title,
                            "detail": f"Due: {task.due_date.strftime('%b %d')}",
                            "client": task.client_name,
                            "key": item_key,
                        })

                # Check for urgent emails via SparkEmail MCP
                if spark_email.is_configured:
                    try:
                        urgent_emails = await spark_email.find_urgent_emails(hours=1, limit=5)
                        for email in urgent_emails:
                            subject = email.get("subject", "(no subject)")
                            sender = email.get("from", "unknown")
                            item_key = f"email:{email.get('uid', subject)}"
                            if _should_alert(user.id, item_key):
                                urgent_items.append({
                                    "type": "urgent_email",
                                    "title": subject,
                                    "detail": f"From: {sender}",
                                    "client": email.get("account", ""),
                                    "key": item_key,
                                })
                    except Exception as e:
                        logger.warning("Failed to check SparkEmail for urgent items", error=str(e))

                # Send alerts if there are urgent items
                if urgent_items:
                    logger.info(
                        "Found urgent items",
                        user_email=user.email,
                        count=len(urgent_items),
                    )
                    await _send_urgent_alerts(user, urgent_items)
                    for item in urgent_items:
                        _record_alert(user.id, item["key"])

            except Exception as e:
                logger.error(
                    "Failed to check urgent items for user",
                    user_email=user.email,
                    error=str(e),
                )


async def _send_urgent_alerts(user: User, items: list[dict]) -> None:
    """Send urgent item alerts via SMS and Slack."""
    # Format SMS
    if user.phone_number:
        lines = [f"ALERT: {len(items)} urgent item(s)"]
        for item in items[:5]:
            emoji = "📅" if item["type"] == "calendar" else "⚠️"
            lines.append(f"{emoji} {item['title']} - {item['detail']}")
        sms_service.send_sms(user.phone_number, "\n".join(lines))

    # Format Slack
    if user.slack_user_id:
        blocks = slack_service.format_urgent_alert_blocks(items)
        slack_service.send_dm(
            user.slack_user_id,
            f"Urgent: {len(items)} item(s) need attention",
            blocks=blocks,
        )


async def sync_external_tasks() -> None:
    """Sync tasks from Asana and Notion for all users."""
    logger.info("Running external task sync")

    async with async_session() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()

        for user in users:
            try:
                # Sync Asana
                from src.services.asana_sync import AsanaSyncService

                asana_sync = AsanaSyncService(db)
                asana_result = await asana_sync.sync_user_tasks(user.id)
                if asana_result["synced"] > 0:
                    logger.info(
                        "Asana sync complete",
                        user_email=user.email,
                        **asana_result,
                    )

                # Sync Notion
                from src.services.notion_sync import NotionSyncService

                notion_sync = NotionSyncService(db)
                notion_result = await notion_sync.sync_user_tasks(user.id)
                if notion_result["synced"] > 0:
                    logger.info(
                        "Notion sync complete",
                        user_email=user.email,
                        **notion_result,
                    )

            except Exception as e:
                logger.error(
                    "Failed to sync tasks for user",
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

    # External task sync - runs every 30 minutes
    scheduler.add_job(
        sync_external_tasks,
        CronTrigger(minute="*/30"),
        id="external_sync",
        name="Sync Asana and Notion tasks",
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
