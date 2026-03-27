from datetime import datetime

import httpx
import structlog

logger = structlog.get_logger()

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionTask:
    """Represents a task-like item from a Notion database."""

    def __init__(
        self,
        page_id: str,
        title: str,
        status: str | None = None,
        due_date: str | None = None,
        assignee: str | None = None,
        database_name: str | None = None,
        database_id: str | None = None,
        url: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        self.page_id = page_id
        self.title = title
        self.status = status
        self.due_date_str = due_date
        self.assignee = assignee
        self.database_name = database_name
        self.database_id = database_id
        self.url = url
        self.tags = tags or []

    @property
    def due_date(self) -> datetime | None:
        if self.due_date_str:
            try:
                return datetime.fromisoformat(self.due_date_str.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    @property
    def is_completed(self) -> bool:
        if not self.status:
            return False
        return self.status.lower() in ("done", "complete", "completed", "closed")

    def to_dict(self) -> dict:
        return {
            "page_id": self.page_id,
            "title": self.title,
            "status": self.status,
            "due_date": self.due_date_str,
            "assignee": self.assignee,
            "database_name": self.database_name,
            "database_id": self.database_id,
            "url": self.url,
            "tags": self.tags,
        }


class NotionService:
    """Service for interacting with the Notion API."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    @classmethod
    def from_integration(cls, integration) -> "NotionService":
        """Create service from an Integration model."""
        return cls(api_key=integration.access_token)

    async def _get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{NOTION_API_BASE}{path}",
                headers=self.headers,
                params=params or {},
            )
            response.raise_for_status()
            return response.json()

    async def _post(self, path: str, data: dict) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{NOTION_API_BASE}{path}",
                headers=self.headers,
                json=data,
            )
            response.raise_for_status()
            return response.json()

    async def _patch(self, path: str, data: dict) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{NOTION_API_BASE}{path}",
                headers=self.headers,
                json=data,
            )
            response.raise_for_status()
            return response.json()

    async def get_me(self) -> dict:
        """Get info about the integration/bot user."""
        return await self._get("/users/me")

    async def get_databases(self) -> list[dict]:
        """Search for all databases accessible to the integration."""
        result = await self._post("/search", data={"filter": {"property": "object", "value": "database"}})
        return result.get("results", [])

    async def query_database(
        self,
        database_id: str,
        filter_obj: dict | None = None,
    ) -> list[dict]:
        """Query a Notion database with optional filter."""
        body: dict = {}
        if filter_obj:
            body["filter"] = filter_obj
        result = await self._post(f"/databases/{database_id}/query", data=body)
        return result.get("results", [])

    async def get_tasks_from_database(self, database_id: str, database_name: str = "") -> list[NotionTask]:
        """Extract task-like items from a Notion database."""
        pages = await self.query_database(database_id)
        tasks = []
        for page in pages:
            task = self._parse_page_as_task(page, database_name, database_id)
            if task:
                tasks.append(task)
        return tasks

    async def update_page(self, page_id: str, properties: dict) -> dict:
        """Update properties on a Notion page."""
        return await self._patch(f"/pages/{page_id}", data={"properties": properties})

    def _parse_page_as_task(self, page: dict, database_name: str, database_id: str) -> NotionTask | None:
        """Parse a Notion page into a NotionTask, handling flexible schemas."""
        try:
            props = page.get("properties", {})
            title = self._extract_title(props)
            if not title:
                return None

            status = self._extract_status(props)
            due_date = self._extract_date(props)
            assignee = self._extract_person(props)
            tags = self._extract_tags(props)

            return NotionTask(
                page_id=page["id"],
                title=title,
                status=status,
                due_date=due_date,
                assignee=assignee,
                database_name=database_name,
                database_id=database_id,
                url=page.get("url"),
                tags=tags,
            )
        except Exception as e:
            logger.warning("Failed to parse Notion page", page_id=page.get("id"), error=str(e))
            return None

    def _extract_title(self, props: dict) -> str | None:
        """Extract the title from page properties (handles different property names)."""
        for name in ("Name", "Title", "Task", "name", "title", "task"):
            prop = props.get(name)
            if prop and prop.get("type") == "title":
                title_arr = prop.get("title", [])
                if title_arr:
                    return title_arr[0].get("plain_text", "")
        # Fallback: find any title-type property
        for prop in props.values():
            if isinstance(prop, dict) and prop.get("type") == "title":
                title_arr = prop.get("title", [])
                if title_arr:
                    return title_arr[0].get("plain_text", "")
        return None

    def _extract_status(self, props: dict) -> str | None:
        """Extract status from properties."""
        for name in ("Status", "status", "State", "state"):
            prop = props.get(name)
            if not prop:
                continue
            if prop.get("type") == "status":
                status_obj = prop.get("status")
                if status_obj:
                    return status_obj.get("name")
            elif prop.get("type") == "select":
                select_obj = prop.get("select")
                if select_obj:
                    return select_obj.get("name")
        return None

    def _extract_date(self, props: dict) -> str | None:
        """Extract due date from properties."""
        for name in ("Due", "Due Date", "due", "due_date", "Date", "Deadline"):
            prop = props.get(name)
            if prop and prop.get("type") == "date":
                date_obj = prop.get("date")
                if date_obj:
                    return date_obj.get("start")
        return None

    def _extract_person(self, props: dict) -> str | None:
        """Extract assignee from properties."""
        for name in ("Assignee", "assignee", "Assign", "Owner", "Person"):
            prop = props.get(name)
            if prop and prop.get("type") == "people":
                people = prop.get("people", [])
                if people:
                    return people[0].get("name")
        return None

    def _extract_tags(self, props: dict) -> list[str]:
        """Extract tags from properties."""
        for name in ("Tags", "tags", "Labels", "labels", "Category"):
            prop = props.get(name)
            if prop and prop.get("type") == "multi_select":
                return [opt.get("name", "") for opt in prop.get("multi_select", [])]
        return []
