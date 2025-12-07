from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import structlog

from src.integrations.google_auth import GoogleOAuth

logger = structlog.get_logger()


class CalendarEvent:
    """Represents a calendar event."""

    def __init__(
        self,
        id: str,
        summary: str,
        start: datetime,
        end: datetime,
        location: str | None = None,
        description: str | None = None,
        is_all_day: bool = False,
        attendees: list[str] | None = None,
        meeting_link: str | None = None,
        calendar_name: str | None = None,
    ) -> None:
        self.id = id
        self.summary = summary
        self.start = start
        self.end = end
        self.location = location
        self.description = description
        self.is_all_day = is_all_day
        self.attendees = attendees or []
        self.meeting_link = meeting_link
        self.calendar_name = calendar_name

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "summary": self.summary,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "location": self.location,
            "description": self.description,
            "is_all_day": self.is_all_day,
            "attendees": self.attendees,
            "meeting_link": self.meeting_link,
            "calendar_name": self.calendar_name,
        }

    def format_time_range(self, timezone: str = "UTC") -> str:
        """Format the event time range for display."""
        tz = ZoneInfo(timezone)
        start_local = self.start.astimezone(tz)
        end_local = self.end.astimezone(tz)

        if self.is_all_day:
            return "All day"

        return f"{start_local.strftime('%H:%M')} - {end_local.strftime('%H:%M')}"


class GoogleCalendarService:
    """Service for interacting with Google Calendar."""

    def __init__(self, credentials: Credentials) -> None:
        self.service = build("calendar", "v3", credentials=credentials)

    @classmethod
    def from_integration(cls, integration) -> "GoogleCalendarService":
        """Create service from an Integration model."""
        credentials = GoogleOAuth.credentials_from_dict(
            {
                "access_token": integration.access_token,
                "refresh_token": integration.refresh_token,
                "scopes": integration.scopes,
            }
        )
        return cls(credentials)

    def get_calendars(self) -> list[dict]:
        """Get list of calendars."""
        calendar_list = self.service.calendarList().list().execute()
        return calendar_list.get("items", [])

    def get_todays_events(self, timezone: str = "UTC") -> list[CalendarEvent]:
        """Get all events for today."""
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        return self.get_events(start_of_day, end_of_day, timezone)

    def get_events(
        self,
        start_time: datetime,
        end_time: datetime,
        timezone: str = "UTC",
    ) -> list[CalendarEvent]:
        """Get events within a time range from all calendars."""
        events = []

        # Get all calendars
        calendars = self.get_calendars()

        for calendar in calendars:
            calendar_id = calendar["id"]
            calendar_name = calendar.get("summary", "Unknown")

            try:
                events_result = (
                    self.service.events()
                    .list(
                        calendarId=calendar_id,
                        timeMin=start_time.isoformat(),
                        timeMax=end_time.isoformat(),
                        singleEvents=True,
                        orderBy="startTime",
                    )
                    .execute()
                )

                for event in events_result.get("items", []):
                    parsed_event = self._parse_event(event, calendar_name, timezone)
                    if parsed_event:
                        events.append(parsed_event)

            except Exception as e:
                logger.warning(
                    "Failed to fetch events from calendar",
                    calendar_id=calendar_id,
                    error=str(e),
                )

        # Sort all events by start time
        events.sort(key=lambda e: e.start)
        return events

    def _parse_event(
        self, event: dict, calendar_name: str, timezone: str
    ) -> CalendarEvent | None:
        """Parse a Google Calendar event into our format."""
        try:
            # Handle all-day vs timed events
            start_data = event.get("start", {})
            end_data = event.get("end", {})

            is_all_day = "date" in start_data

            tz = ZoneInfo(timezone)

            if is_all_day:
                start = datetime.fromisoformat(start_data["date"]).replace(tzinfo=tz)
                end = datetime.fromisoformat(end_data["date"]).replace(tzinfo=tz)
            else:
                start = datetime.fromisoformat(
                    start_data.get("dateTime", start_data.get("date"))
                )
                end = datetime.fromisoformat(end_data.get("dateTime", end_data.get("date")))

                # Ensure timezone awareness
                if start.tzinfo is None:
                    start = start.replace(tzinfo=tz)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=tz)

            # Extract attendees
            attendees = [
                a.get("email", "")
                for a in event.get("attendees", [])
                if a.get("email") and not a.get("self", False)
            ]

            # Extract meeting link
            meeting_link = None
            if "hangoutLink" in event:
                meeting_link = event["hangoutLink"]
            elif "conferenceData" in event:
                entry_points = event["conferenceData"].get("entryPoints", [])
                for ep in entry_points:
                    if ep.get("entryPointType") == "video":
                        meeting_link = ep.get("uri")
                        break

            return CalendarEvent(
                id=event["id"],
                summary=event.get("summary", "No title"),
                start=start,
                end=end,
                location=event.get("location"),
                description=event.get("description"),
                is_all_day=is_all_day,
                attendees=attendees,
                meeting_link=meeting_link,
                calendar_name=calendar_name,
            )

        except Exception as e:
            logger.warning("Failed to parse event", event_id=event.get("id"), error=str(e))
            return None

    def get_upcoming_events(self, hours: int = 2, timezone: str = "UTC") -> list[CalendarEvent]:
        """Get events starting within the next N hours."""
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
        end_time = now + timedelta(hours=hours)
        return self.get_events(now, end_time, timezone)
