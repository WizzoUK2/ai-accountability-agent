from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import structlog

from config import settings

logger = structlog.get_logger()

# Google OAuth scopes needed for Calendar and Gmail
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]


class GoogleOAuth:
    """Handle Google OAuth authentication."""

    def __init__(self) -> None:
        self.client_config = {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uris": [settings.google_redirect_uri],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

    def get_authorization_url(self) -> str:
        """Get the Google OAuth authorization URL."""
        flow = Flow.from_client_config(
            self.client_config,
            scopes=GOOGLE_SCOPES,
            redirect_uri=settings.google_redirect_uri,
        )

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )

        return auth_url

    def exchange_code(self, code: str) -> Credentials:
        """Exchange authorization code for credentials."""
        flow = Flow.from_client_config(
            self.client_config,
            scopes=GOOGLE_SCOPES,
            redirect_uri=settings.google_redirect_uri,
        )

        flow.fetch_token(code=code)
        return flow.credentials

    def get_user_info(self, credentials: Credentials) -> dict:
        """Get user info from Google."""
        service = build("oauth2", "v2", credentials=credentials)
        user_info = service.userinfo().get().execute()
        return user_info

    @staticmethod
    def credentials_from_dict(data: dict) -> Credentials:
        """Create credentials from stored dictionary."""
        return Credentials(
            token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=data.get("scopes", "").split(",") if data.get("scopes") else GOOGLE_SCOPES,
        )
