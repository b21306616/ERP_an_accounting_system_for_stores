"""API v1 routes for counterparties, pricing, purchases, and settlements."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from server_app.api.dependencies import get_db
from server_app.api.routers_v1 import error_detail, require_v1_permission, success_response
from server_app.db.models import (
    Counterparty,
    CounterpartyCategory,
    Currency,
    DebtLedger,
    ExpenseCategory,
    Payment,
    PaymentAllocation,
    PriceList,
    PriceListItem,
    Product,
    ProductUom,
    PurchaseInvoice,
    PurchaseInvoiceLine,
    Service,
    UnitOfMeasure,
    User,
    Warehouse,
)
from server_app.schemas.business_v1 import (
    CounterpartyCategoryCreate,
    CounterpartyCreate,
    CounterpartyUpdate,
    PaymentCreate,
    PriceListCreate,
    PriceListItemCreate,
    PurchaseInvoiceCreate,
)
from server_app.services.settlements import (
    current_debt_balance,
    generate_doc_number,
    money,
    now_utc,
    post_debt_entry,
    price,
    qty4,
    update_purchase_invoice_payment_status,
)
from server_app.services.warehouse import WarehouseBusinessError, get_or_create_balance, post_stock_movement


router = APIRouter(prefix="/api/v1", tags=["business"])
require_counterparty_view = require_v1_permission("counterparty.view")
require_counterparty_create = require_v1_permission("counterparty.create")
require_counterparty_edit = require_v1_permission("counterparty.edit")
require_counterparty_category = require_v1_permission("counterparty.category_manage")
require_debt_view = require_v1_permission("counterparty.debt_view")
require_payment_create = require_v1_permission("counterparty.payment_create")
require_payment_cancel = require_v1_permission("counterparty.payment_cancel")
require_pricing_view = require_v1_permission("pricing.view")
require_pricing_create = require_v1_permission("pricing.price_list_create")
require_pricing_edit = require_v1_permission("pricing.price_list_edit")
require_purchase_view = require_v1_permission("purchase.view")
require_purchase_create = require_v1_permission("purchase.invoice_create")
require_purchase_post = require_v1_permission("purchase.post")
require_purchase_cancel = require_v1_permission("purchase.cancel")


def _decimal(value: Decimal | int | str | None, places: str) -> str:
    """Return a decimal value as a normalized string."""

    if value is None:
        value = Decimal("0")
    return str(Decimal(value).quantize(Decimal(places)))


def _doc_datetime(doc_date: date) -> datetime:
    """Convert a date document field into a UTC datetime for ledgers."""

    return datetime.combine(doc_date, time.min, tzinfo=timezone.utc)


def _get_or_404(session: Session, model: type[Any], object_id: int, name: str) -> Any:
    """Load one row by primary key or raise a v1 error."""

    item = session.get(model, object_id)
    if item is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", f"{name} not found."))
    return item


def _updates(payload: Any) -> dict[str, Any]:
    """Return explicitly supplied update fields."""

    return payload.model_dump(exclude_unset=True)


def _currency_payload(currency: Currency) -> dict[str, Any]:
    """Return a currency payload."""

    return {
        "id": currency.id,
        "code": currency.code,
        "name": currency.name,
        "symbol": currency.symbol,
        "is_system": currency.is_system,
        "is_active": currency.is_active,
    }


def _category_payload(category: CounterpartyCategory) -> dict[str, Any]:
    """Return a counterparty category payload."""

    return {"id": category.id, "name_ru": category.name_ru, "name_tk": category.name_tk}


def _counterparty_payload(session: Session, row: Counterparty, include_debt: bool = False) -> dict[str, Any]:
    """Return a counterparty payload."""

    data = {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "category_id": row.category_id,
        "category_name_ru": row.category.name_ru if row.category else None,
        "counterparty_type": row.counterparty_type,
        "role_flags": row.role_flags,
        "phone": row.phone,
        "email": row.email,
        "tax_id": row.tax_id,
        "address": row.address,
        "price_list_id": row.price_list_id,
        "price_list_name_ru": row.price_list.name_ru if row.price_list else None,
        "discount_percent": _decimal(row.discount_percent, "0.01"),
        "credit_limit_tmt": _decimal(row.credit_limit_tmt, "0.01"),
        "note": row.note,
        "is_active": row.is_active,
    }
    if include_debt:
        data["debt"] = {
            "receivable": _decimal(current_debt_balance(session, row.id, "receivable"), "0.01"),
            "payable": _decimal(current_debt_balance(session, row.id, "payable"), "0.01"),
        }
    return data


def _price_list_payload(row: PriceList) -> dict[str, Any]:
    """Return a price-list payload."""

    return {
        "id": row.id,
        "name_ru": row.name_ru,
        "name_tk": row.name_tk,
        "currency_id": row.currency_id,
        "currency_code": row.currency.code if row.currency else None,
        "is_default": row.is_default,
        "is_active": row.is_active,
        "note": row.note,
    }


def _price_item_payload(row: PriceListItem) -> dict[str, Any]:
    """Return a price-list item payload."""

    return {
        "id": row.id,
        "price_list_id": row.price_list_id,
        "product_id": row.product_id,
        "product_sku": row.product.sku if row.product else None,
        "product_name": row.product.name if row.product else None,
        "service_id": row.service_id,
        "service_code": row.service.code if row.service else None,
        "service_name_ru": row.service.name_ru if row.service else None,
        "product_uom_id": row.product_uom_id,
        "uom_id": row.uom_id,
        "uom_code": row.uom.code if row.uom else None,
        "price_tmt": _decimal(row.price_tmt, "0.0001"),
        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
    }


def _invoice_line_payload(line: PurchaseInvoiceLine) -> dict[str, Any]:
    """Return a purchase invoice line payload."""

    return {
        "id": line.id,
        "product_id": line.product_id,
        "product_sku": line.product.sku if line.product else None,
        "product_name": line.product.name if line.product else None,
        "service_id": line.service_id,
        "service_code": line.service.code if line.service else None,
        "service_name_ru": line.service.name_ru if line.service else None,
        "expense_category_id": line.expense_category_id,
        "product_uom_id": line.product_uom_id,
        "uom_id": line.uom_id,
        "uom_code": line.uom.code if line.uom else None,
        "quantity": _decimal(line.quantity, "0.0001"),
        "price_cur": _decimal(line.price_cur, "0.0001"),
        "price_tmt": _decimal(line.price_tmt, "0.0001"),
        "amount_cur": _decimal(line.amount_cur, "0.01"),
        "amount_tmt": _decimal(line.amount_tmt, "0.01"),
        "avg_cost_before": _decimal(line.avg_cost_before, "0.0001") if line.avg_cost_before is not None else None,
        "avg_cost_after": _decimal(line.avg_cost_after, "0.0001") if line.avg_cost_after is not None else None,
    }


def _invoice_payload(invoice: PurchaseInvoice) -> dict[str, Any]:
    """Return a purchase invoice payload."""

    return {
        "id": invoice.id,
        "doc_number": invoice.doc_number,
        "doc_date": invoice.doc_date.isoformat() if invoice.doc_date else None,
        "counterparty_id": invoice.counterparty_id,
        "counterparty_name": invoice.counterparty.name if invoice.counterparty else None,
        "warehouse_id": invoice.warehouse_id,
        "warehouse_name": invoice.warehouse.name if invoice.warehouse else None,
        "currency_id": invoice.currency_id,
        "currency_code": invoice.currency.code if invoice.currency else None,
        "currency_rate": _decimal(invoice.currency_rate, "0.000001"),
        "total_amount_cur": _decimal(invoice.total_amount_cur, "0.01"),
        "total_amount_tmt": _decimal(invoice.total_amount_tmt, "0.01"),
        "payment_status": invoice.payment_status,
        "expiry_note": invoice.expiry_note,
        "is_return": invoice.is_return,
        "return_invoice_id": invoice.return_invoice_id,
        "status": invoice.status,
        "note": invoice.note,
        "posted_by_user_id": invoice.posted_by_user_id,
        "posted_at": invoice.posted_at.isoformat() if invoice.posted_at else None,
        "lines": [_invoice_line_payload(line) for line in invoice.lines],
    }


def _debt_payload(row: DebtLedger) -> dict[str, Any]:
    """Return a debt ledger payload."""

    return {
        "id": row.id,
        "counterparty_id": row.counterparty_id,
        "counterparty_name": row.counterparty.name if row.counterparty else None,
        "debt_type": row.debt_type,
        "doc_type": row.doc_type,
        "doc_id": row.doc_id,
        "doc_number": row.doc_number,
        "doc_date": row.doc_date.isoformat() if row.doc_date else None,
        "amount_tmt": _decimal(row.amount_tmt, "0.01"),
        "balance_after": _decimal(row.balance_after, "0.01"),
        "currency_id": row.currency_id,
        "amount_cur": _decimal(row.amount_cur, "0.01") if row.amount_cur is not None else None,
        "note": row.note,
    }


def _payment_payload(payment: Payment) -> dict[str, Any]:
    """Return a payment payload."""

    return {
        "id": payment.id,
        "doc_number": payment.doc_number,
        "doc_date": payment.doc_date.isoformat() if payment.doc_date else None,
        "counterparty_id": payment.counterparty_id,
        "counterparty_name": payment.counterparty.name if payment.counterparty else None,
        "direction": payment.direction,
        "payment_method": payment.payment_method,
        "amount_tmt": _decimal(payment.amount_tmt, "0.01"),
        "currency_id": payment.currency_id,
        "amount_cur": _decimal(payment.amount_cur, "0.01") if payment.amount_cur is not None else None,
        "currency_rate": _decimal(payment.currency_rate, "0.000001") if payment.currency_rate is not None else None,
        "status": payment.status,
        "note": payment.note,
        "allocations": [
            {
                "id": allocation.id,
                "doc_type": allocation.doc_type,
                "doc_id": allocation.doc_id,
                "allocated_amount": _decimal(allocation.allocated_amount, "0.01"),
            }
            for allocation in payment.allocations
        ],
    }


def _invoice_query(session: Session):
    """Return a purchase invoice query with response relationships loaded."""

    return session.query(PurchaseInvoice).options(
        selectinload(PurchaseInvoice.counterparty),
        selectinload(PurchaseInvoice.warehouse),
        selectinload(PurchaseInvoice.currency),
        selectinload(PurchaseInvoice.lines).selectinload(PurchaseInvoiceLine.product),
        selectinload(PurchaseInvoice.lines).selectinload(PurchaseInvoiceLine.service),
        selectinload(PurchaseInvoice.lines).selectinload(PurchaseInvoiceLine.uom),
    )


def _refresh_invoice(session: Session, invoice_id: int) -> PurchaseInvoice:
    """Reload an invoice with response relationships."""

    invoice = _invoice_query(session).filter(PurchaseInvoice.id == invoice_id).one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", "Purchase invoice not found."))
    return invoice


def _ensure_active_currency(session: Session, currency_id: int) -> Currency:
    """Return an active currency."""

    currency = _get_or_404(session, Currency, currency_id, "Currency")
    if not currency.is_active:
        raise HTTPException(status_code=400, detail=error_detail("INACTIVE_CURRENCY", "Currency is inactive."))
    return currency


def _ensure_active_counterparty(session: Session, counterparty_id: int) -> Counterparty:
    """Return an active counterparty."""

    counterparty = _get_or_404(session, Counterparty, counterparty_id, "Counterparty")
    if not counterparty.is_active:
        raise HTTPException(status_code=400, detail=error_detail("INACTIVE_COUNTERPARTY", "Counterparty is inactive."))
    return counterparty


def _ensure_supplier(counterparty: Counterparty) -> None:
    """Require supplier role for purchase documents."""

    if counterparty.role_flags not in {1, 3} and counterparty.counterparty_type not in {"supplier", "both"}:
        raise HTTPException(status_code=400, detail=error_detail("NOT_SUPPLIER", "Counterparty is not marked as a supplier."))


def _ensure_active_warehouse(session: Session, warehouse_id: int) -> Warehouse:
    """Return an active warehouse."""

    warehouse = _get_or_404(session, Warehouse, warehouse_id, "Warehouse")
    if not warehouse.is_active:
        raise HTTPException(status_code=400, detail=error_detail("INACTIVE_WAREHOUSE", "Warehouse is inactive."))
    return warehouse


def _line_uom_id(session: Session, product: Product | None, product_uom_id: int | None, uom_id: int | None) -> int | None:
    """Resolve the stock UOM used for a product or service line."""

    if product_uom_id is not None:
        product_uom = _get_or_404(session, ProductUom, product_uom_id, "Product UOM")
        return product_uom.uom_id
    if uom_id is not None:
        _get_or_404(session, UnitOfMeasure, uom_id, "Unit of measure")
        return uom_id
    return product.base_uom_id if product is not None else None


def _create_invoice_line(session: Session, invoice: PurchaseInvoice, line_payload: Any) -> PurchaseInvoiceLine:
    """Create one invoice line and validate references."""

    line_qty = qty4(line_payload.quantity)
    line_price_cur = price(line_payload.price_cur)
    line_price_tmt = price(line_price_cur * invoice.currency_rate)
    amount_cur = money(line_qty * line_price_cur)
    amount_tmt = money(line_qty * line_price_tmt)
    product: Product | None = None

    if line_payload.product_id is not None:
        product = _get_or_404(session, Product, line_payload.product_id, "Product")
        if not product.is_active:
            raise HTTPException(status_code=400, detail=error_detail("INACTIVE_PRODUCT", "Product is inactive."))
    if line_payload.service_id is not None:
        service = _get_or_404(session, Service, line_payload.service_id, "Service")
        if not service.is_active:
            raise HTTPException(status_code=400, detail=error_detail("INACTIVE_SERVICE", "Service is inactive."))
        _get_or_404(session, ExpenseCategory, line_payload.expense_category_id, "Expense category")

    resolved_uom_id = _line_uom_id(session, product, line_payload.product_uom_id, line_payload.uom_id)
    return PurchaseInvoiceLine(
        product_id=line_payload.product_id,
        service_id=line_payload.service_id,
        expense_category_id=line_payload.expense_category_id,
        product_uom_id=line_payload.product_uom_id,
        uom_id=resolved_uom_id,
        quantity=line_qty,
        price_cur=line_price_cur,
        price_tmt=line_price_tmt,
        amount_cur=amount_cur,
        amount_tmt=amount_tmt,
    )


@router.get("/currencies")
def list_currencies(
    _: User = Depends(require_pricing_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List currencies through API v1."""

    rows = session.query(Currency).order_by(Currency.code).all()
    return success_response([_currency_payload(row) for row in rows])


@router.get("/counterparty-categories")
def list_counterparty_categories(
    _: User = Depends(require_counterparty_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List counterparty categories."""

    rows = session.query(CounterpartyCategory).order_by(CounterpartyCategory.name_ru).all()
    return success_response([_category_payload(row) for row in rows])


@router.post("/counterparty-categories", status_code=status.HTTP_201_CREATED)
def create_counterparty_category(
    payload: CounterpartyCategoryCreate,
    _: User = Depends(require_counterparty_category),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a counterparty category."""

    category = CounterpartyCategory(**payload.model_dump())
    session.add(category)
    session.commit()
    session.refresh(category)
    return success_response(_category_payload(category))


@router.get("/counterparties")
def list_counterparties(
    search: str | None = Query(default=None),
    include_debt: bool = Query(default=False),
    _: User = Depends(require_counterparty_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List counterparties."""

    query = session.query(Counterparty).options(selectinload(Counterparty.category), selectinload(Counterparty.price_list))
    if search:
        pattern = f"%{search}%"
        query = query.filter(or_(Counterparty.code.ilike(pattern), Counterparty.name.ilike(pattern), Counterparty.phone.ilike(pattern)))
    rows = query.order_by(Counterparty.name).limit(500).all()
    return success_response([_counterparty_payload(session, row, include_debt=include_debt) for row in rows])


@router.post("/counterparties", status_code=status.HTTP_201_CREATED)
def create_counterparty(
    payload: CounterpartyCreate,
    _: User = Depends(require_counterparty_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a counterparty."""

    if session.query(Counterparty).filter(Counterparty.code == payload.code).one_or_none() is not None:
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_CODE", "Counterparty code already exists."))
    if payload.category_id is not None:
        _get_or_404(session, CounterpartyCategory, payload.category_id, "Counterparty category")
    if payload.price_list_id is not None:
        _get_or_404(session, PriceList, payload.price_list_id, "Price list")
    row = Counterparty(**payload.model_dump())
    session.add(row)
    session.commit()
    return success_response(_counterparty_payload(session, row))


@router.patch("/counterparties/{counterparty_id}")
def update_counterparty(
    counterparty_id: int,
    payload: CounterpartyUpdate,
    _: User = Depends(require_counterparty_edit),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update a counterparty."""

    row = _get_or_404(session, Counterparty, counterparty_id, "Counterparty")
    updates = _updates(payload)
    if updates.get("category_id") is not None:
        _get_or_404(session, CounterpartyCategory, int(updates["category_id"]), "Counterparty category")
    if updates.get("price_list_id") is not None:
        _get_or_404(session, PriceList, int(updates["price_list_id"]), "Price list")
    for key, value in updates.items():
        setattr(row, key, value)
    session.commit()
    return success_response(_counterparty_payload(session, row))


@router.get("/counterparties/{counterparty_id}/debt-summary")
def get_counterparty_debt_summary(
    counterparty_id: int,
    _: User = Depends(require_debt_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return receivable/payable debt balances for one counterparty."""

    row = _get_or_404(session, Counterparty, counterparty_id, "Counterparty")
    return success_response(_counterparty_payload(session, row, include_debt=True)["debt"])


@router.get("/price-lists")
def list_price_lists(
    _: User = Depends(require_pricing_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List price lists."""

    rows = session.query(PriceList).options(selectinload(PriceList.currency)).order_by(PriceList.name_ru).all()
    return success_response([_price_list_payload(row) for row in rows])


@router.post("/price-lists", status_code=status.HTTP_201_CREATED)
def create_price_list(
    payload: PriceListCreate,
    _: User = Depends(require_pricing_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a price list."""

    _ensure_active_currency(session, payload.currency_id)
    if payload.is_default:
        session.query(PriceList).filter(PriceList.is_default.is_(True)).update({PriceList.is_default: False})
    row = PriceList(**payload.model_dump())
    session.add(row)
    session.commit()
    session.refresh(row)
    return success_response(_price_list_payload(row))


@router.post("/price-lists/{price_list_id}/items", status_code=status.HTTP_201_CREATED)
def add_price_list_item(
    price_list_id: int,
    payload: PriceListItemCreate,
    _: User = Depends(require_pricing_edit),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Add one versioned price-list item."""

    price_list = _get_or_404(session, PriceList, price_list_id, "Price list")
    if payload.product_id is not None:
        _get_or_404(session, Product, payload.product_id, "Product")
    if payload.service_id is not None:
        _get_or_404(session, Service, payload.service_id, "Service")
    if payload.product_uom_id is not None:
        _get_or_404(session, ProductUom, payload.product_uom_id, "Product UOM")
    if payload.uom_id is not None:
        _get_or_404(session, UnitOfMeasure, payload.uom_id, "Unit of measure")
    item = PriceListItem(price_list=price_list, **payload.model_dump())
    session.add(item)
    session.commit()
    return success_response(_price_item_payload(item))


@router.get("/prices/current")
def get_current_price(
    price_list_id: int | None = Query(default=None),
    counterparty_id: int | None = Query(default=None),
    product_id: int | None = Query(default=None),
    service_id: int | None = Query(default=None),
    on_date: date | None = Query(default=None),
    _: User = Depends(require_pricing_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return the current price for one product or service."""

    if (product_id is None) == (service_id is None):
        raise HTTPException(status_code=400, detail=error_detail("INVALID_TARGET", "Exactly one of product_id or service_id is required."))
    if price_list_id is None and counterparty_id is not None:
        counterparty = _get_or_404(session, Counterparty, counterparty_id, "Counterparty")
        price_list_id = counterparty.price_list_id
    if price_list_id is None:
        default_list = session.query(PriceList).filter(PriceList.is_default.is_(True), PriceList.is_active.is_(True)).one_or_none()
        if default_list is not None:
            price_list_id = default_list.id
    if price_list_id is None:
        raise HTTPException(status_code=404, detail=error_detail("PRICE_LIST_NOT_FOUND", "No price list selected and no default price list exists."))
    effective_date = on_date or date.today()
    query = (
        session.query(PriceListItem)
        .options(selectinload(PriceListItem.product), selectinload(PriceListItem.service), selectinload(PriceListItem.uom))
        .filter(
            PriceListItem.price_list_id == price_list_id,
            PriceListItem.valid_from <= effective_date,
            or_(PriceListItem.valid_to.is_(None), PriceListItem.valid_to >= effective_date),
        )
    )
    query = query.filter(PriceListItem.product_id == product_id) if product_id is not None else query.filter(PriceListItem.service_id == service_id)
    item = query.order_by(PriceListItem.valid_from.desc(), PriceListItem.id.desc()).first()
    if item is None:
        raise HTTPException(status_code=404, detail=error_detail("PRICE_NOT_FOUND", "No active price was found."))
    return success_response(_price_item_payload(item))


@router.get("/purchase-invoices")
def list_purchase_invoices(
    _: User = Depends(require_purchase_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List recent purchase invoices."""

    rows = _invoice_query(session).order_by(PurchaseInvoice.id.desc()).limit(200).all()
    return success_response([_invoice_payload(row) for row in rows])


@router.post("/purchase-invoices", status_code=status.HTTP_201_CREATED)
def create_purchase_invoice(
    payload: PurchaseInvoiceCreate,
    current_user: User = Depends(require_purchase_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a draft purchase invoice."""

    counterparty = _ensure_active_counterparty(session, payload.counterparty_id)
    _ensure_supplier(counterparty)
    _ensure_active_warehouse(session, payload.warehouse_id)
    _ensure_active_currency(session, payload.currency_id)
    if payload.return_invoice_id is not None:
        _get_or_404(session, PurchaseInvoice, payload.return_invoice_id, "Return source invoice")
    doc_number = payload.doc_number or generate_doc_number(session, PurchaseInvoice, "PIN")
    if session.query(PurchaseInvoice).filter(PurchaseInvoice.doc_number == doc_number).one_or_none() is not None:
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_DOC_NUMBER", "Purchase invoice number already exists."))
    invoice = PurchaseInvoice(
        doc_number=doc_number,
        doc_date=payload.doc_date or date.today(),
        purchase_order_id=payload.purchase_order_id,
        counterparty_id=payload.counterparty_id,
        warehouse_id=payload.warehouse_id,
        currency_id=payload.currency_id,
        currency_rate=payload.currency_rate,
        expiry_note=payload.expiry_note,
        is_return=payload.is_return,
        return_invoice_id=payload.return_invoice_id,
        note=payload.note,
        created_by_user_id=current_user.id,
    )
    session.add(invoice)
    session.flush()
    for line_payload in payload.lines:
        invoice.lines.append(_create_invoice_line(session, invoice, line_payload))
    invoice.total_amount_cur = money(sum((line.amount_cur for line in invoice.lines), Decimal("0")))
    invoice.total_amount_tmt = money(sum((line.amount_tmt for line in invoice.lines), Decimal("0")))
    if invoice.is_return:
        invoice.total_amount_cur = -invoice.total_amount_cur
        invoice.total_amount_tmt = -invoice.total_amount_tmt
    session.commit()
    return success_response(_invoice_payload(_refresh_invoice(session, invoice.id)))


@router.get("/purchase-invoices/{invoice_id}")
def get_purchase_invoice(
    invoice_id: int,
    _: User = Depends(require_purchase_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one purchase invoice."""

    return success_response(_invoice_payload(_refresh_invoice(session, invoice_id)))


@router.post("/purchase-invoices/{invoice_id}/post")
def post_purchase_invoice(
    invoice_id: int,
    current_user: User = Depends(require_purchase_post),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Post a purchase invoice to stock and payable debt."""

    invoice = _refresh_invoice(session, invoice_id)
    if invoice.status != "draft":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only draft purchase invoices can be posted."))
    try:
        for line in invoice.lines:
            if line.product_id is None:
                continue
            balance = get_or_create_balance(session, invoice.warehouse_id, line.product_id, line.uom_id)
            line.avg_cost_before = price(balance.avg_cost_tmt)
            movement = post_stock_movement(
                session,
                warehouse_id=invoice.warehouse_id,
                product_id=line.product_id,
                uom_id=line.uom_id,
                movement_type="purchase",
                document_type="purchase_invoice",
                document_id=invoice.id,
                quantity_delta=(-line.quantity if invoice.is_return else line.quantity),
                unit_cost_tmt=line.price_tmt,
                user_id=current_user.id,
            )
            balance_after = get_or_create_balance(session, invoice.warehouse_id, line.product_id, line.uom_id)
            line.avg_cost_after = price(balance_after.avg_cost_tmt if movement else line.avg_cost_before)
    except WarehouseBusinessError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=error_detail(exc.code, str(exc), exc.details)) from exc

    invoice.status = "posted"
    invoice.posted_by_user_id = current_user.id
    invoice.posted_at = now_utc()
    post_debt_entry(
        session,
        counterparty_id=invoice.counterparty_id,
        debt_type="payable",
        doc_type="purchase_invoice",
        doc_id=invoice.id,
        doc_number=invoice.doc_number,
        doc_date=_doc_datetime(invoice.doc_date),
        amount_tmt=invoice.total_amount_tmt,
        currency_id=invoice.currency_id,
        amount_cur=invoice.total_amount_cur,
        note="Purchase invoice posted",
        user_id=current_user.id,
    )
    session.commit()
    return success_response(_invoice_payload(_refresh_invoice(session, invoice.id)))


@router.post("/purchase-invoices/{invoice_id}/cancel")
def cancel_purchase_invoice(
    invoice_id: int,
    current_user: User = Depends(require_purchase_cancel),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cancel a posted purchase invoice with reversing entries."""

    invoice = _refresh_invoice(session, invoice_id)
    if invoice.status != "posted":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only posted purchase invoices can be cancelled."))
    try:
        for line in invoice.lines:
            if line.product_id is None:
                continue
            post_stock_movement(
                session,
                warehouse_id=invoice.warehouse_id,
                product_id=line.product_id,
                uom_id=line.uom_id,
                movement_type="purchase_cancel",
                document_type="purchase_invoice",
                document_id=invoice.id,
                quantity_delta=(line.quantity if invoice.is_return else -line.quantity),
                unit_cost_tmt=line.price_tmt,
                user_id=current_user.id,
            )
    except WarehouseBusinessError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=error_detail(exc.code, str(exc), exc.details)) from exc

    invoice.status = "cancelled"
    post_debt_entry(
        session,
        counterparty_id=invoice.counterparty_id,
        debt_type="payable",
        doc_type="purchase_invoice",
        doc_id=invoice.id,
        doc_number=invoice.doc_number,
        doc_date=now_utc(),
        amount_tmt=-invoice.total_amount_tmt,
        currency_id=invoice.currency_id,
        amount_cur=-invoice.total_amount_cur,
        note="Purchase invoice cancelled",
        user_id=current_user.id,
    )
    session.commit()
    return success_response(_invoice_payload(_refresh_invoice(session, invoice.id)))


@router.get("/debt-ledger")
def list_debt_ledger(
    counterparty_id: int | None = Query(default=None),
    debt_type: str | None = Query(default=None),
    _: User = Depends(require_debt_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List recent debt ledger entries."""

    query = session.query(DebtLedger).options(selectinload(DebtLedger.counterparty))
    if counterparty_id is not None:
        query = query.filter(DebtLedger.counterparty_id == counterparty_id)
    if debt_type is not None:
        query = query.filter(DebtLedger.debt_type == debt_type)
    rows = query.order_by(DebtLedger.id.desc()).limit(500).all()
    return success_response([_debt_payload(row) for row in rows])


@router.post("/payments", status_code=status.HTTP_201_CREATED)
def create_payment(
    payload: PaymentCreate,
    current_user: User = Depends(require_payment_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create and post a payment document."""

    _ensure_active_counterparty(session, payload.counterparty_id)
    if payload.currency_id is not None:
        _ensure_active_currency(session, payload.currency_id)
    allocation_total = money(sum((allocation.allocated_amount for allocation in payload.allocations), Decimal("0")))
    if allocation_total > money(payload.amount_tmt):
        raise HTTPException(status_code=400, detail=error_detail("ALLOCATION_EXCEEDS_PAYMENT", "Allocations cannot exceed payment amount."))
    doc_number = payload.doc_number or generate_doc_number(session, Payment, "PAY")
    if session.query(Payment).filter(Payment.doc_number == doc_number).one_or_none() is not None:
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_DOC_NUMBER", "Payment number already exists."))
    payment = Payment(
        doc_number=doc_number,
        doc_date=payload.doc_date or now_utc(),
        counterparty_id=payload.counterparty_id,
        direction=payload.direction,
        payment_method=payload.payment_method,
        amount_tmt=money(payload.amount_tmt),
        currency_id=payload.currency_id,
        amount_cur=money(payload.amount_cur) if payload.amount_cur is not None else None,
        currency_rate=payload.currency_rate,
        note=payload.note,
        created_by_user_id=current_user.id,
    )
    session.add(payment)
    session.flush()
    for allocation in payload.allocations:
        if allocation.doc_type != "purchase_invoice":
            raise HTTPException(status_code=400, detail=error_detail("UNSUPPORTED_ALLOCATION", "Only purchase_invoice allocations are supported in this layer."))
        invoice = _get_or_404(session, PurchaseInvoice, allocation.doc_id, "Purchase invoice")
        if invoice.counterparty_id != payment.counterparty_id:
            raise HTTPException(status_code=400, detail=error_detail("ALLOCATION_COUNTERPARTY_MISMATCH", "Allocation document belongs to another counterparty."))
        payment.allocations.append(
            PaymentAllocation(
                doc_type=allocation.doc_type,
                doc_id=allocation.doc_id,
                allocated_amount=money(allocation.allocated_amount),
            )
        )
        update_purchase_invoice_payment_status(session, invoice)

    debt_type = "payable" if payment.direction == "outgoing" else "receivable"
    post_debt_entry(
        session,
        counterparty_id=payment.counterparty_id,
        debt_type=debt_type,
        doc_type="payment",
        doc_id=payment.id,
        doc_number=payment.doc_number,
        doc_date=payment.doc_date,
        amount_tmt=-payment.amount_tmt,
        currency_id=payment.currency_id,
        amount_cur=payment.amount_cur,
        note="Payment posted",
        user_id=current_user.id,
    )
    session.commit()
    for allocation in payment.allocations:
        if allocation.doc_type == "purchase_invoice":
            invoice = session.get(PurchaseInvoice, allocation.doc_id)
            if invoice is not None:
                update_purchase_invoice_payment_status(session, invoice)
    session.commit()
    refreshed = (
        session.query(Payment)
        .options(selectinload(Payment.counterparty), selectinload(Payment.allocations))
        .filter(Payment.id == payment.id)
        .one()
    )
    return success_response(_payment_payload(refreshed))


@router.post("/payments/{payment_id}/cancel")
def cancel_payment(
    payment_id: int,
    current_user: User = Depends(require_payment_cancel),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cancel a posted payment and reverse its debt effect."""

    payment = (
        session.query(Payment)
        .options(selectinload(Payment.counterparty), selectinload(Payment.allocations))
        .filter(Payment.id == payment_id)
        .one_or_none()
    )
    if payment is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", "Payment not found."))
    if payment.status != "posted":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only posted payments can be cancelled."))
    payment.status = "cancelled"
    payment.cancelled_by_user_id = current_user.id
    payment.cancelled_at = now_utc()
    debt_type = "payable" if payment.direction == "outgoing" else "receivable"
    post_debt_entry(
        session,
        counterparty_id=payment.counterparty_id,
        debt_type=debt_type,
        doc_type="payment",
        doc_id=payment.id,
        doc_number=payment.doc_number,
        doc_date=now_utc(),
        amount_tmt=payment.amount_tmt,
        currency_id=payment.currency_id,
        amount_cur=payment.amount_cur,
        note="Payment cancelled",
        user_id=current_user.id,
    )
    for allocation in payment.allocations:
        if allocation.doc_type == "purchase_invoice":
            invoice = session.get(PurchaseInvoice, allocation.doc_id)
            if invoice is not None:
                update_purchase_invoice_payment_status(session, invoice)
    session.commit()
    return success_response(_payment_payload(payment))
