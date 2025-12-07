from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.models.user import User
from src.models.integration import Integration, IntegrationType
from src.integrations.google_calendar import GoogleCalendarService
from src.integrations.google_gmail import GoogleGmailService
from src.integrations.twilio_sms import sms_service
from src.integrations.slack import slack_service
from src.services.ai_prioritization import ai_service

logger = structlog.get_logger()


class BriefingService:
    """Service for generating and sending briefings."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def generate_morning_briefing(self, user: User) -> dict:
        """Generate a morning briefing for a user."""
        logger.info("Generating morning briefing", user_email=user.email)

        briefing_data = {
            "user": user.email,
            "generated_at": datetime.now(ZoneInfo(user.timezone)).isoformat(),
            "calendar_events": [],
            "email_summary": {},
            "urgent_emails": [],
            "priorities": [],
        }

        # Get Google integration
        result = await self.db.execute(
            select(Integration).where(
                Integration.user_id == user.id,
                Integration.type == IntegrationType.GOOGLE,
                Integration.is_active,
            )
        )
        google_integrations = result.scalars().all()

        # Aggregate calendar events from all Google accounts
        all_events = []
        for integration in google_integrations:
            try:
                calendar_service = GoogleCalendarService.from_integration(integration)
                events = calendar_service.get_todays_events(user.timezone)
                for event in events:
                    event_dict = event.to_dict()
                    event_dict["time_range"] = event.format_time_range(user.timezone)
                    event_dict["account"] = integration.account_email
                    all_events.append(event_dict)
            except Exception as e:
                logger.error(
                    "Failed to fetch calendar events",
                    account=integration.account_email,
                    error=str(e),
                )

        # Sort all events by start time
        all_events.sort(key=lambda e: e["start"])
        briefing_data["calendar_events"] = all_events

        # Aggregate email summaries and urgent emails
        total_unread = 0
        total_important = 0
        all_urgent_emails = []

        for integration in google_integrations:
            try:
                gmail_service = GoogleGmailService.from_integration(integration)
                summary = gmail_service.get_inbox_summary()
                total_unread += summary.get("unread_count", 0)
                total_important += summary.get("important_unread_count", 0)

                # Get important unread emails
                important_emails = gmail_service.get_important_unread(max_results=5)
                for email in important_emails:
                    email_dict = email.to_dict()
                    email_dict["account"] = integration.account_email
                    all_urgent_emails.append(email_dict)

            except Exception as e:
                logger.error(
                    "Failed to fetch email data",
                    account=integration.account_email,
                    error=str(e),
                )

        briefing_data["email_summary"] = {
            "unread_count": total_unread,
            "important_unread_count": total_important,
        }
        briefing_data["urgent_emails"] = all_urgent_emails

        # Use AI to generate priorities
        try:
            priorities = await ai_service.generate_daily_priorities(
                calendar_events=all_events,
                urgent_emails=all_urgent_emails,
                email_summary=briefing_data["email_summary"],
            )
            briefing_data["priorities"] = priorities
        except Exception as e:
            logger.error("Failed to generate AI priorities", error=str(e))

        return briefing_data

    def format_sms_briefing(self, briefing: dict) -> str:
        """Format briefing data as SMS text."""
        lines = ["Good morning! Here's your day:"]
        lines.append("")

        # Calendar
        events = briefing.get("calendar_events", [])
        if events:
            lines.append(f"CALENDAR ({len(events)} events):")
            for event in events[:5]:
                time_range = event.get("time_range", "")
                summary = event.get("summary", "")[:30]
                lines.append(f"• {time_range}: {summary}")
            if len(events) > 5:
                lines.append(f"  (+{len(events) - 5} more)")
        else:
            lines.append("CALENDAR: Clear day!")

        lines.append("")

        # Email
        summary = briefing.get("email_summary", {})
        unread = summary.get("unread_count", 0)
        important = summary.get("important_unread_count", 0)
        lines.append(f"EMAIL: {unread} unread, {important} important")

        urgent = briefing.get("urgent_emails", [])
        if urgent:
            lines.append("Needs attention:")
            for email in urgent[:3]:
                sender = email.get("sender", "")[:15]
                subject = email.get("subject", "")[:25]
                lines.append(f"• {sender}: {subject}")

        # Priorities
        priorities = briefing.get("priorities", [])
        if priorities:
            lines.append("")
            lines.append("TODAY'S PRIORITIES:")
            for i, p in enumerate(priorities[:3], 1):
                lines.append(f"{i}. {p[:50]}")

        return "\n".join(lines)

    async def send_briefing(self, user: User, briefing: dict) -> dict:
        """Send briefing via configured channels."""
        results = {"sms": False, "slack": False}

        # Send SMS if phone number configured
        if user.phone_number:
            sms_text = self.format_sms_briefing(briefing)
            results["sms"] = sms_service.send_sms(user.phone_number, sms_text)

        # Send Slack if user ID configured
        if user.slack_user_id:
            blocks = slack_service.format_morning_briefing_blocks(
                calendar_events=briefing.get("calendar_events", []),
                urgent_emails=briefing.get("urgent_emails", []),
                email_summary=briefing.get("email_summary", {}),
                priorities=briefing.get("priorities", []),
            )
            results["slack"] = slack_service.send_dm(
                user.slack_user_id,
                "Here's your morning briefing",
                blocks=blocks,
            )

        logger.info("Briefing sent", user_email=user.email, results=results)
        return results
