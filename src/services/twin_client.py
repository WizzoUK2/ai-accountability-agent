"""Client for the Wizzo Digital Twin API.

Calls the twin's /v1/prioritise, /v1/score-emails, and /v1/score-tasks
endpoints to get Craig-shaped decisions instead of generic Claude output.

Falls back to the existing AIPrioritizationService when the twin API is
unreachable, disabled, or returns an error.
"""

import hashlib
from datetime import datetime, timezone

import httpx
import structlog

from config import settings
from src.services.ai_prioritization import ai_service
from src.services.entity_matcher import match_entity

logger = structlog.get_logger()


class TwinClient:
    """Async HTTP client for the Digital Twin API."""

    def __init__(self) -> None:
        self.is_configured = bool(
            settings.twin_api_enabled
            and settings.twin_api_url
            and settings.twin_api_key
        )
        if self.is_configured:
            logger.info("Twin API client enabled", url=settings.twin_api_url)
        else:
            logger.info("Twin API not configured — will use generic AI fallback")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.twin_api_key}",
            "Content-Type": "application/json",
        }

    async def _post(self, endpoint: str, payload: dict) -> dict | None:
        """POST to twin API. Returns parsed JSON or None on failure."""
        url = f"{settings.twin_api_url.rstrip('/')}/v1/{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=settings.twin_api_timeout) as client:
                resp = await client.post(url, json=payload, headers=self._headers())
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException:
            logger.warning("Twin API timeout", endpoint=endpoint)
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Twin API HTTP error",
                endpoint=endpoint,
                status=e.response.status_code,
                body=e.response.text[:200],
            )
        except httpx.ConnectError:
            logger.warning("Twin API unreachable", endpoint=endpoint)
        except Exception as e:
            logger.error("Twin API unexpected error", endpoint=endpoint, error=str(e))
        return None

    # ------------------------------------------------------------------
    # Data adapters: agent dict shapes → Twin API request shapes
    # ------------------------------------------------------------------

    @staticmethod
    def _adapt_email(email: dict, index: int) -> dict:
        """Convert agent email dict to Twin API EmailItem shape."""
        sender = email.get("sender", email.get("from", ""))
        account = email.get("account", "")
        adapted = {
            "id": email.get("uid") or email.get("id") or hashlib.md5(
                f"{sender}{email.get('subject', '')}{index}".encode()
            ).hexdigest()[:12],
            "subject": email.get("subject", ""),
            "sender": sender,
            "preview": email.get("snippet", email.get("preview", ""))[:200],
            "received_at": email.get("date", datetime.now(timezone.utc).isoformat()),
        }
        # Tag with entity if we can match by account or sender domain
        entity = match_entity(account_email=account, sender_email=sender)
        if entity:
            adapted["entity"] = entity
        return adapted

    @staticmethod
    def _adapt_task(task: dict, index: int) -> dict:
        """Convert agent task dict to Twin API TaskItem shape."""
        client_name = task.get("client_name", task.get("project"))
        adapted = {
            "id": task.get("id") or str(index),
            "name": task.get("title", task.get("name", "")),
            "project": client_name,
            "due_on": task.get("due_date"),
            "assignee": task.get("assignee"),
            "notes": task.get("notes"),
        }
        # Tag with entity if we can match by project/client name
        entity = match_entity(project_name=client_name)
        if entity:
            adapted["entity"] = entity
        return adapted

    # ------------------------------------------------------------------
    # Public methods (drop-in replacements for ai_service calls)
    # ------------------------------------------------------------------

    async def generate_daily_priorities(
        self,
        calendar_events: list[dict],
        urgent_emails: list[dict],
        email_summary: dict,
        tasks: list[dict] | None = None,
    ) -> list[str]:
        """Get Craig-shaped daily priorities from the twin.

        Falls back to generic ai_service.generate_daily_priorities().
        """
        if not self.is_configured:
            return await ai_service.generate_daily_priorities(
                calendar_events, urgent_emails, email_summary, tasks
            )

        # Build the mixed items list the /v1/prioritise endpoint expects
        items = []
        for event in calendar_events[:10]:
            item = {
                "id": event.get("id", event.get("summary", "")),
                "type": "calendar",
                "name": event.get("summary", ""),
                "time_range": event.get("time_range", ""),
                "account": event.get("account", ""),
            }
            entity = match_entity(account_email=event.get("account", ""))
            if entity:
                item["entity"] = entity
            items.append(item)
        for i, email in enumerate(urgent_emails[:10]):
            adapted = self._adapt_email(email, i)
            adapted["type"] = "email"
            adapted["name"] = f"Email from {adapted['sender']}: {adapted['subject']}"
            items.append(adapted)
        for i, task in enumerate((tasks or [])[:10]):
            adapted = self._adapt_task(task, i)
            adapted["type"] = "task"
            items.append(adapted)

        context = f"Unread emails: {email_summary.get('unread_count', 0)}, important: {email_summary.get('important_unread_count', 0)}"

        result = await self._post("prioritise", {
            "items": items,
            "context": context,
            "sensitivity": "public",
        })

        if result:
            priorities = []
            craig_note = result.get("craig_note")
            if craig_note:
                priorities.append(craig_note)
            for item in result.get("items", []):
                reasoning = item.get("reasoning", "")
                action = item.get("suggested_action")
                line = action if action else reasoning
                if line:
                    priorities.append(line)
            if priorities:
                logger.info(
                    "Twin priorities generated",
                    count=len(priorities),
                    context_chunks=result.get("retrieved_context_count", 0),
                )
                return priorities[:5]

        logger.info("Falling back to generic AI for priorities")
        return await ai_service.generate_daily_priorities(
            calendar_events, urgent_emails, email_summary, tasks
        )

    async def analyze_email_urgency(self, emails: list[dict]) -> list[dict]:
        """Score emails with twin-aware urgency. Falls back to ai_service."""
        if not self.is_configured or not emails:
            return await ai_service.analyze_email_urgency(emails)

        adapted = [self._adapt_email(e, i) for i, e in enumerate(emails[:10])]

        result = await self._post("score-emails", {
            "emails": adapted,
            "sensitivity": "public",
        })

        if result and result.get("emails"):
            scored = result["emails"]
            score_by_id = {s["id"]: s for s in scored}
            for i, email in enumerate(emails[:10]):
                adapted_id = adapted[i]["id"]
                if adapted_id in score_by_id:
                    s = score_by_id[adapted_id]
                    email["urgency_score"] = max(1, min(10, s.get("urgency", 50) // 10))
                    email["urgency_reason"] = s.get("reasoning", "")
                    email["twin_category"] = s.get("category", "")
                    if s.get("suggested_reply"):
                        email["suggested_reply"] = s["suggested_reply"]

            emails.sort(key=lambda e: e.get("urgency_score", 5), reverse=True)
            logger.info(
                "Twin email scoring done",
                count=len(scored),
                context_chunks=result.get("retrieved_context_count", 0),
            )
            return emails

        logger.info("Falling back to generic AI for email scoring")
        return await ai_service.analyze_email_urgency(emails)

    async def generate_task_priorities(self, tasks: list[dict]) -> list[dict]:
        """Score tasks with twin-aware prioritisation. Falls back to ai_service."""
        if not self.is_configured or not tasks:
            return await ai_service.generate_task_priorities(tasks)

        adapted = [self._adapt_task(t, i) for i, t in enumerate(tasks[:20])]

        result = await self._post("score-tasks", {
            "tasks": adapted,
            "sensitivity": "public",
        })

        if result and result.get("tasks"):
            scored = result["tasks"]
            score_by_id = {s["id"]: s for s in scored}
            for i, task in enumerate(tasks[:20]):
                adapted_id = adapted[i]["id"]
                if adapted_id in score_by_id:
                    s = score_by_id[adapted_id]
                    task["ai_priority_score"] = s.get("priority", 50)
                    task["ai_priority_reason"] = s.get("reasoning", "")
                    task["twin_defer"] = s.get("defer", False)

            tasks.sort(key=lambda t: t.get("ai_priority_score", 50), reverse=True)
            logger.info(
                "Twin task scoring done",
                count=len(scored),
                context_chunks=result.get("retrieved_context_count", 0),
            )
            return tasks

        logger.info("Falling back to generic AI for task scoring")
        return await ai_service.generate_task_priorities(tasks)

    async def query(self, query: str, sensitivity: str = "public") -> str | None:
        """Open-ended query against the twin's second brain. Returns None on failure."""
        if not self.is_configured:
            return None
        result = await self._post("query", {
            "query": query,
            "sensitivity": sensitivity,
            "synthesise": True,
        })
        if result:
            return result.get("answer")
        return None


# Singleton
twin_client = TwinClient()
