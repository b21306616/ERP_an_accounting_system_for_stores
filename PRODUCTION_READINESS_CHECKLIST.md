# Production Readiness Checklist

Use this checklist before converting `Server Program` and `User Program` into separate EXE builds.

## Server PC

- MSSQL Server and SQL Server Management Studio are installed.
- ODBC Driver 18 for SQL Server is installed.
- `python "Server Program/server.py"` opens only the GUI controller.
- First setup creates or updates the `ERPAccountingServer` Windows Service.
- API host is set to a LAN-reachable address, normally `0.0.0.0` for all interfaces.
- Windows Firewall allows the configured API port, for example TCP `8000`.
- Swagger is reachable from the server at `http://127.0.0.1:<port>/docs`.
- Health is reachable from the server at `http://127.0.0.1:<port>/health`.
- Logs are checked after service start, stop, failed start, and config update.

## MSSQL Smoke

- Optional migration smoke uses a disposable database only:
  `set ERP_MSSQL_TEST_URL=mssql+pyodbc://...`
- Run from `Server Program`:
  `python -m unittest tests.test_mssql_migrations -v`
- Confirm the reported Alembic head is `0010_report_filters`.

## Endpoint Client PC

- Server URL is configured as `http://<server-lan-ip>:<port>/api/v1` or `<server-lan-ip>:<port>`.
- Local endpoint config is stored in Windows AppData, not the project folder.
- Login succeeds using `X-Session-Token` API sessions.
- Role-specific navigation and action buttons match the logged-in user permissions.
- Run from `User Program` against the server PC:
  `python lan_smoke.py --server http://<server-lan-ip>:<port> --username super_admin`

## Functional Smoke

- Create warehouse, product, supplier, and customer.
- Post a purchase invoice and verify stock balance.
- Open a cash shift, post a sale, and verify stock, debt, and cashier X/Z reports.
- Export sales, stock, purchases, debt, cash-flow, and profit/loss reports to XLSX.
- Save and reload a report filter.
- Switch UI language between Russian, Turkmen, and English.

## EXE Readiness Gate

- Full server tests pass: `python -m unittest discover -v` in `Server Program`.
- Full user tests pass: `python -m unittest discover -v` in `User Program`.
- MSSQL smoke passes on a disposable database.
- LAN smoke passes from at least one endpoint PC.
- No EXE packaging starts until the checks above pass.
