"""Foundation reference-data CRUD API routes."""

from __future__ import annotations

from typing import Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload

from server_app.api.dependencies import get_current_user, get_db, require_owner
from server_app.db.models import (
    Contract,
    Counterparty,
    Currency,
    ExchangeRate,
    MoneyAccount,
    Product,
    ProductSet,
    ProductSetItem,
    User,
    Warehouse,
)
from server_app.schemas.foundation import (
    ContractCreate,
    ContractRead,
    ContractUpdate,
    CounterpartyCreate,
    CounterpartyRead,
    CounterpartyUpdate,
    CurrencyCreate,
    CurrencyRead,
    CurrencyUpdate,
    ExchangeRateCreate,
    ExchangeRateRead,
    ExchangeRateUpdate,
    MoneyAccountCreate,
    MoneyAccountRead,
    MoneyAccountUpdate,
    ProductCreate,
    ProductRead,
    ProductSetCreate,
    ProductSetRead,
    ProductSetUpdate,
    ProductUpdate,
    WarehouseCreate,
    WarehouseRead,
    WarehouseUpdate,
)


router = APIRouter(prefix="/reference", tags=["reference-data"])
ModelT = TypeVar("ModelT")


def _get_or_404(session: Session, model: type[ModelT], object_id: int, name: str) -> ModelT:
    """Load one model by id or raise a standard HTTP 404 response."""

    item = session.get(model, object_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{name} not found.")
    return item


def _non_none_updates(payload: Any) -> dict[str, Any]:
    """Return only fields explicitly set to non-None values."""

    return payload.model_dump(exclude_unset=True, exclude_none=True)


def _apply_updates(item: Any, payload: Any) -> None:
    """Apply a Pydantic update payload to a SQLAlchemy object."""

    for key, value in _non_none_updates(payload).items():
        setattr(item, key, value)


def _commit_refresh(session: Session, item: ModelT) -> ModelT:
    """Commit a change and refresh the changed ORM object."""

    session.commit()
    session.refresh(item)
    return item


def _deactivate_or_delete(session: Session, item: Any) -> None:
    """Prefer soft deactivation when the model has an ``is_active`` field."""

    if hasattr(item, "is_active"):
        item.is_active = False
    else:
        session.delete(item)
    session.commit()


@router.get("/currencies", response_model=list[CurrencyRead])
def list_currencies(
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[Currency]:
    """List currencies."""

    return session.query(Currency).order_by(Currency.code).all()


@router.post("/currencies", response_model=CurrencyRead, status_code=status.HTTP_201_CREATED)
def create_currency(
    payload: CurrencyCreate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> Currency:
    """Create a currency."""

    currency = Currency(**payload.model_dump())
    session.add(currency)
    return _commit_refresh(session, currency)


@router.get("/currencies/{currency_id}", response_model=CurrencyRead)
def get_currency(
    currency_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Currency:
    """Return one currency."""

    return _get_or_404(session, Currency, currency_id, "Currency")


@router.patch("/currencies/{currency_id}", response_model=CurrencyRead)
def update_currency(
    currency_id: int,
    payload: CurrencyUpdate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> Currency:
    """Update a currency."""

    currency = _get_or_404(session, Currency, currency_id, "Currency")
    _apply_updates(currency, payload)
    return _commit_refresh(session, currency)


@router.delete("/currencies/{currency_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_currency(
    currency_id: int,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> None:
    """Deactivate a currency."""

    currency = _get_or_404(session, Currency, currency_id, "Currency")
    _deactivate_or_delete(session, currency)


@router.get("/exchange-rates", response_model=list[ExchangeRateRead])
def list_exchange_rates(
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[ExchangeRate]:
    """List exchange rates."""

    return session.query(ExchangeRate).order_by(ExchangeRate.rate_date.desc()).all()


@router.post("/exchange-rates", response_model=ExchangeRateRead, status_code=status.HTTP_201_CREATED)
def create_exchange_rate(
    payload: ExchangeRateCreate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> ExchangeRate:
    """Create an exchange-rate row."""

    rate = ExchangeRate(**payload.model_dump())
    session.add(rate)
    return _commit_refresh(session, rate)


@router.get("/exchange-rates/{rate_id}", response_model=ExchangeRateRead)
def get_exchange_rate(
    rate_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ExchangeRate:
    """Return one exchange-rate row."""

    return _get_or_404(session, ExchangeRate, rate_id, "Exchange rate")


@router.patch("/exchange-rates/{rate_id}", response_model=ExchangeRateRead)
def update_exchange_rate(
    rate_id: int,
    payload: ExchangeRateUpdate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> ExchangeRate:
    """Update an exchange-rate row."""

    rate = _get_or_404(session, ExchangeRate, rate_id, "Exchange rate")
    _apply_updates(rate, payload)
    return _commit_refresh(session, rate)


@router.delete("/exchange-rates/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exchange_rate(
    rate_id: int,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> None:
    """Delete an exchange-rate row."""

    rate = _get_or_404(session, ExchangeRate, rate_id, "Exchange rate")
    _deactivate_or_delete(session, rate)


@router.get("/warehouses", response_model=list[WarehouseRead])
def list_warehouses(
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[Warehouse]:
    """List warehouses."""

    return session.query(Warehouse).order_by(Warehouse.code).all()


@router.post("/warehouses", response_model=WarehouseRead, status_code=status.HTTP_201_CREATED)
def create_warehouse(
    payload: WarehouseCreate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> Warehouse:
    """Create a warehouse."""

    warehouse = Warehouse(**payload.model_dump())
    session.add(warehouse)
    return _commit_refresh(session, warehouse)


@router.get("/warehouses/{warehouse_id}", response_model=WarehouseRead)
def get_warehouse(
    warehouse_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Warehouse:
    """Return one warehouse."""

    return _get_or_404(session, Warehouse, warehouse_id, "Warehouse")


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseRead)
def update_warehouse(
    warehouse_id: int,
    payload: WarehouseUpdate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> Warehouse:
    """Update a warehouse."""

    warehouse = _get_or_404(session, Warehouse, warehouse_id, "Warehouse")
    _apply_updates(warehouse, payload)
    return _commit_refresh(session, warehouse)


@router.delete("/warehouses/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_warehouse(
    warehouse_id: int,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> None:
    """Deactivate a warehouse."""

    warehouse = _get_or_404(session, Warehouse, warehouse_id, "Warehouse")
    _deactivate_or_delete(session, warehouse)


@router.get("/products", response_model=list[ProductRead])
def list_products(
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[Product]:
    """List products."""

    return session.query(Product).order_by(Product.sku).all()


@router.post("/products", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> Product:
    """Create a product."""

    product = Product(**payload.model_dump())
    session.add(product)
    return _commit_refresh(session, product)


@router.get("/products/{product_id}", response_model=ProductRead)
def get_product(
    product_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Product:
    """Return one product."""

    return _get_or_404(session, Product, product_id, "Product")


@router.patch("/products/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> Product:
    """Update a product."""

    product = _get_or_404(session, Product, product_id, "Product")
    _apply_updates(product, payload)
    return _commit_refresh(session, product)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> None:
    """Deactivate a product."""

    product = _get_or_404(session, Product, product_id, "Product")
    _deactivate_or_delete(session, product)


def _replace_product_set_items(
    session: Session,
    product_set: ProductSet,
    payload: ProductSetCreate | ProductSetUpdate,
) -> None:
    """Replace component lines inside a product set."""

    if payload.items is None:
        return

    product_set.items.clear()
    session.flush()

    for item_payload in payload.items:
        _get_or_404(session, Product, item_payload.product_id, "Product")
        product_set.items.append(
            ProductSetItem(
                product_id=item_payload.product_id,
                quantity=item_payload.quantity,
            )
        )


@router.get("/product-sets", response_model=list[ProductSetRead])
def list_product_sets(
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[ProductSet]:
    """List product sets with component items."""

    return (
        session.query(ProductSet)
        .options(selectinload(ProductSet.items))
        .order_by(ProductSet.code)
        .all()
    )


@router.post("/product-sets", response_model=ProductSetRead, status_code=status.HTTP_201_CREATED)
def create_product_set(
    payload: ProductSetCreate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> ProductSet:
    """Create a product set."""

    product_set = ProductSet(
        code=payload.code,
        name=payload.name,
        fixed_price=payload.fixed_price,
        is_active=payload.is_active,
    )
    session.add(product_set)
    _replace_product_set_items(session, product_set, payload)
    session.commit()
    product_set = (
        session.query(ProductSet)
        .options(selectinload(ProductSet.items))
        .filter(ProductSet.id == product_set.id)
        .one()
    )
    return product_set


@router.get("/product-sets/{product_set_id}", response_model=ProductSetRead)
def get_product_set(
    product_set_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ProductSet:
    """Return one product set with component items."""

    product_set = (
        session.query(ProductSet)
        .options(selectinload(ProductSet.items))
        .filter(ProductSet.id == product_set_id)
        .one_or_none()
    )
    if product_set is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product set not found.")
    return product_set


@router.patch("/product-sets/{product_set_id}", response_model=ProductSetRead)
def update_product_set(
    product_set_id: int,
    payload: ProductSetUpdate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> ProductSet:
    """Update a product set and optionally replace its items."""

    product_set = _get_or_404(session, ProductSet, product_set_id, "Product set")
    updates = _non_none_updates(payload)
    updates.pop("items", None)
    for key, value in updates.items():
        setattr(product_set, key, value)

    _replace_product_set_items(session, product_set, payload)
    session.commit()
    product_set = (
        session.query(ProductSet)
        .options(selectinload(ProductSet.items))
        .filter(ProductSet.id == product_set_id)
        .one()
    )
    return product_set


@router.delete("/product-sets/{product_set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_set(
    product_set_id: int,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> None:
    """Deactivate a product set."""

    product_set = _get_or_404(session, ProductSet, product_set_id, "Product set")
    _deactivate_or_delete(session, product_set)


@router.get("/counterparties", response_model=list[CounterpartyRead])
def list_counterparties(
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[Counterparty]:
    """List counterparties."""

    return session.query(Counterparty).order_by(Counterparty.name).all()


@router.post("/counterparties", response_model=CounterpartyRead, status_code=status.HTTP_201_CREATED)
def create_counterparty(
    payload: CounterpartyCreate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> Counterparty:
    """Create a counterparty."""

    counterparty = Counterparty(**payload.model_dump())
    session.add(counterparty)
    return _commit_refresh(session, counterparty)


@router.get("/counterparties/{counterparty_id}", response_model=CounterpartyRead)
def get_counterparty(
    counterparty_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Counterparty:
    """Return one counterparty."""

    return _get_or_404(session, Counterparty, counterparty_id, "Counterparty")


@router.patch("/counterparties/{counterparty_id}", response_model=CounterpartyRead)
def update_counterparty(
    counterparty_id: int,
    payload: CounterpartyUpdate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> Counterparty:
    """Update a counterparty."""

    counterparty = _get_or_404(session, Counterparty, counterparty_id, "Counterparty")
    _apply_updates(counterparty, payload)
    return _commit_refresh(session, counterparty)


@router.delete("/counterparties/{counterparty_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_counterparty(
    counterparty_id: int,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> None:
    """Deactivate a counterparty."""

    counterparty = _get_or_404(session, Counterparty, counterparty_id, "Counterparty")
    _deactivate_or_delete(session, counterparty)


@router.get("/contracts", response_model=list[ContractRead])
def list_contracts(
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[Contract]:
    """List contracts."""

    return session.query(Contract).order_by(Contract.number).all()


@router.post("/contracts", response_model=ContractRead, status_code=status.HTTP_201_CREATED)
def create_contract(
    payload: ContractCreate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> Contract:
    """Create a contract."""

    _get_or_404(session, Counterparty, payload.counterparty_id, "Counterparty")
    if payload.currency_id is not None:
        _get_or_404(session, Currency, payload.currency_id, "Currency")
    contract = Contract(**payload.model_dump())
    session.add(contract)
    return _commit_refresh(session, contract)


@router.get("/contracts/{contract_id}", response_model=ContractRead)
def get_contract(
    contract_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Contract:
    """Return one contract."""

    return _get_or_404(session, Contract, contract_id, "Contract")


@router.patch("/contracts/{contract_id}", response_model=ContractRead)
def update_contract(
    contract_id: int,
    payload: ContractUpdate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> Contract:
    """Update a contract."""

    contract = _get_or_404(session, Contract, contract_id, "Contract")
    if payload.currency_id is not None:
        _get_or_404(session, Currency, payload.currency_id, "Currency")
    _apply_updates(contract, payload)
    return _commit_refresh(session, contract)


@router.delete("/contracts/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract(
    contract_id: int,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> None:
    """Deactivate a contract."""

    contract = _get_or_404(session, Contract, contract_id, "Contract")
    _deactivate_or_delete(session, contract)


@router.get("/money-accounts", response_model=list[MoneyAccountRead])
def list_money_accounts(
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[MoneyAccount]:
    """List cash and bank accounts."""

    return session.query(MoneyAccount).order_by(MoneyAccount.name).all()


@router.post("/money-accounts", response_model=MoneyAccountRead, status_code=status.HTTP_201_CREATED)
def create_money_account(
    payload: MoneyAccountCreate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> MoneyAccount:
    """Create a cash or bank account."""

    _get_or_404(session, Currency, payload.currency_id, "Currency")
    account = MoneyAccount(**payload.model_dump())
    session.add(account)
    return _commit_refresh(session, account)


@router.get("/money-accounts/{account_id}", response_model=MoneyAccountRead)
def get_money_account(
    account_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> MoneyAccount:
    """Return one cash or bank account."""

    return _get_or_404(session, MoneyAccount, account_id, "Money account")


@router.patch("/money-accounts/{account_id}", response_model=MoneyAccountRead)
def update_money_account(
    account_id: int,
    payload: MoneyAccountUpdate,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> MoneyAccount:
    """Update a cash or bank account."""

    account = _get_or_404(session, MoneyAccount, account_id, "Money account")
    if payload.currency_id is not None:
        _get_or_404(session, Currency, payload.currency_id, "Currency")
    _apply_updates(account, payload)
    return _commit_refresh(session, account)


@router.delete("/money-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_money_account(
    account_id: int,
    _: User = Depends(require_owner),
    session: Session = Depends(get_db),
) -> None:
    """Deactivate a cash or bank account."""

    account = _get_or_404(session, MoneyAccount, account_id, "Money account")
    _deactivate_or_delete(session, account)
