"""Tests for Laravel-style fresh seed helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import fresh_seed as fresh_seed_cli
from server_app.api.routers_sales_v1 import _sales_chart_points, _sales_report_payload
from server_app.core.config import ApiConfig, AppConfig, DatabaseConfig
from server_app.core.constants import SUPER_ADMIN_USERNAME
from server_app.core.security import verify_password
from server_app.db.base import Base
from server_app.db.fresh_seed import (
    DemoSeedOptions,
    prepare_fresh_schema,
    seed_demo_data,
)
from server_app.db.models import (
    CashOperation,
    Payment,
    Product,
    ProductBarcode,
    PurchaseInvoice,
    Sale,
    ServiceBarcode,
    User,
)


class _MissingConfigManager:
    """Config manager test double with no saved config."""

    def exists(self) -> bool:
        return False


class _SavedConfigManager:
    """Config manager test double with a saved config."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def exists(self) -> bool:
        return True

    def load(self) -> AppConfig:
        return self.config


class FreshSeedDataTests(unittest.TestCase):
    """Validate fake-data seeding without touching MSSQL."""

    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite+pysqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_seed_demo_data_populates_every_mapped_table(self) -> None:
        """Every ORM table should receive at least one row."""

        with self.session_factory() as session:
            result = seed_demo_data(
                session,
                DemoSeedOptions(super_admin_password="admin123", scale="small", seed=123),
            )
            session.commit()

            empty_tables = [name for name, count in result.table_counts.items() if count <= 0]

        self.assertEqual(empty_tables, [])

    def test_seed_demo_data_sets_login_passwords_and_unique_values(self) -> None:
        """Important unique business identifiers should not collide."""

        with self.session_factory() as session:
            seed_demo_data(
                session,
                DemoSeedOptions(
                    super_admin_password="admin123",
                    demo_user_password="demo123",
                    scale="small",
                    seed=456,
                ),
            )
            session.commit()

            super_admin = session.query(User).filter(User.username == SUPER_ADMIN_USERNAME).one()
            self.assertTrue(verify_password("admin123", super_admin.password_hash))
            cashier = session.query(User).filter(User.username == "cashier1").one()
            self.assertTrue(verify_password("demo123", cashier.password_hash))

            for model, column in (
                (User, User.username),
                (Product, Product.sku),
                (ProductBarcode, ProductBarcode.barcode),
                (ServiceBarcode, ServiceBarcode.barcode),
                (PurchaseInvoice, PurchaseInvoice.doc_number),
                (Sale, Sale.doc_number),
                (Payment, Payment.doc_number),
                (CashOperation, CashOperation.doc_number),
            ):
                values = [row[0] for row in session.execute(select(column)).all()]
                self.assertEqual(len(values), len(set(values)), model.__tablename__)

    def test_seed_demo_data_row_counts_are_visible_from_database(self) -> None:
        """The returned counts should match the committed database state."""

        with self.session_factory() as session:
            result = seed_demo_data(
                session,
                DemoSeedOptions(super_admin_password="admin123", scale="small", seed=789),
            )
            session.commit()

            for table in Base.metadata.sorted_tables:
                db_count = session.execute(select(func.count()).select_from(table)).scalar_one()
                self.assertEqual(result.table_counts[table.name], db_count, table.name)

    def test_seed_demo_data_creates_current_period_sales_report_rows(self) -> None:
        """Fresh demo data should give the dashboard sales chart real rows."""

        with self.session_factory() as session:
            seed_demo_data(
                session,
                DemoSeedOptions(super_admin_password="admin123", scale="small", seed=321),
            )
            session.commit()

            today = datetime.now(timezone.utc).date()
            month_start = today.replace(day=1)
            date_from = datetime(month_start.year, month_start.month, month_start.day, tzinfo=timezone.utc)
            date_to = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
            report = _sales_report_payload(session, date_from, date_to)

        self.assertGreater(len(report["rows"]), 0)
        self.assertGreater(len(report["chart_points"]), 0)

    def test_sales_chart_points_aggregate_sales_and_returns_by_date(self) -> None:
        """Daily chart points should summarize sales and returns precisely."""

        doc_date = datetime(2026, 6, 24, 10, 0, tzinfo=timezone.utc)
        sale_one = SimpleNamespace(
            doc_date=doc_date,
            lines=[SimpleNamespace(quantity="2.0000")],
            total_amount_tmt="30.00",
            paid_cash_tmt="10.00",
            paid_transfer_tmt="0.00",
            paid_bonus_tmt="0.00",
            debt_amount_tmt="20.00",
        )
        sale_two = SimpleNamespace(
            doc_date=doc_date,
            lines=[SimpleNamespace(quantity="1.0000")],
            total_amount_tmt="5.00",
            paid_cash_tmt="0.00",
            paid_transfer_tmt="5.00",
            paid_bonus_tmt="0.00",
            debt_amount_tmt="0.00",
        )
        sale_return = SimpleNamespace(
            doc_date=doc_date,
            lines=[SimpleNamespace(quantity="1.0000")],
            total_amount_tmt="10.00",
            refund_cash_tmt="0.00",
            refund_transfer_tmt="0.00",
            refund_bonus_tmt="0.00",
            receivable_correction_tmt="10.00",
        )

        points = _sales_chart_points([sale_one, sale_two], [sale_return])

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["date"], "2026-06-24")
        self.assertEqual(points[0]["sales_total_tmt"], "35.00")
        self.assertEqual(points[0]["returns_total_tmt"], "10.00")
        self.assertEqual(points[0]["net_amount_tmt"], "25.00")
        self.assertEqual(points[0]["document_count"], 2)
        self.assertEqual(points[0]["returns_count"], 1)
        self.assertEqual(points[0]["sold_quantity"], "3.0000")
        self.assertEqual(points[0]["returned_quantity"], "1.0000")
        self.assertEqual(points[0]["cash_tmt"], "10.00")
        self.assertEqual(points[0]["transfer_tmt"], "5.00")
        self.assertEqual(points[0]["debt_tmt"], "10.00")


class FreshSchemaTests(unittest.TestCase):
    """Validate destructive schema dispatch with mocked MSSQL operations."""

    def setUp(self) -> None:
        self.config = AppConfig(
            database=DatabaseConfig(server="localhost", database="ERPTest"),
            api=ApiConfig(),
            jwt_secret="secret",
        )

    def test_prepare_fresh_schema_table_mode_drops_tables_then_migrates(self) -> None:
        with (
            patch("server_app.db.fresh_seed.create_database_if_missing") as create_db,
            patch("server_app.db.fresh_seed.drop_all_user_tables") as drop_tables,
            patch("server_app.db.fresh_seed.drop_configured_database") as drop_database,
            patch("server_app.db.fresh_seed.run_migrations") as migrations,
            patch("server_app.db.fresh_seed.grant_windows_service_database_access") as grant_access,
        ):
            prepare_fresh_schema(self.config, "tables")

        create_db.assert_called_once_with(self.config)
        drop_tables.assert_called_once_with(self.config)
        drop_database.assert_not_called()
        migrations.assert_called_once_with(self.config)
        grant_access.assert_called_once_with(self.config)

    def test_prepare_fresh_schema_database_mode_drops_database_then_migrates(self) -> None:
        with (
            patch("server_app.db.fresh_seed.create_database_if_missing") as create_db,
            patch("server_app.db.fresh_seed.drop_all_user_tables") as drop_tables,
            patch("server_app.db.fresh_seed.drop_configured_database") as drop_database,
            patch("server_app.db.fresh_seed.run_migrations") as migrations,
            patch("server_app.db.fresh_seed.grant_windows_service_database_access") as grant_access,
        ):
            prepare_fresh_schema(self.config, "database")

        drop_database.assert_called_once_with(self.config)
        create_db.assert_called_once_with(self.config)
        drop_tables.assert_not_called()
        migrations.assert_called_once_with(self.config)
        grant_access.assert_called_once_with(self.config)


class FreshSeedCliTests(unittest.TestCase):
    """Validate CLI safeguards without touching a live DB."""

    def setUp(self) -> None:
        self.config = AppConfig(
            database=DatabaseConfig(server="localhost", database="ERPTest"),
            api=ApiConfig(),
            jwt_secret="secret",
        )

    def test_cli_refuses_missing_config(self) -> None:
        stderr = io.StringIO()
        with (
            patch("fresh_seed.ConfigManager", return_value=_MissingConfigManager()),
            patch("sys.stderr", stderr),
        ):
            exit_code = fresh_seed_cli.main(["--yes", "--super-admin-password", "admin123"])

        self.assertEqual(exit_code, 1)
        self.assertIn("No saved server config", stderr.getvalue())

    def test_cli_dry_run_does_not_seed(self) -> None:
        stdout = io.StringIO()
        with (
            patch("fresh_seed.ConfigManager", return_value=_SavedConfigManager(self.config)),
            patch("fresh_seed.fresh_seed_database") as fresh_seed_database,
            patch("sys.stdout", stdout),
        ):
            exit_code = fresh_seed_cli.main(["--dry-run", "--scale", "small"])

        self.assertEqual(exit_code, 0)
        fresh_seed_database.assert_not_called()
        self.assertIn("Dry run complete", stdout.getvalue())

    def test_cli_requires_confirmation_without_yes(self) -> None:
        stdout = io.StringIO()
        with (
            patch("fresh_seed.ConfigManager", return_value=_SavedConfigManager(self.config)),
            patch("fresh_seed.fresh_seed_database") as fresh_seed_database,
            patch("builtins.input", return_value="wrong"),
            patch("sys.stdout", stdout),
        ):
            exit_code = fresh_seed_cli.main(["--super-admin-password", "admin123"])

        self.assertEqual(exit_code, 1)
        fresh_seed_database.assert_not_called()
        self.assertIn("cancelled", stdout.getvalue())

    def test_cli_passes_options_to_seed_runner(self) -> None:
        result = type("Result", (), {"table_counts": {"users": 2}})()
        stdout = io.StringIO()
        with (
            patch("fresh_seed.ConfigManager", return_value=_SavedConfigManager(self.config)),
            patch("fresh_seed.fresh_seed_database", return_value=result) as fresh_seed_database,
            patch("sys.stdout", stdout),
        ):
            exit_code = fresh_seed_cli.main(
                [
                    "--yes",
                    "--mode",
                    "database",
                    "--scale",
                    "medium",
                    "--seed",
                    "42",
                    "--super-admin-password",
                    "admin123",
                    "--demo-user-password",
                    "demo123",
                ]
            )

        self.assertEqual(exit_code, 0)
        called_config, called_options = fresh_seed_database.call_args.args[:2]
        self.assertEqual(called_config.database.database, "ERPTest")
        self.assertEqual(fresh_seed_database.call_args.kwargs["mode"], "database")
        self.assertEqual(called_options.super_admin_password, "admin123")
        self.assertEqual(called_options.demo_user_password, "demo123")
        self.assertEqual(called_options.scale, "medium")
        self.assertEqual(called_options.seed, 42)


if __name__ == "__main__":
    unittest.main()
