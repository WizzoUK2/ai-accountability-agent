from datetime import datetime

import httpx
import structlog

logger = structlog.get_logger()

ASANA_API_BASE = "https://app.asana.com/api/1.0"


class AsanaTask:
    """Represents an Asana task."""

    def __init__(
        self,
        gid: str,
        name: str,
        completed: bool = False,
        due_on: str | None = None,
        due_at: str | None = None,
        notes: str | None = None,
        assignee_name: str | None = None,
        project_name: str | None = None,
        project_gid: str | None = None,
        tags: list[str] | None = None,
        permalink_url: str | None = None,
    ) -> None:
        self.gid = gid
        self.name = name
        self.completed = completed
        self.due_on = due_on
        self.due_at = due_at
        self.notes = notes
        self.assignee_name = assignee_name
        self.project_name = project_name
        self.project_gid = project_gid
        self.tags = tags or []
        self.permalink_url = permalink_url

    @property
    def due_date(self) -> datetime | None:
        """Parse due date from Asana format."""
        if self.due_at:
            return datetime.fromisoformat(self.due_at.replace("Z", "+00:00"))
        if self.due_on:
            return datetime.fromisoformat(self.due_on)
        return None

    def to_dict(self) -> dict:
        return {
            "gid": self.gid,
            "name": self.name,
            "completed": self.completed,
            "due_on": self.due_on,
            "due_at": self.due_at,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "notes": self.notes,
            "assignee_name": self.assignee_name,
            "project_name": self.project_name,
            "project_gid": self.project_gid,
            "tags": self.tags,
            "permalink_url": self.permalink_url,
        }


class AsanaService:
    """Service for interacting with the Asana API."""

    def __init__(self, access_token: str) -> None:
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    @classmethod
    def from_integration(cls, integration) -> "AsanaService":
        """Create service from an Integration model."""
        return cls(access_token=integration.access_token)

    async def _get(self, path: str, params: dict | None = None) -> dict:
        """Make an authenticated GET request to the Asana API."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ASANA_API_BASE}{path}",
                headers=self.headers,
                params=params or {},
            )
            response.raise_for_status()
            return response.json()

    async def _post(self, path: str, data: dict) -> dict:
        """Make an authenticated POST request to the Asana API."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ASANA_API_BASE}{path}",
                headers=self.headers,
                json={"data": data},
            )
            response.raise_for_status()
            return response.json()

    async def _put(self, path: str, data: dict) -> dict:
        """Make an authenticated PUT request to the Asana API."""
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{ASANA_API_BASE}{path}",
                headers=self.headers,
                json={"data": data},
            )
            response.raise_for_status()
            return response.json()

    async def get_me(self) -> dict:
        """Get the authenticated user's info."""
        result = await self._get("/users/me")
        return result.get("data", {})

    async def get_workspaces(self) -> list[dict]:
        """Get all workspaces the user belongs to."""
        result = await self._get("/workspaces")
        return result.get("data", [])

    async def get_projects(self, workspace_gid: str) -> list[dict]:
        """Get all projects in a workspace."""
        result = await self._get(
            "/projects",
            params={
                "workspace": workspace_gid,
                "opt_fields": "name,color,archived,permalink_url",
            },
        )
        return [p for p in result.get("data", []) if not p.get("archived")]

    async def get_my_tasks(self, workspace_gid: str) -> list[AsanaTask]:
        """Get tasks assigned to the authenticated user in a workspace."""
        me = await self.get_me()
        user_gid = me.get("gid")

        result = await self._get(
            "/tasks",
            params={
                "assignee": user_gid,
                "workspace": workspace_gid,
                "completed_since": "now",
                "opt_fields": (
                    "name,completed,due_on,due_at,notes,assignee.name,"
                    "projects.name,projects.gid,tags.name,permalink_url"
                ),
            },
        )
        return [self._parse_task(t) for t in result.get("data", [])]

    async def get_project_tasks(self, project_gid: str) -> list[AsanaTask]:
        """Get all incomplete tasks in a project."""
        result = await self._get(
            f"/projects/{project_gid}/tasks",
            params={
                "completed_since": "now",
                "opt_fields": (
                    "name,completed,due_on,due_at,notes,assignee.name,"
                    "projects.name,projects.gid,tags.name,permalink_url"
                ),
            },
        )
        return [self._parse_task(t) for t in result.get("data", [])]

    async def complete_task(self, task_gid: str) -> dict:
        """Mark a task as complete."""
        result = await self._put(f"/tasks/{task_gid}", data={"completed": True})
        return result.get("data", {})

    def _parse_task(self, data: dict) -> AsanaTask:
        """Parse an Asana API task response into an AsanaTask."""
        projects = data.get("projects", [])
        project_name = projects[0].get("name") if projects else None
        project_gid = projects[0].get("gid") if projects else None

        tags = [t.get("name", "") for t in data.get("tags", [])]

        assignee = data.get("assignee")
        assignee_name = assignee.get("name") if isinstance(assignee, dict) else None

        return AsanaTask(
            gid=data["gid"],
            name=data.get("name", ""),
            completed=data.get("completed", False),
            due_on=data.get("due_on"),
            due_at=data.get("due_at"),
            notes=data.get("notes"),
            assignee_name=assignee_name,
            project_name=project_name,
            project_gid=project_gid,
            tags=tags,
            permalink_url=data.get("permalink_url"),
        )
