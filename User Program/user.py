"""Development launcher for the ERP endpoint client.

Run this file with Python while developing. Later it can become the
PyInstaller entry point for the future ``user.exe`` build.
"""

from user_app.ui.main import run_desktop_app


if __name__ == "__main__":
    run_desktop_app()
