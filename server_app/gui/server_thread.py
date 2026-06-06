"""Background API server thread used by the PyQt6 GUI."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from sqlalchemy.orm import Session, sessionmaker
import uvicorn

from server_app.api.app import create_app
from server_app.core.config import AppConfig


class ApiServerThread(QThread):
    """Run uvicorn in a Qt worker thread so the GUI remains responsive."""

    started_listening = pyqtSignal()
    stopped = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, config: AppConfig, session_factory: sessionmaker[Session]) -> None:
        super().__init__()
        self.config = config
        self.session_factory = session_factory
        self.server: uvicorn.Server | None = None

    def run(self) -> None:
        """Create the FastAPI app and run uvicorn until shutdown is requested."""

        try:
            app = create_app(self.config, self.session_factory)
            uvicorn_config = uvicorn.Config(
                app,
                host=self.config.api.host,
                port=self.config.api.port,
                log_level="info",
            )
            self.server = uvicorn.Server(uvicorn_config)
            self.started_listening.emit()
            self.server.run()
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.stopped.emit()

    def stop(self) -> None:
        """Ask uvicorn to exit cleanly."""

        if self.server is not None:
            self.server.should_exit = True
