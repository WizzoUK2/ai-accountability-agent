from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "ai-accountability-agent"
    debug: bool = False
    log_level: str = "INFO"

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/accountability.db"

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    # Twilio SMS
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    user_phone_number: str = ""

    # Slack
    slack_bot_token: str = ""
    slack_signing_secret: str = ""
    slack_user_id: str = ""

    # Asana
    asana_access_token: str = ""

    # Notion
    notion_api_key: str = ""

    # Spark Email MCP
    spark_email_command: str = ""  # e.g., "python" or path to Python
    spark_email_args: list[str] = []  # e.g., ["/path/to/spark_email_mcp/server.py"]

    # Anthropic
    anthropic_api_key: str = ""

    # Scheduling
    morning_briefing_time: str = "07:00"
    timezone: str = "Australia/Sydney"


settings = Settings()
