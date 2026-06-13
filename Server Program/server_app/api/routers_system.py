"""Health API route used by the Windows service controller."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from server_app.api.dependencies import get_db


router = APIRouter(tags=["system"])


@router.get("/health")
def health(session: Session = Depends(get_db)) -> dict[str, str]:
    """Return a simple API and database health response."""

    session.execute(text("SELECT 1"))
    return {"status": "ok"}
