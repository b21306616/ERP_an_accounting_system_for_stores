"""Non-GUI API server runtime used by the Windows service."""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
import uvicorn

from server_app.api.app import create_app
from server_app.core.config import AppConfig, ConfigManager
from server_app.db.bootstrap import prepare_existing_database


class ApiServiceRuntime:
    """Prepare database resources and run uvicorn for the Windows service."""

    def __init__(self, config_manager: ConfigManager | None = None) -> None:
        self.config_manager = config_manager or ConfigManager()
        self.config: AppConfig | None = None
        self.engine: Engine | None = None
        self.session_factory: sessionmaker[Session] | None = None
        self.server: uvicorn.Server | None = None

    def prepare(self) -> None:
        """Load config, validate/migrate the database, and create the uvicorn server."""

        self.config = self.config_manager.load()
        self.engine, self.session_factory = prepare_existing_database(self.config)
        app = create_app(self.config, self.session_factory)
        uvicorn_config = uvicorn.Config(
            app,
            host=self.config.api.host,
            port=self.config.api.port,
            log_level="info",
            use_colors=False,
        )
        self.server = uvicorn.Server(uvicorn_config)

    def run(self) -> None:
        """Run uvicorn until the service receives a stop request."""

        if self.server is None:
            self.prepare()

        assert self.server is not None
        try:
            self.server.run()
        finally:
            self.close()

    def stop(self) -> None:
        """Ask uvicorn to stop cleanly."""

        if self.server is not None:
            self.server.should_exit = True

    def close(self) -> None:
        """Dispose database resources."""

        if self.engine is not None:
            self.engine.dispose()
            self.engine = None
        self.session_factory = None
