"""RED stub (Phase 87-06 task 2): the route is written in the next commit."""
from fastapi import APIRouter

from database import mongodb  # noqa: F401

router = APIRouter(prefix="/api/auth/invite", tags=["Authentication"])
