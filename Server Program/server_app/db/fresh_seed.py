"""Laravel-style database refresh and demo-data seeding helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import random

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from server_app.core.config import AppConfig
from server_app.core.constants import (
    BUILTIN_ROLES,
    SUPER_ADMIN_ROLE,
    SUPER_ADMIN_USERNAME,
)
from server_app.core.security import hash_password, hash_session_token
from server_app.db.base import Base
from server_app.db.bootstrap import (
    _quote_sql_identifier,
    create_database_if_missing,
    grant_windows_service_database_access,
    run_migrations,
    seed_super_admin_user,
    validate_database_name,
)
from server_app.db.models import (
    AuditLog,
    CashOperation,
    CashRegister,
    CashShift,
    Contract,
    Counterparty,
    CounterpartyCategory,
    Currency,
    DebtLedger,
    ExchangeRate,
    ExpenseCategory,
    Inventory,
    InventoryLine,
    InventoryRevision,
    LoyaltyCard,
    LoyaltySetting,
    MoneyAccount,
    Payment,
    PaymentAllocation,
    PriceList,
    PriceListItem,
    Product,
    ProductBarcode,
    ProductGroup,
    ProductSet,
    ProductSetItem,
    ProductUom,
    Promotion,
    PurchaseInvoice,
    PurchaseInvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    ReportFilter,
    Role,
    Sale,
    SaleLine,
    SaleReturn,
    SaleReturnLine,
    Service,
    ServiceBarcode,
    StockTransfer,
    StockTransferLine,
    StockWriteoff,
    StockWriteoffLine,
    UnitOfMeasure,
    User,
    UserSession,
    Warehouse,
    Workplace,
)
from server_app.db.session import create_db_engine, create_session_factory
from server_app.services.loyalty import post_loyalty_transaction
from server_app.services.settlements import (
    generate_doc_number,
    money,
    post_debt_entry,
    price,
    qty4,
    update_purchase_invoice_payment_status,
)
from server_app.services.warehouse import get_or_create_balance, post_stock_movement, quantity

try:
    from faker import Faker
except ImportError:  # pragma: no cover - exercised by real CLI environments only.
    Faker = None  # type: ignore[assignment]


FreshMode = str


@dataclass(frozen=True)
class SeedProfile:
    """Row-count profile for demo seeding."""

    user_copies_per_role: int
    product_count: int
    counterparty_count: int
    service_count: int


@dataclass(frozen=True)
class DemoSeedOptions:
    """Runtime options for fake data generation."""

    super_admin_password: str
    demo_user_password: str = "password123"
    scale: str = "small"
    seed: int | None = None


@dataclass(frozen=True)
class DemoSeedResult:
    """Summary returned after seeding finishes."""

    table_counts: dict[str, int]


SCALE_PROFILES: dict[str, SeedProfile] = {
    "small": SeedProfile(user_copies_per_role=1, product_count=8, counterparty_count=6, service_count=3),
    "medium": SeedProfile(user_copies_per_role=2, product_count=20, counterparty_count=15, service_count=6),
    "large": SeedProfile(user_copies_per_role=4, product_count=60, counterparty_count=40, service_count=12),
}


def validate_fresh_mode(mode: str) -> None:
    """Validate the destructive refresh mode."""

    if mode not in {"tables", "database"}:
        raise ValueError("Fresh mode must be either 'tables' or 'database'.")


def profile_for_scale(scale: str) -> SeedProfile:
    """Return the configured seed profile for a scale name."""

    try:
        return SCALE_PROFILES[scale]
    except KeyError as exc:
        raise ValueError(f"Unknown seed scale '{scale}'.") from exc


def drop_configured_database(config: AppConfig) -> None:
    """Drop the configured MSSQL database after closing active connections."""

    db_name = config.database.database
    validate_database_name(db_name)
    quoted_name = _quote_sql_identifier(db_name)
    engine = create_db_engine(config, database_override="master")
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            exists = connection.execute(
                text("SELECT 1 FROM sys.databases WHERE name = :name"),
                {"name": db_name},
            ).scalar_one_or_none()
            if exists is None:
                return

            connection.execute(text(f"ALTER DATABASE {quoted_name} SET SINGLE_USER WITH ROLLBACK IMMEDIATE"))
            connection.execute(text(f"DROP DATABASE {quoted_name}"))
    finally:
        engine.dispose()


def drop_all_user_tables(config: AppConfig) -> None:
    """Drop all non-system tables from the configured MSSQL database."""

    engine = create_db_engine(config)
    drop_sql = text(
        """
        DECLARE @sql nvarchar(max) = N'';

        SELECT @sql = @sql
            + N'ALTER TABLE '
            + QUOTENAME(SCHEMA_NAME(parent_table.schema_id))
            + N'.'
            + QUOTENAME(parent_table.name)
            + N' DROP CONSTRAINT '
            + QUOTENAME(foreign_key.name)
            + N';'
        FROM sys.foreign_keys AS foreign_key
        INNER JOIN sys.tables AS parent_table
            ON parent_table.object_id = foreign_key.parent_object_id;

        EXEC sp_executesql @sql;

        SET @sql = N'';

        SELECT @sql = @sql
            + N'DROP TABLE '
            + QUOTENAME(schema_name(schema_row.schema_id))
            + N'.'
            + QUOTENAME(table_row.name)
            + N';'
        FROM sys.tables AS table_row
        INNER JOIN sys.schemas AS schema_row
            ON schema_row.schema_id = table_row.schema_id
        WHERE table_row.is_ms_shipped = 0;

        EXEC sp_executesql @sql;
        """
    )
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(drop_sql)
    finally:
        engine.dispose()


def prepare_fresh_schema(config: AppConfig, mode: FreshMode) -> None:
    """Destroy existing schema/data, recreate the DB shape, and grant service access."""

    validate_fresh_mode(mode)

    if mode == "database":
        drop_configured_database(config)
        create_database_if_missing(config)
    else:
        create_database_if_missing(config)
        drop_all_user_tables(config)

    run_migrations(config)
    grant_windows_service_database_access(config)


def fresh_seed_database(config: AppConfig, options: DemoSeedOptions, mode: FreshMode = "tables") -> DemoSeedResult:
    """Run a full Laravel-style fresh refresh and fake-data seed."""

    prepare_fresh_schema(config, mode)

    engine = create_db_engine(config)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            result = seed_demo_data(session, options)
            session.commit()
            return result
    finally:
        engine.dispose()


class DemoSeeder:
    """Insert coherent fake ERP data into a fresh database."""

    def __init__(self, session: Session, options: DemoSeedOptions) -> None:
        if Faker is None:
            raise RuntimeError("Faker is required for demo seeding. Run: pip install -r requirements.txt")

        self.session = session
        self.options = options
        self.profile = profile_for_scale(options.scale)
        self.random = random.Random(options.seed)
        self.fake = Faker("en_US")
        if options.seed is not None:
            self.fake.seed_instance(options.seed)

        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.today = self.now.date()

    def seed(self) -> DemoSeedResult:
        """Seed all mapped tables and return per-table row counts."""

        super_admin = seed_super_admin_user(self.session, None, self.options.super_admin_password)
        self.session.flush()

        roles = {role.name: role for role in self.session.query(Role).all()}
        workplaces = self._seed_workplaces()
        users = self._seed_users(roles, workplaces, super_admin)
        self._seed_sessions_and_audit(users)

        currencies = self._seed_currencies()
        warehouses = self._seed_warehouses()
        cash_registers, shifts = self._seed_cashier_layer(warehouses, users)
        groups = self._seed_product_groups()
        uoms = self._seed_uoms()
        products, product_uoms = self._seed_products(groups, uoms)
        product_set = self._seed_product_set(products)
        expense_categories = self._seed_expense_categories()
        services = self._seed_services(expense_categories)
        price_lists = self._seed_price_lists(currencies, products, product_uoms, uoms, services)
        counterparties = self._seed_counterparties(price_lists)
        contracts = self._seed_contracts(counterparties, currencies)
        self._attach_price_lists(counterparties, price_lists)
        self._seed_money_accounts(currencies)
        loyalty_cards = self._seed_loyalty(counterparties, users)
        promotions = self._seed_promotions(products, groups)
        self._seed_report_filters(users)
        self._seed_stock_opening(warehouses, products, product_uoms, users)
        purchase_invoice = self._seed_purchase_flow(
            users,
            warehouses,
            currencies,
            counterparties,
            contracts,
            products,
            product_uoms,
            services,
            expense_categories,
            shifts,
        )
        self._seed_warehouse_documents(warehouses, products, product_uoms, users)
        sale, sale_line = self._seed_sales_flow(
            users,
            warehouses,
            currencies,
            counterparties,
            contracts,
            price_lists,
            products,
            product_uoms,
            shifts,
            cash_registers,
            promotions,
            loyalty_cards,
        )
        self._seed_sale_return(users, warehouses, currencies, sale, sale_line, shifts, cash_registers)
        self._seed_cash_operations(shifts, cash_registers, users)

        # Keep the local variables live until the graph is fully flushed; this
        # also makes the intended dependency order obvious to future edits.
        _ = product_set, purchase_invoice
        self.session.flush()
        return DemoSeedResult(table_counts=count_seeded_tables(self.session))

    def _seed_workplaces(self) -> list[Workplace]:
        rows = [
            Workplace(code="HQ", name="Head Office", workplace_type="office", is_active=True),
            Workplace(code="POS-01", name="Main Cashier", workplace_type="cashier", is_active=True),
            Workplace(code="WH-OPS", name="Warehouse Operations", workplace_type="warehouse", is_active=True),
        ]
        self.session.add_all(rows)
        self.session.flush()
        return rows

    def _seed_users(
        self,
        roles: dict[str, Role],
        workplaces: list[Workplace],
        super_admin: User,
    ) -> list[User]:
        users = [super_admin]
        password_hash = hash_password(self.options.demo_user_password)
        role_workplaces = {
            "Accountant": workplaces[0],
            "Manager": workplaces[2],
            "Cashier": workplaces[1],
            "Auditor": workplaces[0],
        }

        for role_name in BUILTIN_ROLES:
            if role_name == SUPER_ADMIN_ROLE:
                continue
            role = roles[role_name]
            for index in range(1, self.profile.user_copies_per_role + 1):
                username = f"{role_name.lower().replace(' ', '_')}{index}"
                user = User(
                    username=username,
                    full_name=self._safe_text(self.fake.name(), 160),
                    password_hash=password_hash,
                    role=role,
                    workplace=role_workplaces.get(role_name),
                    is_active=True,
                )
                self.session.add(user)
                users.append(user)

        self.session.flush()
        return users

    def _seed_sessions_and_audit(self, users: list[User]) -> None:
        session_user = users[0]
        self.session.add(
            UserSession(
                user=session_user,
                token_hash=hash_session_token(f"demo-session-{session_user.username}"),
                expires_at=self.now + timedelta(hours=8),
                revoked_at=None,
                client_name="Seeded Desktop Client",
                client_version="demo",
                ip_address="127.0.0.1",
            )
        )
        self.session.add(
            AuditLog(
                user=session_user,
                action="fresh_seed",
                module="system",
                entity_name="database",
                entity_id="demo",
                details="Demo database was refreshed and seeded.",
                old_values=None,
                new_values=json.dumps({"scale": self.options.scale}, sort_keys=True),
                ip_address="127.0.0.1",
            )
        )
        self.session.flush()

    def _seed_currencies(self) -> dict[str, Currency]:
        existing = {row.code: row for row in self.session.query(Currency).all()}
        for code, name, symbol, rate in (
            ("USD", "US dollar", "$", Decimal("3.500000")),
            ("EUR", "Euro", "EUR", Decimal("3.800000")),
        ):
            currency = Currency(code=code, name=name, symbol=symbol, is_system=False, is_active=True)
            self.session.add(currency)
            existing[code] = currency
            self.session.flush()
            self.session.add(ExchangeRate(currency=currency, rate_date=self.today, rate_to_system=rate))

        tmt = existing["TMT"]
        self.session.add(ExchangeRate(currency=tmt, rate_date=self.today, rate_to_system=Decimal("1.000000")))
        self.session.flush()
        return existing

    def _seed_warehouses(self) -> list[Warehouse]:
        rows = [
            Warehouse(code="WH-MAIN", name="Main Warehouse", location=self._safe_text(self.fake.address(), 255)),
            Warehouse(code="WH-SHOP", name="Shop Floor", location=self._safe_text(self.fake.street_address(), 255)),
        ]
        self.session.add_all(rows)
        self.session.flush()
        return rows

    def _seed_cashier_layer(
        self,
        warehouses: list[Warehouse],
        users: list[User],
    ) -> tuple[list[CashRegister], list[CashShift]]:
        registers = [
            CashRegister(name="Main Register", warehouse=warehouses[1], is_active=True),
            CashRegister(name="Reserve Register", warehouse=warehouses[1], is_active=True),
        ]
        self.session.add_all(registers)
        self.session.flush()

        cashier = self._first_user_by_role(users, "Cashier")
        shift = CashShift(
            cash_register=registers[0],
            opened_by_user=cashier,
            closed_by_user=None,
            opened_at=self.now - timedelta(hours=4),
            closed_at=None,
            opening_amount=money("150.00"),
            closing_amount=None,
            status="open",
        )
        self.session.add(shift)
        self.session.flush()
        return registers, [shift]

    def _seed_product_groups(self) -> list[ProductGroup]:
        roots = [
            ProductGroup(code="FOOD", name_ru="Food", name_tk="Food", sort_order=1),
            ProductGroup(code="HOUSE", name_ru="Household", name_tk="Household", sort_order=2),
        ]
        self.session.add_all(roots)
        self.session.flush()

        child = ProductGroup(
            parent=roots[0],
            code="FOOD-DRINKS",
            name_ru="Drinks",
            name_tk="Drinks",
            sort_order=10,
        )
        self.session.add(child)
        self.session.flush()
        return [*roots, child]

    def _seed_uoms(self) -> dict[str, UnitOfMeasure]:
        existing = {row.code: row for row in self.session.query(UnitOfMeasure).all()}
        for code, name in (("box", "Box"), ("pack", "Pack")):
            row = UnitOfMeasure(code=code, name_ru=name, name_tk=name, is_active=True)
            self.session.add(row)
            existing[code] = row
        self.session.flush()
        return existing

    def _seed_products(
        self,
        groups: list[ProductGroup],
        uoms: dict[str, UnitOfMeasure],
    ) -> tuple[list[Product], list[ProductUom]]:
        products: list[Product] = []
        product_uoms: list[ProductUom] = []
        base_uoms = [uoms["pcs"], uoms["kg"], uoms["l"]]

        for index in range(1, self.profile.product_count + 1):
            base_uom = base_uoms[(index - 1) % len(base_uoms)]
            retail = money(Decimal(self.random.randint(8, 150)) + Decimal("0.99"))
            cost = money(retail * Decimal("0.65"))
            product = Product(
                sku=f"SKU-{index:04d}",
                name=self._safe_text(f"{self.fake.word().title()} Item {index}", 180),
                name_tk=self._safe_text(f"Demo Item {index}", 180),
                group=groups[index % len(groups)],
                base_uom=base_uom,
                product_type="standard",
                unit=base_uom.code,
                retail_price=retail,
                last_known_cost=cost,
                min_stock=quantity(self.random.randint(2, 12)),
                description=self._safe_text(self.fake.sentence(), 255),
                is_active=True,
            )
            self.session.add(product)
            products.append(product)
            self.session.flush()

            base_product_uom = ProductUom(product=product, uom=base_uom, coefficient=Decimal("1.000000"), is_base=True)
            self.session.add(base_product_uom)
            product_uoms.append(base_product_uom)

            if base_uom.code == "pcs":
                pack_uom = ProductUom(product=product, uom=uoms["box"], coefficient=Decimal("12.000000"), is_base=False)
                self.session.add(pack_uom)
                product_uoms.append(pack_uom)

            self.session.add(
                ProductBarcode(
                    product=product,
                    product_uom=base_product_uom,
                    barcode=f"200000{index:07d}",
                    is_weight_barcode=base_uom.code == "kg",
                )
            )

        self.session.flush()
        return products, product_uoms

    def _seed_product_set(self, products: list[Product]) -> ProductSet:
        product_set = ProductSet(code="SET-0001", name="Starter Bundle", fixed_price=money("99.90"), is_active=True)
        self.session.add(product_set)
        self.session.flush()

        for product in products[: min(3, len(products))]:
            self.session.add(ProductSetItem(product_set=product_set, product=product, quantity=quantity("1")))

        self.session.flush()
        return product_set

    def _seed_expense_categories(self) -> list[ExpenseCategory]:
        rows = [
            ExpenseCategory(code="EXP-DELIVERY", name_ru="Delivery", name_tk="Delivery"),
            ExpenseCategory(code="EXP-SERVICE", name_ru="Services", name_tk="Services"),
        ]
        self.session.add_all(rows)
        self.session.flush()
        return rows

    def _seed_services(self, expense_categories: list[ExpenseCategory]) -> list[Service]:
        services: list[Service] = []
        for index in range(1, self.profile.service_count + 1):
            service = Service(
                code=f"SVC-{index:04d}",
                name_ru=f"Demo Service {index}",
                name_tk=f"Demo Service {index}",
                service_type="sale" if index % 2 else "purchase",
                expense_category=expense_categories[index % len(expense_categories)],
                default_price=money(self.random.randint(15, 90)),
                is_active=True,
            )
            self.session.add(service)
            services.append(service)
            self.session.flush()
            self.session.add(ServiceBarcode(service=service, barcode=f"290000{index:07d}"))

        self.session.flush()
        return services

    def _seed_price_lists(
        self,
        currencies: dict[str, Currency],
        products: list[Product],
        product_uoms: list[ProductUom],
        uoms: dict[str, UnitOfMeasure],
        services: list[Service],
    ) -> list[PriceList]:
        price_list = PriceList(
            name_ru="Retail Price List",
            name_tk="Retail Price List",
            currency=currencies["TMT"],
            is_default=True,
            is_active=True,
            note="Seeded default price list.",
        )
        wholesale = PriceList(
            name_ru="Wholesale Price List",
            name_tk="Wholesale Price List",
            currency=currencies["TMT"],
            is_default=False,
            is_active=True,
            note="Seeded wholesale price list.",
        )
        self.session.add_all([price_list, wholesale])
        self.session.flush()

        base_uom_by_product_id = {row.product_id: row for row in product_uoms if row.is_base}
        for product in products:
            product_uom = base_uom_by_product_id[product.id]
            self.session.add(
                PriceListItem(
                    price_list=price_list,
                    product=product,
                    product_uom=product_uom,
                    uom=product.base_uom or uoms["pcs"],
                    price_tmt=price(product.retail_price),
                    valid_from=self.today - timedelta(days=30),
                    valid_to=None,
                )
            )
            self.session.add(
                PriceListItem(
                    price_list=wholesale,
                    product=product,
                    product_uom=product_uom,
                    uom=product.base_uom or uoms["pcs"],
                    price_tmt=price(product.retail_price * Decimal("0.90")),
                    valid_from=self.today - timedelta(days=30),
                    valid_to=None,
                )
            )

        for service in services:
            self.session.add(
                PriceListItem(
                    price_list=price_list,
                    service=service,
                    price_tmt=price(service.default_price),
                    valid_from=self.today - timedelta(days=30),
                )
            )

        self.session.flush()
        return [price_list, wholesale]

    def _seed_counterparties(self, price_lists: list[PriceList]) -> list[Counterparty]:
        categories = [
            CounterpartyCategory(name_ru="Retail Customers", name_tk="Retail Customers"),
            CounterpartyCategory(name_ru="Suppliers", name_tk="Suppliers"),
        ]
        self.session.add_all(categories)
        self.session.flush()

        counterparties: list[Counterparty] = []
        type_cycle = [
            ("supplier", 1, categories[1]),
            ("customer", 2, categories[0]),
            ("both", 3, categories[0]),
        ]
        for index in range(1, self.profile.counterparty_count + 1):
            counterparty_type, role_flags, category = type_cycle[(index - 1) % len(type_cycle)]
            counterparty = Counterparty(
                code=f"CP-{index:04d}",
                name=self._safe_text(self.fake.company(), 180),
                category=category,
                counterparty_type=counterparty_type,
                role_flags=role_flags,
                phone=self._safe_text(self.fake.phone_number(), 80),
                email=self._safe_text(self.fake.company_email(), 120),
                tax_id=f"TAX-{index:06d}",
                address=self._safe_text(self.fake.address(), 200),
                price_list=price_lists[0] if role_flags in {2, 3} else None,
                discount_percent=Decimal("3.00") if role_flags in {2, 3} else Decimal("0.00"),
                credit_limit_tmt=money("5000.00") if role_flags in {2, 3} else money("0.00"),
                note=self._safe_text(self.fake.sentence(), 255),
                is_active=True,
            )
            self.session.add(counterparty)
            counterparties.append(counterparty)

        self.session.flush()
        return counterparties

    def _seed_contracts(
        self,
        counterparties: list[Counterparty],
        currencies: dict[str, Currency],
    ) -> dict[int, Contract]:
        contracts: dict[int, Contract] = {}
        for index, counterparty in enumerate(counterparties, start=1):
            contract = Contract(
                counterparty=counterparty,
                currency=currencies["TMT"],
                number=f"CN-{index:04d}",
                title=f"Seeded contract {index}",
                start_date=self.today - timedelta(days=180),
                end_date=self.today + timedelta(days=180),
                is_active=True,
            )
            self.session.add(contract)
            contracts[counterparty.id] = contract

        self.session.flush()
        return contracts

    def _attach_price_lists(self, counterparties: list[Counterparty], price_lists: list[PriceList]) -> None:
        for counterparty in counterparties:
            if counterparty.role_flags in {2, 3}:
                counterparty.price_list = price_lists[0 if counterparty.id % 2 else 1]
        self.session.flush()

    def _seed_money_accounts(self, currencies: dict[str, Currency]) -> None:
        self.session.add_all(
            [
                MoneyAccount(
                    currency=currencies["TMT"],
                    name="Main Cash Account",
                    account_type="cash",
                    details="Seeded cash account.",
                    is_active=True,
                ),
                MoneyAccount(
                    currency=currencies["USD"],
                    name="USD Bank Account",
                    account_type="bank",
                    details="Seeded bank account.",
                    is_active=True,
                ),
            ]
        )
        self.session.flush()

    def _seed_loyalty(self, counterparties: list[Counterparty], users: list[User]) -> list[LoyaltyCard]:
        self.session.add(
            LoyaltySetting(
                earn_rate_percent=Decimal("2.00"),
                redemption_limit_percent=Decimal("50.00"),
                is_active=True,
                note="Seeded loyalty settings.",
            )
        )
        self.session.flush()

        cards: list[LoyaltyCard] = []
        customers = [row for row in counterparties if row.role_flags in {2, 3}]
        for index, counterparty in enumerate(customers[: max(1, min(3, len(customers)))], start=1):
            card = LoyaltyCard(
                card_number=f"LC-{index:06d}",
                counterparty=counterparty,
                owner_name=counterparty.name,
                phone=counterparty.phone,
                balance_tmt=money("0.00"),
                is_active=True,
                note="Seeded loyalty card.",
            )
            self.session.add(card)
            cards.append(card)
            self.session.flush()
            post_loyalty_transaction(
                self.session,
                card,
                transaction_type="adjustment",
                amount_tmt=money("25.00"),
                doc_type="seed",
                doc_id=index,
                note="Opening bonus balance.",
                user_id=users[0].id,
            )

        self.session.flush()
        return cards

    def _seed_promotions(self, products: list[Product], groups: list[ProductGroup]) -> list[Promotion]:
        promotions = [
            Promotion(
                name="Seeded Product Discount",
                promotion_type="discount",
                target_type="product",
                product=products[0],
                discount_type="percent",
                discount_value=Decimal("5.0000"),
                min_quantity=qty4("1"),
                valid_from=self.now - timedelta(days=7),
                valid_to=self.now + timedelta(days=30),
                is_active=True,
                note="Demo discount promotion.",
            ),
            Promotion(
                name="Seeded Gift Promo",
                promotion_type="gift",
                target_type="group",
                product_group=groups[0],
                gift_product=products[-1],
                gift_quantity=qty4("1"),
                valid_from=self.now - timedelta(days=7),
                valid_to=self.now + timedelta(days=30),
                is_active=True,
                note="Demo gift promotion.",
            ),
        ]
        self.session.add_all(promotions)
        self.session.flush()
        return promotions

    def _seed_report_filters(self, users: list[User]) -> None:
        self.session.add(
            ReportFilter(
                report_code="sales_summary",
                name="Current Month",
                filters_json=json.dumps({"period": "current_month"}, sort_keys=True),
                is_shared=True,
                created_by_user=users[0],
            )
        )
        self.session.flush()

    def _seed_stock_opening(
        self,
        warehouses: list[Warehouse],
        products: list[Product],
        product_uoms: list[ProductUom],
        users: list[User],
    ) -> None:
        base_uom_by_product_id = {row.product_id: row for row in product_uoms if row.is_base}
        for product in products:
            product_uom = base_uom_by_product_id[product.id]
            post_stock_movement(
                self.session,
                warehouse_id=warehouses[0].id,
                product_id=product.id,
                uom_id=product_uom.uom_id,
                movement_type="opening_balance",
                document_type="fresh_seed",
                document_id=None,
                quantity_delta=quantity(self.random.randint(30, 120)),
                unit_cost_tmt=money(product.last_known_cost),
                user_id=users[0].id,
            )

        self.session.flush()

    def _seed_purchase_flow(
        self,
        users: list[User],
        warehouses: list[Warehouse],
        currencies: dict[str, Currency],
        counterparties: list[Counterparty],
        contracts: dict[int, Contract],
        products: list[Product],
        product_uoms: list[ProductUom],
        services: list[Service],
        expense_categories: list[ExpenseCategory],
        shifts: list[CashShift],
    ) -> PurchaseInvoice:
        supplier = next(row for row in counterparties if row.role_flags in {1, 3})
        contract = contracts[supplier.id]
        product = products[0]
        product_uom = next(row for row in product_uoms if row.product_id == product.id and row.is_base)
        product_qty = qty4("10")
        product_price = price(product.last_known_cost)
        product_amount = money(product_qty * product_price)
        service_amount = money("35.00")
        total = money(product_amount + service_amount)

        order = PurchaseOrder(
            doc_number=generate_doc_number(self.session, PurchaseOrder, "PO"),
            doc_date=self.today - timedelta(days=5),
            counterparty=supplier,
            contract=contract,
            warehouse=warehouses[0],
            currency=currencies["TMT"],
            currency_rate=Decimal("1.000000"),
            total_amount_cur=total,
            total_amount_tmt=total,
            status="sent",
            note="Seeded purchase order.",
            created_by_user=users[0],
            sent_by_user=users[0],
            sent_at=self.now - timedelta(days=4),
        )
        self.session.add(order)
        self.session.flush()

        product_order_line = PurchaseOrderLine(
            order=order,
            product=product,
            product_uom=product_uom,
            uom=product_uom.uom,
            quantity_ordered=product_qty,
            quantity_received=product_qty,
            price_cur=product_price,
            price_tmt=product_price,
            amount_cur=product_amount,
            amount_tmt=product_amount,
        )
        service_order_line = PurchaseOrderLine(
            order=order,
            service=services[0],
            expense_category=expense_categories[0],
            quantity_ordered=qty4("1"),
            quantity_received=qty4("1"),
            price_cur=price(service_amount),
            price_tmt=price(service_amount),
            amount_cur=service_amount,
            amount_tmt=service_amount,
        )
        self.session.add_all([product_order_line, service_order_line])
        self.session.flush()

        invoice = PurchaseInvoice(
            doc_number=generate_doc_number(self.session, PurchaseInvoice, "PI"),
            doc_date=self.today - timedelta(days=3),
            purchase_order=order,
            counterparty=supplier,
            contract=contract,
            warehouse=warehouses[0],
            currency=currencies["TMT"],
            currency_rate=Decimal("1.000000"),
            total_amount_cur=total,
            total_amount_tmt=total,
            payment_status="unpaid",
            expiry_note="Seeded invoice expiry note.",
            is_return=False,
            status="posted",
            note="Seeded purchase invoice.",
            created_by_user_id=users[0].id,
            posted_by_user_id=users[0].id,
            posted_at=self.now - timedelta(days=2),
        )
        self.session.add(invoice)
        self.session.flush()

        self.session.add_all(
            [
                PurchaseInvoiceLine(
                    invoice=invoice,
                    purchase_order_line=product_order_line,
                    product=product,
                    product_uom=product_uom,
                    uom=product_uom.uom,
                    quantity=product_qty,
                    price_cur=product_price,
                    price_tmt=product_price,
                    amount_cur=product_amount,
                    amount_tmt=product_amount,
                    avg_cost_before=price(product.last_known_cost),
                    avg_cost_after=price(product_price),
                ),
                PurchaseInvoiceLine(
                    invoice=invoice,
                    purchase_order_line=service_order_line,
                    service=services[0],
                    expense_category=expense_categories[0],
                    quantity=qty4("1"),
                    price_cur=price(service_amount),
                    price_tmt=price(service_amount),
                    amount_cur=service_amount,
                    amount_tmt=service_amount,
                ),
            ]
        )
        self.session.flush()

        post_stock_movement(
            self.session,
            warehouse_id=warehouses[0].id,
            product_id=product.id,
            uom_id=product_uom.uom_id,
            movement_type="purchase",
            document_type="purchase_invoice",
            document_id=invoice.id,
            quantity_delta=quantity(product_qty),
            unit_cost_tmt=money(product_price),
            user_id=users[0].id,
        )
        post_debt_entry(
            self.session,
            counterparty_id=supplier.id,
            contract_id=contract.id,
            debt_type="payable",
            doc_type="purchase_invoice",
            doc_id=invoice.id,
            doc_number=invoice.doc_number,
            doc_date=self._as_datetime(invoice.doc_date),
            amount_tmt=total,
            currency_id=currencies["TMT"].id,
            amount_cur=total,
            note="Seeded payable.",
            user_id=users[0].id,
        )

        payment_amount = money(total / Decimal("2"))
        payment = Payment(
            doc_number=generate_doc_number(self.session, Payment, "PAY"),
            doc_date=self.now - timedelta(days=1),
            counterparty=supplier,
            contract=contract,
            direction="outgoing",
            payment_method="cash",
            amount_tmt=payment_amount,
            currency=currencies["TMT"],
            amount_cur=payment_amount,
            currency_rate=Decimal("1.000000"),
            cash_shift=shifts[0],
            status="posted",
            note="Seeded supplier payment.",
            created_by_user_id=users[0].id,
        )
        self.session.add(payment)
        self.session.flush()
        self.session.add(
            PaymentAllocation(
                payment=payment,
                doc_type="purchase_invoice",
                doc_id=invoice.id,
                allocated_amount=payment_amount,
            )
        )
        post_debt_entry(
            self.session,
            counterparty_id=supplier.id,
            contract_id=contract.id,
            debt_type="payable",
            doc_type="payment",
            doc_id=payment.id,
            doc_number=payment.doc_number,
            doc_date=payment.doc_date,
            amount_tmt=-payment_amount,
            currency_id=currencies["TMT"].id,
            amount_cur=-payment_amount,
            note="Seeded payable payment.",
            user_id=users[0].id,
        )
        update_purchase_invoice_payment_status(self.session, invoice)
        self.session.flush()
        return invoice

    def _seed_warehouse_documents(
        self,
        warehouses: list[Warehouse],
        products: list[Product],
        product_uoms: list[ProductUom],
        users: list[User],
    ) -> None:
        product = products[1]
        product_uom = next(row for row in product_uoms if row.product_id == product.id and row.is_base)

        transfer = StockTransfer(
            source_warehouse=warehouses[0],
            target_warehouse=warehouses[1],
            status="received",
            note="Seeded received transfer.",
            created_by_user_id=users[0].id,
            sent_by_user_id=users[0].id,
            received_by_user_id=users[0].id,
            sent_at=self.now - timedelta(hours=3),
            received_at=self.now - timedelta(hours=2),
        )
        self.session.add(transfer)
        self.session.flush()
        self.session.add(
            StockTransferLine(
                transfer=transfer,
                product=product,
                uom=product_uom.uom,
                quantity=quantity("4"),
                unit_cost_tmt=money(product.last_known_cost),
            )
        )
        self.session.flush()
        post_stock_movement(
            self.session,
            warehouse_id=warehouses[0].id,
            product_id=product.id,
            uom_id=product_uom.uom_id,
            movement_type="transfer_out",
            document_type="stock_transfer",
            document_id=transfer.id,
            quantity_delta=quantity("-4"),
            unit_cost_tmt=money(product.last_known_cost),
            user_id=users[0].id,
        )
        post_stock_movement(
            self.session,
            warehouse_id=warehouses[1].id,
            product_id=product.id,
            uom_id=product_uom.uom_id,
            movement_type="transfer_in",
            document_type="stock_transfer",
            document_id=transfer.id,
            quantity_delta=quantity("4"),
            unit_cost_tmt=money(product.last_known_cost),
            user_id=users[0].id,
        )

        writeoff = StockWriteoff(
            warehouse=warehouses[0],
            status="posted",
            reason_code="damaged",
            note="Seeded write-off.",
            created_by_user_id=users[0].id,
            posted_by_user_id=users[0].id,
            posted_at=self.now - timedelta(hours=1),
        )
        self.session.add(writeoff)
        self.session.flush()
        self.session.add(
            StockWriteoffLine(
                writeoff=writeoff,
                product=product,
                uom=product_uom.uom,
                quantity=quantity("1"),
                unit_cost_tmt=money(product.last_known_cost),
            )
        )
        self.session.flush()
        post_stock_movement(
            self.session,
            warehouse_id=warehouses[0].id,
            product_id=product.id,
            uom_id=product_uom.uom_id,
            movement_type="writeoff",
            document_type="stock_writeoff",
            document_id=writeoff.id,
            quantity_delta=quantity("-1"),
            unit_cost_tmt=money(product.last_known_cost),
            user_id=users[0].id,
        )

        balance = get_or_create_balance(self.session, warehouses[0].id, product.id, product_uom.uom_id)
        inventory = Inventory(
            warehouse=warehouses[0],
            status="posted",
            note="Seeded inventory count.",
            created_by_user_id=users[0].id,
            posted_by_user_id=users[0].id,
            posted_at=self.now,
        )
        self.session.add(inventory)
        self.session.flush()
        actual_qty = quantity(balance.quantity + Decimal("1.000"))
        self.session.add(
            InventoryLine(
                inventory=inventory,
                product=product,
                uom=product_uom.uom,
                qty_expected=quantity(balance.quantity),
                qty_actual=actual_qty,
                unit_cost_tmt=money(balance.avg_cost_tmt),
            )
        )
        post_stock_movement(
            self.session,
            warehouse_id=warehouses[0].id,
            product_id=product.id,
            uom_id=product_uom.uom_id,
            movement_type="inventory_plus",
            document_type="inventory",
            document_id=inventory.id,
            quantity_delta=quantity("1"),
            unit_cost_tmt=money(balance.avg_cost_tmt),
            user_id=users[0].id,
        )
        self.session.add(
            InventoryRevision(
                warehouse=warehouses[0],
                revision_date=self.today,
                note="Seeded revision checkpoint.",
                posted_by_user=users[0],
            )
        )
        self.session.flush()

    def _seed_sales_flow(
        self,
        users: list[User],
        warehouses: list[Warehouse],
        currencies: dict[str, Currency],
        counterparties: list[Counterparty],
        contracts: dict[int, Contract],
        price_lists: list[PriceList],
        products: list[Product],
        product_uoms: list[ProductUom],
        shifts: list[CashShift],
        cash_registers: list[CashRegister],
        promotions: list[Promotion],
        loyalty_cards: list[LoyaltyCard],
    ) -> tuple[Sale, SaleLine]:
        customer = next(row for row in counterparties if row.role_flags in {2, 3})
        contract = contracts[customer.id]
        product = products[2]
        product_uom = next(row for row in product_uoms if row.product_id == product.id and row.is_base)
        sale_qty = qty4("2")
        unit_price = price(product.retail_price)
        discount_percent = Decimal("5.00")
        gross = money(sale_qty * unit_price)
        discount_amount = money(gross * Decimal("0.05"))
        total = money(gross - discount_amount)
        card = loyalty_cards[0] if loyalty_cards else None

        sale = Sale(
            doc_number=generate_doc_number(self.session, Sale, "SALE"),
            doc_date=self.now - timedelta(hours=2),
            sale_type="wholesale",
            cash_register=cash_registers[0],
            cash_shift=shifts[0],
            counterparty=customer,
            contract=contract,
            warehouse=warehouses[0],
            price_list=price_lists[0],
            currency=currencies["TMT"],
            currency_rate=Decimal("1.000000"),
            discount_percent=discount_percent,
            discount_amount_tmt=discount_amount,
            total_amount_tmt=total,
            payment_type="debt",
            paid_cash_tmt=money("0.00"),
            paid_transfer_tmt=money("0.00"),
            paid_bonus_tmt=money("0.00"),
            debt_amount_tmt=total,
            loyalty_card=card,
            status="posted",
            admin_override_by_user=users[0],
            created_by_user=users[0],
            posted_by_user=users[0],
            posted_at=self.now - timedelta(hours=1, minutes=45),
        )
        self.session.add(sale)
        self.session.flush()

        line = SaleLine(
            sale=sale,
            line_type="product",
            product=product,
            product_uom=product_uom,
            uom=product_uom.uom,
            quantity=sale_qty,
            price_list_price=unit_price,
            price_final=price(unit_price * Decimal("0.95")),
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            amount_tmt=total,
            avg_cost_tmt=price(product.last_known_cost),
            promotion=promotions[0],
            price_override=False,
        )
        self.session.add(line)
        self.session.flush()

        post_stock_movement(
            self.session,
            warehouse_id=warehouses[0].id,
            product_id=product.id,
            uom_id=product_uom.uom_id,
            movement_type="sale",
            document_type="sale",
            document_id=sale.id,
            quantity_delta=quantity("-2"),
            unit_cost_tmt=money(product.last_known_cost),
            user_id=users[0].id,
        )
        post_debt_entry(
            self.session,
            counterparty_id=customer.id,
            contract_id=contract.id,
            debt_type="receivable",
            doc_type="sale",
            doc_id=sale.id,
            doc_number=sale.doc_number,
            doc_date=sale.doc_date,
            amount_tmt=total,
            currency_id=currencies["TMT"].id,
            amount_cur=total,
            note="Seeded sale receivable.",
            user_id=users[0].id,
        )
        if card is not None:
            post_loyalty_transaction(
                self.session,
                card,
                transaction_type="earn",
                amount_tmt=money(total * Decimal("0.02")),
                doc_type="sale",
                doc_id=sale.id,
                note="Seeded loyalty earn.",
                user_id=users[0].id,
            )

        payment_amount = money(total / Decimal("2"))
        payment = Payment(
            doc_number=generate_doc_number(self.session, Payment, "PAY"),
            doc_date=self.now - timedelta(minutes=45),
            counterparty=customer,
            contract=contract,
            direction="incoming",
            payment_method="transfer",
            amount_tmt=payment_amount,
            currency=currencies["TMT"],
            amount_cur=payment_amount,
            currency_rate=Decimal("1.000000"),
            cash_shift=shifts[0],
            status="posted",
            note="Seeded customer payment.",
            created_by_user_id=users[0].id,
        )
        self.session.add(payment)
        self.session.flush()
        self.session.add(PaymentAllocation(payment=payment, doc_type="sale", doc_id=sale.id, allocated_amount=payment_amount))
        post_debt_entry(
            self.session,
            counterparty_id=customer.id,
            contract_id=contract.id,
            debt_type="receivable",
            doc_type="payment",
            doc_id=payment.id,
            doc_number=payment.doc_number,
            doc_date=payment.doc_date,
            amount_tmt=-payment_amount,
            currency_id=currencies["TMT"].id,
            amount_cur=-payment_amount,
            note="Seeded receivable payment.",
            user_id=users[0].id,
        )
        self.session.flush()
        return sale, line

    def _seed_sale_return(
        self,
        users: list[User],
        warehouses: list[Warehouse],
        currencies: dict[str, Currency],
        sale: Sale,
        sale_line: SaleLine,
        shifts: list[CashShift],
        cash_registers: list[CashRegister],
    ) -> None:
        return_qty = qty4("1")
        amount = money(sale_line.price_final * return_qty)
        sale_return = SaleReturn(
            doc_number=generate_doc_number(self.session, SaleReturn, "SR"),
            doc_date=self.now - timedelta(minutes=20),
            sale=sale,
            cash_register=cash_registers[0],
            cash_shift=shifts[0],
            counterparty=sale.counterparty,
            warehouse=warehouses[0],
            currency=currencies["TMT"],
            currency_rate=Decimal("1.000000"),
            total_amount_tmt=amount,
            refund_method="cash",
            refund_cash_tmt=amount,
            refund_transfer_tmt=money("0.00"),
            refund_bonus_tmt=money("0.00"),
            receivable_correction_tmt=money("0.00"),
            status="posted",
            note="Seeded sale return.",
            created_by_user=users[0],
            posted_by_user=users[0],
            posted_at=self.now - timedelta(minutes=10),
        )
        self.session.add(sale_return)
        self.session.flush()
        self.session.add(
            SaleReturnLine(
                sale_return=sale_return,
                source_sale_line=sale_line,
                product=sale_line.product,
                product_uom=sale_line.product_uom,
                uom=sale_line.uom,
                quantity=return_qty,
                price_final=sale_line.price_final,
                amount_tmt=amount,
                avg_cost_tmt=sale_line.avg_cost_tmt,
            )
        )
        self.session.flush()
        post_stock_movement(
            self.session,
            warehouse_id=warehouses[0].id,
            product_id=sale_line.product_id,
            uom_id=sale_line.uom_id,
            movement_type="sale_return",
            document_type="sale_return",
            document_id=sale_return.id,
            quantity_delta=quantity("1"),
            unit_cost_tmt=money(sale_line.avg_cost_tmt),
            user_id=users[0].id,
        )
        self.session.flush()

    def _seed_cash_operations(
        self,
        shifts: list[CashShift],
        cash_registers: list[CashRegister],
        users: list[User],
    ) -> None:
        self.session.add(
            CashOperation(
                doc_number=generate_doc_number(self.session, CashOperation, "CASH"),
                doc_date=self.now - timedelta(minutes=5),
                cash_shift=shifts[0],
                cash_register_from=cash_registers[0],
                cash_register_to=None,
                operation_type="collection",
                amount_tmt=money("50.00"),
                note="Seeded cash collection.",
                created_by_user=users[0],
            )
        )
        self.session.flush()

    def _first_user_by_role(self, users: list[User], role_name: str) -> User:
        for user in users:
            if user.role is not None and user.role.name == role_name:
                return user
        return users[0]

    def _safe_text(self, value: str, max_length: int) -> str:
        value = " ".join(value.split())
        return value[:max_length]

    def _as_datetime(self, value: date) -> datetime:
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def seed_demo_data(session: Session, options: DemoSeedOptions) -> DemoSeedResult:
    """Seed a fresh database with coherent fake rows for every mapped table."""

    return DemoSeeder(session, options).seed()


def count_seeded_tables(session: Session) -> dict[str, int]:
    """Return row counts for every mapped table."""

    counts: dict[str, int] = {}
    for table in Base.metadata.sorted_tables:
        count = session.execute(select(func.count()).select_from(table)).scalar_one()
        counts[table.name] = int(count)
    return counts
