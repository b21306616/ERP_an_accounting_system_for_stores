"""FastAPI application factory."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from server_app.api import routers_auth, routers_foundation, routers_system, routers_users
from server_app.core.config import AppConfig
from server_app.core.constants import APP_NAME


def create_app(config: AppConfig, session_factory: sessionmaker[Session]) -> FastAPI:
    """Create and configure the FastAPI application instance."""

    app = FastAPI(
        title=APP_NAME,
        version="0.1.0",
        description="LAN API for the ERP accounting server Foundation MVP.",
    )
    app.state.config = config
    app.state.session_factory = session_factory
    app.state.started_at = datetime.now(timezone.utc)

    app.include_router(routers_system.router)
    app.include_router(routers_auth.router)
    app.include_router(routers_users.router)
    app.include_router(routers_foundation.router)

    return app
