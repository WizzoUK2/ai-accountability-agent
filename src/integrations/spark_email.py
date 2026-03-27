import json
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
from mcp import StdioServerParameters
import structlog

from config import settings

logger = structlog.get_logger()


class SparkEmailService:
    """MCP client for the spark_email_mcp server.

    Provides multi-account email intelligence by connecting to the
    spark_email_mcp server via stdio transport.
    """

    def __init__(self, server_command: str | None = None, server_args: list[str] | None = None):
        self.server_command = server_command or settings.spark_email_command
        self.server_args = server_args or settings.spark_email_args
        self.is_configured = bool(self.server_command)

        if not self.is_configured:
            logger.warning("SparkEmail not configured - multi-account email features disabled")

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[ClientSession, None]:
        """Create a connected MCP client session."""
        params = StdioServerParameters(
            command=self.server_command,
            args=self.server_args,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    async def _call_tool(self, name: str, arguments: dict) -> dict | list | str:
        """Call an MCP tool and return parsed JSON result."""
        async with self._session() as session:
            result = await session.call_tool(name, arguments)
            # MCP tool results contain a list of content blocks
            for content in result.content:
                if hasattr(content, "text"):
                    try:
                        return json.loads(content.text)
                    except json.JSONDecodeError:
                        return content.text
            return {}

    async def list_accounts(self) -> list[dict]:
        """List all configured email accounts."""
        if not self.is_configured:
            return []

        try:
            result = await self._call_tool("spark_list_accounts", {
                "response_format": "json",
            })
            if isinstance(result, list):
                return result
            return []
        except Exception as e:
            logger.error("Failed to list email accounts", error=str(e))
            return []

    async def get_recent_emails(
        self,
        account: str | None = None,
        folder: str = "INBOX",
        limit: int = 20,
    ) -> list[dict]:
        """Get recent emails from a specific account or the default account."""
        if not self.is_configured:
            return []

        try:
            args = {
                "folder": folder,
                "limit": limit,
                "response_format": "json",
            }
            if account:
                args["account"] = account
            result = await self._call_tool("spark_list_emails", args)
            if isinstance(result, dict):
                return result.get("emails", [])
            return []
        except Exception as e:
            logger.error("Failed to get recent emails", account=account, error=str(e))
            return []

    async def read_email(
        self,
        uid: str,
        account: str | None = None,
        folder: str = "INBOX",
    ) -> dict:
        """Read a full email by UID."""
        if not self.is_configured:
            return {}

        try:
            args = {
                "uid": uid,
                "folder": folder,
                "response_format": "json",
            }
            if account:
                args["account"] = account
            result = await self._call_tool("spark_read_email", args)
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.error("Failed to read email", uid=uid, error=str(e))
            return {}

    async def search_all_accounts(
        self,
        query: str = "",
        since: str | None = None,
        folder: str = "INBOX",
        limit: int = 10,
    ) -> list[dict]:
        """Search for emails across ALL configured accounts.

        Args:
            query: Search text (matches subject/body)
            since: Date filter in DD-Mon-YYYY format (e.g., "15-Jan-2025")
            folder: Folder to search in each account
            limit: Max results per account (1-50)

        Returns:
            List of account result dicts, each with 'account', 'total', 'emails' keys
        """
        if not self.is_configured:
            return []

        try:
            args = {
                "query": query,
                "folder": folder,
                "limit": limit,
                "response_format": "json",
            }
            if since:
                args["since"] = since
            result = await self._call_tool("spark_search_all_accounts", args)
            if isinstance(result, list):
                return result
            return []
        except Exception as e:
            logger.error("Failed to search all accounts", query=query, error=str(e))
            return []

    async def get_unread_across_accounts(self, limit: int = 10) -> list[dict]:
        """Get unread emails from all accounts.

        Returns a flat list of emails with account info attached.
        """
        if not self.is_configured:
            return []

        try:
            accounts = await self.list_accounts()
            all_unread = []

            for acct in accounts:
                acct_name = acct.get("name", acct.get("email", ""))
                args = {
                    "account": acct_name,
                    "folder": "INBOX",
                    "limit": limit,
                    "response_format": "json",
                }
                result = await self._call_tool("spark_list_emails", args)
                if isinstance(result, dict):
                    for email in result.get("emails", []):
                        if not email.get("is_read", True):
                            email["account"] = acct_name
                            email["account_email"] = acct.get("email", "")
                            all_unread.append(email)

            return all_unread
        except Exception as e:
            logger.error("Failed to get unread across accounts", error=str(e))
            return []

    async def get_inbox_summary(self) -> dict:
        """Get a summary of inbox state across all accounts.

        Returns:
            Dict with total_unread, accounts (list of per-account summaries)
        """
        if not self.is_configured:
            return {"total_unread": 0, "accounts": []}

        try:
            accounts = await self.list_accounts()
            account_summaries = []
            total_unread = 0

            for acct in accounts:
                acct_name = acct.get("name", acct.get("email", ""))
                result = await self._call_tool("spark_list_emails", {
                    "account": acct_name,
                    "folder": "INBOX",
                    "limit": 50,
                    "response_format": "json",
                })
                if isinstance(result, dict):
                    emails = result.get("emails", [])
                    total = result.get("total", len(emails))
                    unread = sum(1 for e in emails if not e.get("is_read", True))
                    total_unread += unread
                    account_summaries.append({
                        "account": acct_name,
                        "email": acct.get("email", ""),
                        "total": total,
                        "unread": unread,
                    })

            return {
                "total_unread": total_unread,
                "accounts": account_summaries,
            }
        except Exception as e:
            logger.error("Failed to get inbox summary", error=str(e))
            return {"total_unread": 0, "accounts": []}

    async def find_urgent_emails(self, hours: int = 24, limit: int = 10) -> list[dict]:
        """Find potentially urgent/actionable unread emails across all accounts.

        Fetches recent unread emails and enriches them with basic urgency signals.
        The AI prioritization service should be used on the results for deeper analysis.

        Returns:
            List of email dicts with 'account', 'uid', 'subject', 'from', 'date' keys
        """
        if not self.is_configured:
            return []

        try:
            from datetime import datetime, timedelta
            since_date = (datetime.now() - timedelta(hours=hours)).strftime("%d-%b-%Y")

            account_results = await self.search_all_accounts(
                query="",
                since=since_date,
                folder="INBOX",
                limit=limit,
            )

            urgent = []
            for acct_result in account_results:
                acct_name = acct_result.get("account", "")
                for email in acct_result.get("emails", []):
                    if not email.get("is_read", True):
                        email["account"] = acct_name
                        urgent.append(email)

            return urgent
        except Exception as e:
            logger.error("Failed to find urgent emails", error=str(e))
            return []
