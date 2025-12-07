import json

from anthropic import Anthropic
import structlog

from config import settings

logger = structlog.get_logger()


class AIPrioritizationService:
    """Service for AI-powered prioritization and insights."""

    def __init__(self) -> None:
        if settings.anthropic_api_key:
            self.client = Anthropic(api_key=settings.anthropic_api_key)
            self.is_configured = True
        else:
            self.client = None
            self.is_configured = False
            logger.warning("Anthropic not configured - AI features disabled")

    async def generate_daily_priorities(
        self,
        calendar_events: list[dict],
        urgent_emails: list[dict],
        email_summary: dict,
        tasks: list[dict] | None = None,
    ) -> list[str]:
        """Generate prioritized list of things to focus on today."""
        if not self.is_configured:
            return []

        # Prepare context for Claude
        context = self._prepare_context(calendar_events, urgent_emails, email_summary, tasks)

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system="""You are an executive assistant helping prioritize someone's day.
Based on their calendar, emails, and tasks, identify the 3-5 most important things they should focus on today.
Be specific and actionable. Consider deadlines, meeting prep needs, and urgent communications.
Return your response as a JSON array of strings, each being a priority item. Nothing else.""",
                messages=[
                    {
                        "role": "user",
                        "content": f"Here's my day:\n\n{context}\n\nWhat should I prioritize today?",
                    }
                ],
            )

            # Parse the response
            response_text = response.content[0].text.strip()

            # Try to extract JSON array
            if response_text.startswith("["):
                priorities = json.loads(response_text)
            else:
                # If not valid JSON, try to find array in response
                import re

                match = re.search(r"\[.*\]", response_text, re.DOTALL)
                if match:
                    priorities = json.loads(match.group())
                else:
                    # Fall back to splitting by newlines
                    priorities = [
                        line.strip().lstrip("0123456789.-) ")
                        for line in response_text.split("\n")
                        if line.strip()
                    ]

            logger.info("Generated daily priorities", count=len(priorities))
            return priorities[:5]  # Limit to 5 priorities

        except Exception as e:
            logger.error("Failed to generate priorities", error=str(e))
            return []

    async def analyze_email_urgency(self, emails: list[dict]) -> list[dict]:
        """Analyze emails and score their urgency."""
        if not self.is_configured or not emails:
            return emails

        email_summaries = []
        for email in emails[:10]:  # Limit to prevent token overflow
            email_summaries.append(
                {
                    "sender": email.get("sender", ""),
                    "subject": email.get("subject", ""),
                    "snippet": email.get("snippet", "")[:200],
                }
            )

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system="""Analyze these emails and score their urgency from 1-10.
Consider: time-sensitivity, sender importance, action required, and potential consequences of delay.
Return a JSON array with objects containing "index" (0-based) and "urgency_score" (1-10) and "reason" (brief explanation).""",
                messages=[
                    {
                        "role": "user",
                        "content": f"Analyze these emails:\n\n{json.dumps(email_summaries, indent=2)}",
                    }
                ],
            )

            response_text = response.content[0].text.strip()

            # Parse urgency scores
            import re

            match = re.search(r"\[.*\]", response_text, re.DOTALL)
            if match:
                scores = json.loads(match.group())
                for score_data in scores:
                    idx = score_data.get("index", -1)
                    if 0 <= idx < len(emails):
                        emails[idx]["urgency_score"] = score_data.get("urgency_score", 5)
                        emails[idx]["urgency_reason"] = score_data.get("reason", "")

            # Sort by urgency
            emails.sort(key=lambda e: e.get("urgency_score", 5), reverse=True)
            return emails

        except Exception as e:
            logger.error("Failed to analyze email urgency", error=str(e))
            return emails

    async def generate_task_priorities(self, tasks: list[dict]) -> list[dict]:
        """Analyze tasks and assign priority scores."""
        if not self.is_configured or not tasks:
            return tasks

        task_summaries = []
        for task in tasks[:20]:
            task_summaries.append(
                {
                    "title": task.get("title", ""),
                    "due_date": task.get("due_date"),
                    "client": task.get("client_name"),
                    "source": task.get("source"),
                }
            )

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system="""Analyze these tasks and assign priority scores from 0-100.
Consider: due date proximity, client importance (if any), task complexity, and dependencies.
Return a JSON array with objects containing "index" (0-based), "priority_score" (0-100), and "reason" (brief explanation).""",
                messages=[
                    {
                        "role": "user",
                        "content": f"Prioritize these tasks:\n\n{json.dumps(task_summaries, indent=2)}",
                    }
                ],
            )

            response_text = response.content[0].text.strip()

            import re

            match = re.search(r"\[.*\]", response_text, re.DOTALL)
            if match:
                scores = json.loads(match.group())
                for score_data in scores:
                    idx = score_data.get("index", -1)
                    if 0 <= idx < len(tasks):
                        tasks[idx]["ai_priority_score"] = score_data.get("priority_score", 50)
                        tasks[idx]["ai_priority_reason"] = score_data.get("reason", "")

            # Sort by priority
            tasks.sort(key=lambda t: t.get("ai_priority_score", 50), reverse=True)
            return tasks

        except Exception as e:
            logger.error("Failed to prioritize tasks", error=str(e))
            return tasks

    def _prepare_context(
        self,
        calendar_events: list[dict],
        urgent_emails: list[dict],
        email_summary: dict,
        tasks: list[dict] | None,
    ) -> str:
        """Prepare context string for AI analysis."""
        sections = []

        # Calendar
        if calendar_events:
            cal_lines = ["CALENDAR:"]
            for event in calendar_events[:10]:
                time_range = event.get("time_range", "")
                summary = event.get("summary", "")
                cal_lines.append(f"  - {time_range}: {summary}")
            sections.append("\n".join(cal_lines))
        else:
            sections.append("CALENDAR: No events today")

        # Emails
        unread = email_summary.get("unread_count", 0)
        important = email_summary.get("important_unread_count", 0)
        sections.append(f"EMAIL: {unread} unread, {important} marked important")

        if urgent_emails:
            email_lines = ["IMPORTANT EMAILS:"]
            for email in urgent_emails[:5]:
                sender = email.get("sender", "")
                subject = email.get("subject", "")
                email_lines.append(f"  - From {sender}: {subject}")
            sections.append("\n".join(email_lines))

        # Tasks
        if tasks:
            task_lines = ["TASKS:"]
            for task in tasks[:10]:
                title = task.get("title", "")
                due = task.get("due_date", "no due date")
                task_lines.append(f"  - {title} (due: {due})")
            sections.append("\n".join(task_lines))

        return "\n\n".join(sections)


# Singleton instance
ai_service = AIPrioritizationService()
