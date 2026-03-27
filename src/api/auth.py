from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from config import settings
from src.models.database import get_db
from src.models.user import User
from src.models.integration import Integration, IntegrationType
from src.integrations.google_auth import GoogleOAuth
from src.integrations.asana import AsanaService

router = APIRouter()
logger = structlog.get_logger()


@router.get("/google")
async def google_auth_start() -> RedirectResponse:
    """Start Google OAuth flow."""
    google_oauth = GoogleOAuth()
    auth_url = google_oauth.get_authorization_url()
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_auth_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Handle Google OAuth callback."""
    if error:
        logger.error("Google OAuth error", error=error)
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code provided")

    google_oauth = GoogleOAuth()

    try:
        credentials = google_oauth.exchange_code(code)
    except Exception as e:
        logger.error("Failed to exchange code", error=str(e))
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

    # Get user info from Google
    user_info = google_oauth.get_user_info(credentials)

    # Find or create user
    result = await db.execute(select(User).where(User.email == user_info["email"]))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            email=user_info["email"],
            name=user_info.get("name", user_info["email"]),
            timezone=settings.timezone,
            morning_briefing_time=settings.morning_briefing_time,
        )
        db.add(user)
        await db.flush()
        logger.info("Created new user", email=user.email)

    # Find or update integration
    result = await db.execute(
        select(Integration).where(
            Integration.user_id == user.id,
            Integration.type == IntegrationType.GOOGLE,
            Integration.account_email == user_info["email"],
        )
    )
    integration = result.scalar_one_or_none()

    if integration:
        integration.access_token = credentials.token
        integration.refresh_token = credentials.refresh_token or integration.refresh_token
        integration.token_expiry = credentials.expiry
        integration.scopes = ",".join(credentials.scopes or [])
        integration.is_active = True
        logger.info("Updated Google integration", user_email=user.email)
    else:
        integration = Integration(
            user_id=user.id,
            type=IntegrationType.GOOGLE,
            account_email=user_info["email"],
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            token_expiry=credentials.expiry,
            scopes=",".join(credentials.scopes or []),
        )
        db.add(integration)
        logger.info("Created Google integration", user_email=user.email)

    await db.commit()

    return {
        "status": "success",
        "message": f"Google account {user_info['email']} connected successfully",
        "user_id": str(user.id),
    }


@router.get("/status")
async def auth_status(db: AsyncSession = Depends(get_db)) -> dict:
    """Get the status of all connected integrations."""
    result = await db.execute(
        select(User, Integration)
        .join(Integration, User.id == Integration.user_id)
        .where(Integration.is_active)
    )
    rows = result.all()

    users = {}
    for user, integration in rows:
        if user.id not in users:
            users[user.id] = {
                "email": user.email,
                "name": user.name,
                "integrations": [],
            }
        users[user.id]["integrations"].append(
            {
                "type": integration.type.value,
                "account_email": integration.account_email,
                "last_sync": integration.last_sync.isoformat() if integration.last_sync else None,
            }
        )

    return {"users": list(users.values())}


class TokenAuth(BaseModel):
    access_token: str
    user_email: str


@router.post("/asana")
async def asana_auth(
    body: TokenAuth,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Connect an Asana account via Personal Access Token."""
    # Verify the token works
    try:
        service = AsanaService(access_token=body.access_token)
        me = await service.get_me()
        asana_email = me.get("email", body.user_email)
    except Exception as e:
        logger.error("Invalid Asana token", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid Asana access token")

    # Find or create user
    result = await db.execute(select(User).where(User.email == body.user_email))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            email=body.user_email,
            name=me.get("name", body.user_email),
            timezone=settings.timezone,
            morning_briefing_time=settings.morning_briefing_time,
        )
        db.add(user)
        await db.flush()

    # Upsert integration
    result = await db.execute(
        select(Integration).where(
            Integration.user_id == user.id,
            Integration.type == IntegrationType.ASANA,
        )
    )
    integration = result.scalar_one_or_none()

    if integration:
        integration.access_token = body.access_token
        integration.account_email = asana_email
        integration.is_active = True
    else:
        integration = Integration(
            user_id=user.id,
            type=IntegrationType.ASANA,
            account_email=asana_email,
            access_token=body.access_token,
        )
        db.add(integration)

    await db.commit()
    logger.info("Asana connected", user_email=body.user_email)

    return {
        "status": "success",
        "message": f"Asana account connected for {asana_email}",
        "user_id": str(user.id),
    }


@router.post("/notion")
async def notion_auth(
    body: TokenAuth,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Connect a Notion account via integration token."""
    from src.integrations.notion import NotionService

    # Verify the token works
    try:
        service = NotionService(api_key=body.access_token)
        me = await service.get_me()
    except Exception as e:
        logger.error("Invalid Notion token", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid Notion integration token")

    # Find or create user
    result = await db.execute(select(User).where(User.email == body.user_email))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            email=body.user_email,
            name=body.user_email,
            timezone=settings.timezone,
            morning_briefing_time=settings.morning_briefing_time,
        )
        db.add(user)
        await db.flush()

    # Upsert integration
    result = await db.execute(
        select(Integration).where(
            Integration.user_id == user.id,
            Integration.type == IntegrationType.NOTION,
        )
    )
    integration = result.scalar_one_or_none()

    if integration:
        integration.access_token = body.access_token
        integration.account_email = body.user_email
        integration.is_active = True
    else:
        integration = Integration(
            user_id=user.id,
            type=IntegrationType.NOTION,
            account_email=body.user_email,
            access_token=body.access_token,
        )
        db.add(integration)

    await db.commit()
    logger.info("Notion connected", user_email=body.user_email)

    return {
        "status": "success",
        "message": f"Notion account connected for {body.user_email}",
        "user_id": str(user.id),
    }
