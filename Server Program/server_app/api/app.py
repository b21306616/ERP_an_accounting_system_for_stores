"""FastAPI application factory."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from server_app.api import (
    routers_business_v1,
    routers_catalog_v1,
    routers_sales_v1,
    routers_system,
    routers_v1,
    routers_warehouse_v1,
)
from server_app.core.config import AppConfig
from server_app.core.constants import APP_NAME
from server_app.services.audit import log_api_mutation


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

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        """Return API v1-compatible error envelopes for HTTP errors."""

        detail = exc.detail
        if isinstance(detail, dict) and {"code", "message", "details"}.issubset(detail):
            error = detail
        else:
            error = {
                "code": "HTTP_ERROR",
                "message": str(detail),
                "details": {},
            }
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "data": None, "error": error, "meta": None},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Return validation errors in the documented envelope."""

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed.",
                    "details": {"errors": exc.errors()},
                },
                "meta": None,
            },
        )

    @app.middleware("http")
    async def audit_mutating_api_v1_requests(request: Request, call_next):
        """Append audit rows for successful mutating API v1 requests."""

        response = await call_next(request)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 400:
            session_factory_from_state = getattr(request.app.state, "session_factory", None)
            if session_factory_from_state is not None:
                log_api_mutation(
                    session_factory_from_state,
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    session_token=request.headers.get("X-Session-Token"),
                    ip_address=request.client.host if request.client else None,
                )
        return response

    app.include_router(routers_system.router)
    app.include_router(routers_v1.router)
    app.include_router(routers_catalog_v1.router)
    app.include_router(routers_warehouse_v1.router)
    app.include_router(routers_business_v1.router)
    app.include_router(routers_sales_v1.router)

    return app
