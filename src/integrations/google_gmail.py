from datetime import datetime
from base64 import urlsafe_b64decode
import re

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import structlog

from src.integrations.google_auth import GoogleOAuth

logger = structlog.get_logger()


class EmailMessage:
    """Represents an email message."""

    def __init__(
        self,
        id: str,
        thread_id: str,
        subject: str,
        sender: str,
        sender_email: str,
        snippet: str,
        received_at: datetime,
        is_unread: bool = False,
        is_important: bool = False,
        labels: list[str] | None = None,
        body_preview: str | None = None,
    ) -> None:
        self.id = id
        self.thread_id = thread_id
        self.subject = subject
        self.sender = sender
        self.sender_email = sender_email
        self.snippet = snippet
        self.received_at = received_at
        self.is_unread = is_unread
        self.is_important = is_important
        self.labels = labels or []
        self.body_preview = body_preview

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "subject": self.subject,
            "sender": self.sender,
            "sender_email": self.sender_email,
            "snippet": self.snippet,
            "received_at": self.received_at.isoformat(),
            "is_unread": self.is_unread,
            "is_important": self.is_important,
            "labels": self.labels,
            "body_preview": self.body_preview,
        }


class GoogleGmailService:
    """Service for interacting with Gmail."""

    def __init__(self, credentials: Credentials) -> None:
        self.service = build("gmail", "v1", credentials=credentials)

    @classmethod
    def from_integration(cls, integration) -> "GoogleGmailService":
        """Create service from an Integration model."""
        credentials = GoogleOAuth.credentials_from_dict(
            {
                "access_token": integration.access_token,
                "refresh_token": integration.refresh_token,
                "scopes": integration.scopes,
            }
        )
        return cls(credentials)

    def get_unread_emails(self, max_results: int = 20) -> list[EmailMessage]:
        """Get unread emails from inbox."""
        return self.search_emails("is:unread in:inbox", max_results)

    def get_important_unread(self, max_results: int = 10) -> list[EmailMessage]:
        """Get important unread emails."""
        return self.search_emails("is:unread is:important", max_results)

    def get_recent_emails(self, max_results: int = 20) -> list[EmailMessage]:
        """Get recent emails from inbox."""
        return self.search_emails("in:inbox", max_results)

    def search_emails(self, query: str, max_results: int = 20) -> list[EmailMessage]:
        """Search emails with a Gmail query."""
        try:
            results = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )

            messages = []
            for msg_ref in results.get("messages", []):
                msg = self._get_message(msg_ref["id"])
                if msg:
                    messages.append(msg)

            return messages

        except Exception as e:
            logger.error("Failed to search emails", query=query, error=str(e))
            return []

    def _get_message(self, message_id: str) -> EmailMessage | None:
        """Get full message details."""
        try:
            msg = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

            return self._parse_message(msg)

        except Exception as e:
            logger.warning("Failed to get message", message_id=message_id, error=str(e))
            return None

    def _parse_message(self, msg: dict) -> EmailMessage:
        """Parse a Gmail message into our format."""
        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}

        # Parse sender
        from_header = headers.get("from", "Unknown")
        sender_match = re.match(r"(.+?)\s*<(.+?)>", from_header)
        if sender_match:
            sender = sender_match.group(1).strip().strip('"')
            sender_email = sender_match.group(2)
        else:
            sender = from_header
            sender_email = from_header

        # Parse date
        internal_date = int(msg.get("internalDate", "0"))
        received_at = datetime.fromtimestamp(internal_date / 1000)

        # Check labels
        labels = msg.get("labelIds", [])
        is_unread = "UNREAD" in labels
        is_important = "IMPORTANT" in labels

        # Get body preview
        body_preview = self._extract_body_preview(msg["payload"])

        return EmailMessage(
            id=msg["id"],
            thread_id=msg["threadId"],
            subject=headers.get("subject", "(no subject)"),
            sender=sender,
            sender_email=sender_email,
            snippet=msg.get("snippet", ""),
            received_at=received_at,
            is_unread=is_unread,
            is_important=is_important,
            labels=labels,
            body_preview=body_preview,
        )

    def _extract_body_preview(self, payload: dict, max_length: int = 500) -> str | None:
        """Extract a preview of the email body."""
        body = None

        # Try to get plain text body
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            body = urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
        elif "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    body = urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="ignore")
                    break

        if body:
            # Clean up and truncate
            body = " ".join(body.split())
            if len(body) > max_length:
                body = body[:max_length] + "..."

        return body

    def get_inbox_summary(self) -> dict:
        """Get a summary of the inbox state."""
        try:
            # Get counts
            profile = self.service.users().getProfile(userId="me").execute()
            total_messages = profile.get("messagesTotal", 0)
            total_threads = profile.get("threadsTotal", 0)

            # Count unread
            unread_results = (
                self.service.users()
                .messages()
                .list(userId="me", q="is:unread in:inbox", maxResults=1)
                .execute()
            )
            unread_estimate = unread_results.get("resultSizeEstimate", 0)

            # Count important unread
            important_results = (
                self.service.users()
                .messages()
                .list(userId="me", q="is:unread is:important", maxResults=1)
                .execute()
            )
            important_unread_estimate = important_results.get("resultSizeEstimate", 0)

            return {
                "total_messages": total_messages,
                "total_threads": total_threads,
                "unread_count": unread_estimate,
                "important_unread_count": important_unread_estimate,
            }

        except Exception as e:
            logger.error("Failed to get inbox summary", error=str(e))
            return {}
