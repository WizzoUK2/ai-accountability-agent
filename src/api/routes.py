from fastapi import APIRouter

from src.api.auth import router as auth_router
from src.api.briefings import router as briefings_router
from src.api.tasks import router as tasks_router

router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
router.include_router(briefings_router, prefix="/briefings", tags=["Briefings"])
router.include_router(tasks_router, prefix="/tasks", tags=["Tasks"])
