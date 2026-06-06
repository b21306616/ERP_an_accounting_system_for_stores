"""Main launcher for the LAN accounting server application.

Run this file with Python while developing. Later it can become the
PyInstaller entry point for the future ``server.exe`` build.
"""

from server_app.gui.main import run_desktop_app


if __name__ == "__main__":
    run_desktop_app()
