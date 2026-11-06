"""Staged patch rollouts, the Rollouts tab API (plan 84-09). Skeleton: no routes yet."""
from fastapi import APIRouter

from database import get_database  # noqa: F401

router = APIRouter(prefix="/api/patch-rollouts", tags=["Patch rollouts"])
