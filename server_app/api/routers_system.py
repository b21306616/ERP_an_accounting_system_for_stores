"""Health and system status API routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from server_app.api.dependencies import get_current_user, get_db
from server_app.core.constants import APP_NAME
from server_app.db.models import User


router = APIRouter(tags=["system"])


@router.get("/health")
def health(session: Session = Depends(get_db)) -> dict[str, str]:
    """Return a simple API and database health response."""

    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/system/status")
def system_status(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, str | int | None]:
    """Return server runtime details for authenticated clients."""

    session.execute(text("SELECT 1"))
    started_at = getattr(request.app.state, "started_at", None)
    now = datetime.now(timezone.utc)

    return {
        "application": APP_NAME,
        "status": "running",
        "started_at": started_at.isoformat() if started_at else None,
        "server_time": now.isoformat(),
        "current_user_id": current_user.id,
        "current_username": current_user.username,
    }
