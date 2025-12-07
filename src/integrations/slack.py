from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import structlog

from config import settings

logger = structlog.get_logger()


class SlackService:
    """Service for sending messages via Slack."""

    def __init__(self) -> None:
        if settings.slack_bot_token:
            self.client = WebClient(token=settings.slack_bot_token)
            self.user_id = settings.slack_user_id
            self.is_configured = True
        else:
            self.client = None
            self.user_id = None
            self.is_configured = False
            logger.warning("Slack not configured - Slack messaging disabled")

    def send_dm(self, user_id: str, message: str, blocks: list | None = None) -> bool:
        """Send a direct message to a user."""
        if not self.is_configured:
            logger.warning("Attempted to send Slack message but not configured")
            return False

        try:
            # Open a DM channel with the user
            response = self.client.conversations_open(users=[user_id])
            channel_id = response["channel"]["id"]

            # Send the message
            if blocks:
                self.client.chat_postMessage(
                    channel=channel_id,
                    text=message,
                    blocks=blocks,
                )
            else:
                self.client.chat_postMessage(
                    channel=channel_id,
                    text=message,
                )

            logger.info("Slack message sent", user_id=user_id)
            return True

        except SlackApiError as e:
            logger.error("Failed to send Slack message", user_id=user_id, error=str(e))
            return False

    def send_to_user(self, message: str, blocks: list | None = None) -> bool:
        """Send a message to the configured user."""
        if not self.user_id:
            logger.warning("No Slack user ID configured")
            return False

        return self.send_dm(self.user_id, message, blocks)

    def format_morning_briefing_blocks(
        self,
        calendar_events: list,
        urgent_emails: list,
        email_summary: dict,
        priorities: list | None = None,
    ) -> list:
        """Format a morning briefing as Slack blocks."""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Good Morning! Here's your briefing"},
            },
            {"type": "divider"},
        ]

        # Calendar section
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Today's Calendar*"},
            }
        )

        if calendar_events:
            event_text = ""
            for event in calendar_events[:10]:
                time_str = event.get("time_range", "")
                summary = event.get("summary", "No title")
                event_text += f"• {time_str} - {summary}\n"

            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": event_text},
                }
            )
        else:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "_No events scheduled_"},
                }
            )

        blocks.append({"type": "divider"})

        # Email section
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Email Summary*"},
            }
        )

        unread = email_summary.get("unread_count", 0)
        important = email_summary.get("important_unread_count", 0)
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"• Unread: {unread}\n• Important unread: {important}",
                },
            }
        )

        if urgent_emails:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*Needs attention:*"},
                }
            )
            for email in urgent_emails[:5]:
                sender = email.get("sender", "Unknown")
                subject = email.get("subject", "(no subject)")
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"• *{sender}*: {subject}",
                        },
                    }
                )

        # Priorities section
        if priorities:
            blocks.append({"type": "divider"})
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*Today's Priorities*"},
                }
            )
            for i, priority in enumerate(priorities[:5], 1):
                blocks.append(
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"{i}. {priority}"},
                    }
                )

        return blocks


# Singleton instance
slack_service = SlackService()
