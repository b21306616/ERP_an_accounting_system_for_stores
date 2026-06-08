# ERP Accounting Server

Foundation MVP for a LAN-based accounting server. The app is written in Python,
uses PyQt6 for the Windows setup/control GUI, FastAPI for LAN endpoints,
SQLAlchemy + pyodbc for MSSQL access, and Alembic for database migrations.

## What Is Implemented

- First-run GUI for MSSQL connection, API host/port, and fixed Super Admin password setup.
- Saved config at `%LOCALAPPDATA%\ERPAccountingServer\config.json`.
- Windows DPAPI protection for SQL password and JWT signing secret.
- Automatic relaunch from saved config.
- Background FastAPI server controlled from the PyQt6 summary window.
- MSSQL database creation and Alembic migration bootstrap.
- Built-in roles: Super Admin, Accountant, Manager, Cashier, Auditor.
- PBKDF2 password hashing and internal HS256 bearer tokens.
- API endpoints:
  - `GET /health`
  - `GET /system/status`
  - `POST /auth/login`
  - `GET /auth/me`
  - Super-admin-only `/users`
  - Foundation CRUD under `/reference`

## Run

```powershell
python server.py
```

On first launch, fill the setup form and click **Create database and start server**.
On later launches, the app loads saved config, validates the database, runs
migrations, starts the API, and shows the connection summary.

## Test

```powershell
python -m unittest discover -v
```

The API smoke tests use an in-memory SQLite database and a temporary uvicorn
localhost port, so they do not require MSSQL.
