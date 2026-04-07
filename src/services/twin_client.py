"""
twin_client.py — Client for the wizzo-digital-twin Twin API.

Drop-in replacement for generic Claude AI calls in ai_prioritization.py.
Configured via environment variables with graceful fallback to generic Claude
if the twin API is unavailable or not configured.
"""
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)


class TwinClient:
    """HTTP client for the Digital Twin API."""

    def __init__(self) -> None:
        self.enabled = settings.twin_api_enabled
        self.base_url = settings.twin_api_url
        self.headers = {
            "Authorization": f"Bearer {settings.twin_api_key}",
            "Content-Type": "application/json",
        }
        self.timeout = 30.0

        if self.enabled:
            logger.info("Twin API client enabled: %s", self.base_url)
        else:
            logger.info("Twin API client disabled — using generic Claude fallback")

    async def is_available(self) -> bool:
        if not self.enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/health")
                return r.status_code == 200
        except Exception:
            return False

    async def score_emails(self, emails: list[dict]) -> list[dict] | None:
        """Score emails via twin. Returns None on failure (caller falls back)."""
        if not self.enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base_url}/v1/score-emails",
                    headers=self.headers,
                    json={"emails": emails, "sensitivity": "public"},
                )
                r.raise_for_status()
                return r.json().get("emails", [])
        except Exception as e:
            logger.warning("Twin API score-emails failed: %s", e)
            return None

    async def score_tasks(self, tasks: list[dict]) -> list[dict] | None:
        """Score tasks via twin. Returns None on failure (caller falls back)."""
        if not self.enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base_url}/v1/score-tasks",
                    headers=self.headers,
                    json={"tasks": tasks, "sensitivity": "public"},
                )
                r.raise_for_status()
                return r.json().get("tasks", [])
        except Exception as e:
            logger.warning("Twin API score-tasks failed: %s", e)
            return None

    async def prioritise(self, items: list[dict], context: str | None = None) -> dict | None:
        """Full prioritisation with Craig's voice. Returns None on failure."""
        if not self.enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base_url}/v1/prioritise",
                    headers=self.headers,
                    json={
                        "items": items,
                        "context": context,
                        "sensitivity": "public",
                    },
                )
                r.raise_for_status()
                return r.json()
        except Exception as e:
            logger.warning("Twin API prioritise failed: %s", e)
            return None

    async def query(self, query: str, sensitivity: str = "public") -> str | None:
        """Open-ended query against the second brain. Returns None on failure."""
        if not self.enabled:
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.base_url}/v1/query",
                    headers=self.headers,
                    json={"query": query, "sensitivity": sensitivity, "synthesise": True},
                )
                r.raise_for_status()
                return r.json().get("answer")
        except Exception as e:
            logger.warning("Twin API query failed: %s", e)
            return None


# Singleton
twin_client = TwinClient()
