# ERP Accounting Server

Foundation MVP for a LAN-based accounting server. The app is written in Python,
uses PyQt6 for the Windows setup/control GUI, FastAPI for LAN endpoints,
SQLAlchemy + pyodbc for MSSQL access, and Alembic for database migrations.

## What Is Implemented

- First-run GUI for MSSQL connection, API host/port, and fixed Super Admin password setup.
- Saved config at `%PROGRAMDATA%\ERPAccountingServer\config.json`.
- Machine-scope Windows DPAPI protection for SQL password and JWT signing secret.
- Windows service registration/control for `ERPAccountingServer` / `ERP Accounting Server`.
- Background FastAPI server runs as a Windows service and is controlled from the PyQt6 summary window.
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

Run the app as Administrator when setup, start, stop, or service repair is needed.
On first launch, fill the setup form and click **Create database and start server**.
The GUI creates/migrates the database, saves machine-wide config, installs or
repairs the Windows service, starts it, and shows the connection summary.

On later launches, the GUI loads saved config and shows the service state. Use
**Start Connection** to re-enable Automatic startup and start the service. Use
**Stop Connection** to stop the service and disable startup after reboot. Closing
the GUI does not stop the service.

The service runs as `LocalSystem` with the per-service SID
`NT SERVICE\ERPAccountingServer` enabled. If Windows Authentication is used, the
setup/start flow grants that service SID access to the selected database.

## Test

```powershell
python -m unittest discover -v
```

The API smoke tests use an in-memory SQLite database and a temporary uvicorn
localhost port, so they do not require MSSQL.
