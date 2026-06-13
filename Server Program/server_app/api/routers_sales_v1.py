"""API v1 routes for sales, cashier shifts, and first report summaries."""

from __future__ import annotations

from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from server_app.api.dependencies import get_db
from server_app.api.routers_v1 import error_detail, require_v1_permission, success_response
from server_app.db.models import (
    CashOperation,
    CashRegister,
    CashShift,
    Counterparty,
    Currency,
    DebtLedger,
    Payment,
    Product,
    ProductUom,
    PurchaseInvoice,
    Sale,
    SaleLine,
    Service,
    StockBalance,
    Warehouse,
    User,
)
from server_app.schemas.sales_v1 import (
    CashOperationCreate,
    CashRegisterCreate,
    CashShiftClose,
    CashShiftOpen,
    SaleCreate,
    SaleLineCreate,
)
from server_app.services.settlements import (
    current_debt_balance,
    generate_doc_number,
    money,
    now_utc,
    post_debt_entry,
    price,
    qty4,
)
from server_app.services.warehouse import WarehouseBusinessError, get_or_create_balance, post_stock_movement


router = APIRouter(prefix="/api/v1", tags=["sales-cashier-reports"])

require_cashier_view = require_v1_permission("cashier.view")
require_register_manage = require_v1_permission("cashier.register_manage")
require_shift_open = require_v1_permission("cashier.shift_open")
require_shift_close = require_v1_permission("cashier.shift_close")
require_cash_operation = require_v1_permission("cashier.cash_operation")
require_sale_view = require_v1_permission("sale.view")
require_sale_create = require_v1_permission("sale.create")
require_sale_post = require_v1_permission("sale.post")
require_sale_cancel = require_v1_permission("sale.cancel")
require_reports_view = require_v1_permission("reports.view")


def _decimal(value: Decimal | int | str | None, places: str) -> str:
    """Return a decimal value as a normalized string."""

    if value is None:
        value = Decimal("0")
    return str(Decimal(value).quantize(Decimal(places)))


def _get_or_404(session: Session, model: type[Any], object_id: int, name: str) -> Any:
    """Load one row by primary key or raise a v1 error."""

    row = session.get(model, object_id)
    if row is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", f"{name} not found."))
    return row


def _ensure_customer(counterparty: Counterparty | None, required: bool = True) -> None:
    """Ensure a counterparty is usable as a customer when supplied."""

    if counterparty is None:
        if required:
            raise HTTPException(status_code=400, detail=error_detail("COUNTERPARTY_REQUIRED", "Counterparty is required."))
        return
    if not counterparty.is_active or counterparty.role_flags not in (2, 3):
        raise HTTPException(status_code=400, detail=error_detail("INVALID_COUNTERPARTY_ROLE", "Counterparty must be an active customer."))


def _cash_register_payload(row: CashRegister) -> dict[str, Any]:
    """Return a cash-register payload."""

    return {
        "id": row.id,
        "name": row.name,
        "warehouse_id": row.warehouse_id,
        "warehouse_name": row.warehouse.name if row.warehouse else None,
        "is_active": row.is_active,
    }


def _cash_shift_payload(row: CashShift) -> dict[str, Any]:
    """Return a cash-shift payload."""

    sales_cash = sum((money(sale.paid_cash_tmt) for sale in row.sales if sale.status == "posted"), Decimal("0.00"))
    sales_transfer = sum((money(sale.paid_transfer_tmt) for sale in row.sales if sale.status == "posted"), Decimal("0.00"))
    return {
        "id": row.id,
        "cash_register_id": row.cash_register_id,
        "cash_register_name": row.cash_register.name if row.cash_register else None,
        "opened_by_user_id": row.opened_by_user_id,
        "closed_by_user_id": row.closed_by_user_id,
        "opened_at": row.opened_at.isoformat() if row.opened_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "opening_amount": _decimal(row.opening_amount, "0.01"),
        "closing_amount": _decimal(row.closing_amount, "0.01") if row.closing_amount is not None else None,
        "status": row.status,
        "posted_sales_cash_tmt": _decimal(sales_cash, "0.01"),
        "posted_sales_transfer_tmt": _decimal(sales_transfer, "0.01"),
    }


def _cash_operation_payload(row: CashOperation) -> dict[str, Any]:
    """Return a cash-operation payload."""

    return {
        "id": row.id,
        "doc_number": row.doc_number,
        "doc_date": row.doc_date.isoformat() if row.doc_date else None,
        "cash_shift_id": row.cash_shift_id,
        "cash_register_from_id": row.cash_register_from_id,
        "cash_register_from_name": row.cash_register_from.name if row.cash_register_from else None,
        "cash_register_to_id": row.cash_register_to_id,
        "cash_register_to_name": row.cash_register_to.name if row.cash_register_to else None,
        "operation_type": row.operation_type,
        "amount_tmt": _decimal(row.amount_tmt, "0.01"),
        "note": row.note,
    }


def _sale_line_payload(line: SaleLine) -> dict[str, Any]:
    """Return a sale-line payload."""

    return {
        "id": line.id,
        "line_type": line.line_type,
        "product_id": line.product_id,
        "product_sku": line.product.sku if line.product else None,
        "product_name": line.product.name if line.product else None,
        "service_id": line.service_id,
        "service_code": line.service.code if line.service else None,
        "service_name_ru": line.service.name_ru if line.service else None,
        "product_uom_id": line.product_uom_id,
        "uom_id": line.uom_id,
        "uom_code": line.uom.code if line.uom else None,
        "quantity": _decimal(line.quantity, "0.0001"),
        "price_list_price": _decimal(line.price_list_price, "0.0001"),
        "price_final": _decimal(line.price_final, "0.0001"),
        "discount_percent": _decimal(line.discount_percent, "0.01"),
        "discount_amount": _decimal(line.discount_amount, "0.01"),
        "amount_tmt": _decimal(line.amount_tmt, "0.01"),
        "avg_cost_tmt": _decimal(line.avg_cost_tmt, "0.0001"),
        "price_override": line.price_override,
    }


def _sale_payload(row: Sale) -> dict[str, Any]:
    """Return a sale payload."""

    return {
        "id": row.id,
        "doc_number": row.doc_number,
        "doc_date": row.doc_date.isoformat() if row.doc_date else None,
        "sale_type": row.sale_type,
        "cash_register_id": row.cash_register_id,
        "cash_register_name": row.cash_register.name if row.cash_register else None,
        "cash_shift_id": row.cash_shift_id,
        "counterparty_id": row.counterparty_id,
        "counterparty_name": row.counterparty.name if row.counterparty else None,
        "warehouse_id": row.warehouse_id,
        "warehouse_name": row.warehouse.name if row.warehouse else None,
        "price_list_id": row.price_list_id,
        "currency_id": row.currency_id,
        "currency_code": row.currency.code if row.currency else None,
        "currency_rate": _decimal(row.currency_rate, "0.000001"),
        "discount_percent": _decimal(row.discount_percent, "0.01"),
        "discount_amount_tmt": _decimal(row.discount_amount_tmt, "0.01"),
        "total_amount_tmt": _decimal(row.total_amount_tmt, "0.01"),
        "payment_type": row.payment_type,
        "paid_cash_tmt": _decimal(row.paid_cash_tmt, "0.01"),
        "paid_transfer_tmt": _decimal(row.paid_transfer_tmt, "0.01"),
        "paid_bonus_tmt": _decimal(row.paid_bonus_tmt, "0.01"),
        "debt_amount_tmt": _decimal(row.debt_amount_tmt, "0.01"),
        "status": row.status,
        "posted_at": row.posted_at.isoformat() if row.posted_at else None,
        "lines": [_sale_line_payload(line) for line in row.lines],
    }


def _sale_query(session: Session):
    """Return a sale query with relationships used by payloads."""

    return session.query(Sale).options(
        selectinload(Sale.cash_register),
        selectinload(Sale.cash_shift),
        selectinload(Sale.counterparty),
        selectinload(Sale.warehouse),
        selectinload(Sale.currency),
        selectinload(Sale.lines).selectinload(SaleLine.product),
        selectinload(Sale.lines).selectinload(SaleLine.service),
        selectinload(Sale.lines).selectinload(SaleLine.uom),
    )


def _refresh_sale(session: Session, sale_id: int) -> Sale:
    """Reload one sale with payload relationships."""

    sale = _sale_query(session).filter(Sale.id == sale_id).one_or_none()
    if sale is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", "Sale not found."))
    return sale


def _validate_shift_for_register(session: Session, shift_id: int | None, register_id: int | None) -> CashShift | None:
    """Validate that a shift is open and belongs to the selected register."""

    if shift_id is None:
        return None
    shift = _get_or_404(session, CashShift, shift_id, "Cash shift")
    if shift.status != "open":
        raise HTTPException(status_code=400, detail=error_detail("SHIFT_CLOSED", "Cash shift is not open."))
    if register_id is not None and shift.cash_register_id != register_id:
        raise HTTPException(status_code=400, detail=error_detail("SHIFT_REGISTER_MISMATCH", "Shift belongs to another cash register."))
    return shift


def _build_sale_line(session: Session, payload: SaleLineCreate) -> SaleLine:
    """Create a sale line and validate target objects."""

    quantity = qty4(payload.quantity)
    final_price = price(payload.price_final)
    list_price = price(payload.price_list_price if payload.price_list_price is not None else payload.price_final)
    amount = money(quantity * final_price)
    if payload.product_id is not None:
        _get_or_404(session, Product, payload.product_id, "Product")
        if payload.product_uom_id is not None:
            _get_or_404(session, ProductUom, payload.product_uom_id, "Product UOM")
        line_type = payload.line_type or "product"
    else:
        _get_or_404(session, Service, payload.service_id, "Service")
        line_type = payload.line_type or "service"
    return SaleLine(
        line_type=line_type,
        product_id=payload.product_id,
        service_id=payload.service_id,
        product_uom_id=payload.product_uom_id,
        uom_id=payload.uom_id,
        quantity=quantity,
        price_list_price=list_price,
        price_final=final_price,
        discount_percent=payload.discount_percent,
        discount_amount=money(payload.discount_amount),
        amount_tmt=amount,
        avg_cost_tmt=Decimal("0.0000"),
        price_override=payload.price_override,
    )


def _payment_split(payload: SaleCreate, total: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Return normalized cash, transfer, bonus, and debt amounts."""

    zero = Decimal("0.00")
    if payload.payment_type == "cash":
        supplied = money(payload.paid_cash_tmt)
        if supplied not in (zero, total):
            raise HTTPException(status_code=400, detail=error_detail("PAYMENT_TOTAL_MISMATCH", "Cash payment must equal sale total."))
        return total, zero, zero, zero
    if payload.payment_type == "transfer":
        supplied = money(payload.paid_transfer_tmt)
        if supplied not in (zero, total):
            raise HTTPException(status_code=400, detail=error_detail("PAYMENT_TOTAL_MISMATCH", "Transfer payment must equal sale total."))
        return zero, total, zero, zero
    if payload.payment_type == "bonus":
        supplied = money(payload.paid_bonus_tmt)
        if supplied not in (zero, total):
            raise HTTPException(status_code=400, detail=error_detail("PAYMENT_TOTAL_MISMATCH", "Bonus payment must equal sale total."))
        return zero, zero, total, zero
    if payload.payment_type == "debt":
        return zero, zero, zero, total

    cash = money(payload.paid_cash_tmt)
    transfer = money(payload.paid_transfer_tmt)
    bonus = money(payload.paid_bonus_tmt)
    debt = money(payload.debt_amount_tmt)
    if money(cash + transfer + bonus + debt) != total:
        raise HTTPException(status_code=400, detail=error_detail("PAYMENT_TOTAL_MISMATCH", "Mixed payment parts must equal sale total."))
    return cash, transfer, bonus, debt


@router.get("/cash-registers")
def list_cash_registers(
    _: User = Depends(require_cashier_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List cash registers."""

    rows = session.query(CashRegister).options(selectinload(CashRegister.warehouse)).order_by(CashRegister.id).all()
    return success_response([_cash_register_payload(row) for row in rows])


@router.post("/cash-registers", status_code=status.HTTP_201_CREATED)
def create_cash_register(
    payload: CashRegisterCreate,
    _: User = Depends(require_register_manage),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a cash register bound to a warehouse."""

    warehouse = _get_or_404(session, Warehouse, payload.warehouse_id, "Warehouse")
    register = CashRegister(name=payload.name, warehouse_id=warehouse.id, is_active=payload.is_active)
    session.add(register)
    session.commit()
    session.refresh(register)
    return success_response(_cash_register_payload(register))


@router.get("/cash-shifts")
def list_cash_shifts(
    status_filter: str | None = Query(default=None, alias="status"),
    _: User = Depends(require_cashier_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List recent cash shifts."""

    query = session.query(CashShift).options(selectinload(CashShift.cash_register), selectinload(CashShift.sales))
    if status_filter is not None:
        query = query.filter(CashShift.status == status_filter)
    rows = query.order_by(CashShift.id.desc()).limit(200).all()
    return success_response([_cash_shift_payload(row) for row in rows])


@router.post("/cash-shifts/open", status_code=status.HTTP_201_CREATED)
def open_cash_shift(
    payload: CashShiftOpen,
    current_user: User = Depends(require_shift_open),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Open one cash shift for a register."""

    register = _get_or_404(session, CashRegister, payload.cash_register_id, "Cash register")
    if not register.is_active:
        raise HTTPException(status_code=400, detail=error_detail("INACTIVE_REGISTER", "Cash register is inactive."))
    existing = (
        session.query(CashShift)
        .filter(CashShift.cash_register_id == register.id, CashShift.status == "open")
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail=error_detail("SHIFT_ALREADY_OPEN", "Cash register already has an open shift."))
    shift = CashShift(
        cash_register_id=register.id,
        opened_by_user_id=current_user.id,
        opening_amount=money(payload.opening_amount),
        status="open",
    )
    session.add(shift)
    session.commit()
    return success_response(_cash_shift_payload(shift))


@router.post("/cash-shifts/{shift_id}/close")
def close_cash_shift(
    shift_id: int,
    payload: CashShiftClose,
    current_user: User = Depends(require_shift_close),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Close an open cash shift."""

    shift = _get_or_404(session, CashShift, shift_id, "Cash shift")
    if shift.status != "open":
        raise HTTPException(status_code=400, detail=error_detail("SHIFT_CLOSED", "Cash shift is already closed."))
    shift.status = "closed"
    shift.closed_by_user_id = current_user.id
    shift.closed_at = now_utc()
    shift.closing_amount = money(payload.closing_amount)
    session.commit()
    return success_response(_cash_shift_payload(shift))


@router.post("/cash-operations", status_code=status.HTTP_201_CREATED)
def create_cash_operation(
    payload: CashOperationCreate,
    current_user: User = Depends(require_cash_operation),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a cash collection or register transfer operation."""

    shift = _validate_shift_for_register(session, payload.cash_shift_id, payload.cash_register_from_id)
    _get_or_404(session, CashRegister, payload.cash_register_from_id, "Source cash register")
    if payload.cash_register_to_id is not None:
        _get_or_404(session, CashRegister, payload.cash_register_to_id, "Target cash register")
    doc_number = payload.doc_number or generate_doc_number(session, CashOperation, "COP")
    if session.query(CashOperation).filter(CashOperation.doc_number == doc_number).one_or_none() is not None:
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_DOC_NUMBER", "Cash operation number already exists."))
    operation = CashOperation(
        doc_number=doc_number,
        doc_date=payload.doc_date or now_utc(),
        cash_shift_id=shift.id if shift else payload.cash_shift_id,
        cash_register_from_id=payload.cash_register_from_id,
        cash_register_to_id=payload.cash_register_to_id,
        operation_type=payload.operation_type,
        amount_tmt=money(payload.amount_tmt),
        note=payload.note,
        created_by_user_id=current_user.id,
    )
    session.add(operation)
    session.commit()
    refreshed = (
        session.query(CashOperation)
        .options(selectinload(CashOperation.cash_register_from), selectinload(CashOperation.cash_register_to))
        .filter(CashOperation.id == operation.id)
        .one()
    )
    return success_response(_cash_operation_payload(refreshed))


@router.get("/sales")
def list_sales(
    status_filter: str | None = Query(default=None, alias="status"),
    _: User = Depends(require_sale_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List recent sales."""

    query = _sale_query(session)
    if status_filter is not None:
        query = query.filter(Sale.status == status_filter)
    rows = query.order_by(Sale.id.desc()).limit(200).all()
    return success_response([_sale_payload(row) for row in rows])


@router.get("/sales/{sale_id}")
def get_sale(
    sale_id: int,
    _: User = Depends(require_sale_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one sale document."""

    return success_response(_sale_payload(_refresh_sale(session, sale_id)))


@router.post("/sales", status_code=status.HTTP_201_CREATED)
def create_sale(
    payload: SaleCreate,
    current_user: User = Depends(require_sale_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a draft sale document."""

    _get_or_404(session, Warehouse, payload.warehouse_id, "Warehouse")
    _get_or_404(session, Currency, payload.currency_id, "Currency")
    if payload.cash_register_id is not None:
        register = _get_or_404(session, CashRegister, payload.cash_register_id, "Cash register")
        if register.warehouse_id != payload.warehouse_id:
            raise HTTPException(status_code=400, detail=error_detail("REGISTER_WAREHOUSE_MISMATCH", "Cash register belongs to another warehouse."))
    _validate_shift_for_register(session, payload.cash_shift_id, payload.cash_register_id)
    counterparty = session.get(Counterparty, payload.counterparty_id) if payload.counterparty_id is not None else None
    if payload.counterparty_id is not None and counterparty is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", "Counterparty not found."))
    _ensure_customer(
        counterparty,
        required=payload.sale_type == "wholesale" or payload.payment_type == "debt" or money(payload.debt_amount_tmt) > Decimal("0.00"),
    )

    doc_number = payload.doc_number or generate_doc_number(session, Sale, "SAL")
    if session.query(Sale).filter(Sale.doc_number == doc_number).one_or_none() is not None:
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_DOC_NUMBER", "Sale number already exists."))

    lines = [_build_sale_line(session, item) for item in payload.lines]
    subtotal = money(sum((line.amount_tmt for line in lines), Decimal("0")))
    doc_discount = money((subtotal * money(payload.discount_percent) / Decimal("100")) + payload.discount_amount_tmt)
    if doc_discount > subtotal:
        raise HTTPException(status_code=400, detail=error_detail("DISCOUNT_EXCEEDS_TOTAL", "Document discount exceeds sale subtotal."))
    total = money(subtotal - doc_discount)
    paid_cash, paid_transfer, paid_bonus, debt = _payment_split(payload, total)
    if debt > Decimal("0.00") and counterparty is None:
        raise HTTPException(status_code=400, detail=error_detail("COUNTERPARTY_REQUIRED", "Counterparty is required for debt amount."))

    sale = Sale(
        doc_number=doc_number,
        doc_date=payload.doc_date or now_utc(),
        sale_type=payload.sale_type,
        cash_register_id=payload.cash_register_id,
        cash_shift_id=payload.cash_shift_id,
        counterparty_id=payload.counterparty_id,
        warehouse_id=payload.warehouse_id,
        price_list_id=payload.price_list_id,
        currency_id=payload.currency_id,
        currency_rate=payload.currency_rate,
        discount_percent=payload.discount_percent,
        discount_amount_tmt=doc_discount,
        total_amount_tmt=total,
        payment_type=payload.payment_type,
        paid_cash_tmt=paid_cash,
        paid_transfer_tmt=paid_transfer,
        paid_bonus_tmt=paid_bonus,
        debt_amount_tmt=debt,
        loyalty_card_id=payload.loyalty_card_id,
        status="draft",
        created_by_user_id=current_user.id,
    )
    sale.lines.extend(lines)
    session.add(sale)
    session.commit()
    return success_response(_sale_payload(_refresh_sale(session, sale.id)))


@router.post("/sales/{sale_id}/post")
def post_sale(
    sale_id: int,
    current_user: User = Depends(require_sale_post),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Post a draft sale into stock and debt ledgers."""

    sale = _refresh_sale(session, sale_id)
    if sale.status != "draft":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only draft sales can be posted."))
    if sale.cash_shift_id is not None:
        _validate_shift_for_register(session, sale.cash_shift_id, sale.cash_register_id)
    try:
        for line in sale.lines:
            if line.product_id is None:
                continue
            balance = get_or_create_balance(session, sale.warehouse_id, line.product_id, line.uom_id)
            movement = post_stock_movement(
                session,
                warehouse_id=sale.warehouse_id,
                product_id=line.product_id,
                uom_id=line.uom_id,
                movement_type="sale",
                document_type="sale",
                document_id=sale.id,
                quantity_delta=-line.quantity,
                unit_cost_tmt=balance.avg_cost_tmt,
                user_id=current_user.id,
            )
            line.avg_cost_tmt = movement.unit_cost_tmt
    except WarehouseBusinessError as exc:
        raise HTTPException(status_code=400, detail=error_detail(exc.code, str(exc), exc.details)) from exc

    if money(sale.debt_amount_tmt) > Decimal("0.00"):
        if sale.counterparty_id is None:
            raise HTTPException(status_code=400, detail=error_detail("COUNTERPARTY_REQUIRED", "Counterparty is required for debt sales."))
        post_debt_entry(
            session,
            counterparty_id=sale.counterparty_id,
            debt_type="receivable",
            doc_type="sale",
            doc_id=sale.id,
            doc_number=sale.doc_number,
            doc_date=sale.doc_date,
            amount_tmt=money(sale.debt_amount_tmt),
            currency_id=sale.currency_id,
            amount_cur=money(sale.debt_amount_tmt),
            note="Sale posted",
            user_id=current_user.id,
        )
    sale.status = "posted"
    sale.posted_by_user_id = current_user.id
    sale.posted_at = now_utc()
    session.commit()
    return success_response(_sale_payload(_refresh_sale(session, sale.id)))


@router.post("/sales/{sale_id}/cancel")
def cancel_sale(
    sale_id: int,
    current_user: User = Depends(require_sale_cancel),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cancel a sale and reverse posted side effects."""

    sale = _refresh_sale(session, sale_id)
    if sale.status == "cancelled":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Sale is already cancelled."))
    if sale.status == "posted":
        try:
            for line in sale.lines:
                if line.product_id is None:
                    continue
                post_stock_movement(
                    session,
                    warehouse_id=sale.warehouse_id,
                    product_id=line.product_id,
                    uom_id=line.uom_id,
                    movement_type="sale_cancel",
                    document_type="sale",
                    document_id=sale.id,
                    quantity_delta=line.quantity,
                    unit_cost_tmt=line.avg_cost_tmt,
                    user_id=current_user.id,
                )
        except WarehouseBusinessError as exc:
            raise HTTPException(status_code=400, detail=error_detail(exc.code, str(exc), exc.details)) from exc
        if money(sale.debt_amount_tmt) > Decimal("0.00") and sale.counterparty_id is not None:
            post_debt_entry(
                session,
                counterparty_id=sale.counterparty_id,
                debt_type="receivable",
                doc_type="sale",
                doc_id=sale.id,
                doc_number=sale.doc_number,
                doc_date=now_utc(),
                amount_tmt=-money(sale.debt_amount_tmt),
                currency_id=sale.currency_id,
                amount_cur=-money(sale.debt_amount_tmt),
                note="Sale cancelled",
                user_id=current_user.id,
            )
    sale.status = "cancelled"
    sale.cancelled_by_user_id = current_user.id
    sale.cancelled_at = now_utc()
    session.commit()
    return success_response(_sale_payload(_refresh_sale(session, sale.id)))


def _date_range_filter(query, column, date_from: datetime | None, date_to: datetime | None):
    """Apply optional inclusive datetime filters."""

    if date_from is not None:
        query = query.filter(column >= date_from)
    if date_to is not None:
        query = query.filter(column <= date_to)
    return query


@router.get("/reports/dashboard")
def dashboard_report(
    _: User = Depends(require_reports_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return dashboard totals for the main screen."""

    receivable = session.query(func.coalesce(func.sum(DebtLedger.amount_tmt), 0)).filter(DebtLedger.debt_type == "receivable").scalar() or 0
    payable = session.query(func.coalesce(func.sum(DebtLedger.amount_tmt), 0)).filter(DebtLedger.debt_type == "payable").scalar() or 0
    sales_total = session.query(func.coalesce(func.sum(Sale.total_amount_tmt), 0)).filter(Sale.status == "posted").scalar() or 0
    purchase_total = (
        session.query(func.coalesce(func.sum(PurchaseInvoice.total_amount_tmt), 0))
        .filter(PurchaseInvoice.status == "posted")
        .scalar()
        or 0
    )
    open_shifts = session.query(func.count(CashShift.id)).filter(CashShift.status == "open").scalar() or 0
    return success_response(
        {
            "sales_total_tmt": _decimal(sales_total, "0.01"),
            "purchase_total_tmt": _decimal(purchase_total, "0.01"),
            "receivable_tmt": _decimal(receivable, "0.01"),
            "payable_tmt": _decimal(payable, "0.01"),
            "open_shift_count": int(open_shifts),
        }
    )


@router.get("/reports/stock")
def stock_report(
    _: User = Depends(require_reports_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return current stock balances."""

    rows = (
        session.query(StockBalance)
        .options(selectinload(StockBalance.warehouse), selectinload(StockBalance.product), selectinload(StockBalance.uom))
        .order_by(StockBalance.warehouse_id, StockBalance.product_id)
        .all()
    )
    return success_response(
        [
            {
                "warehouse_id": row.warehouse_id,
                "warehouse_name": row.warehouse.name if row.warehouse else None,
                "product_id": row.product_id,
                "product_sku": row.product.sku if row.product else None,
                "product_name": row.product.name if row.product else None,
                "quantity": _decimal(row.quantity, "0.001"),
                "avg_cost_tmt": _decimal(row.avg_cost_tmt, "0.01"),
                "stock_value_tmt": _decimal(money(row.quantity * row.avg_cost_tmt), "0.01"),
            }
            for row in rows
        ]
    )


@router.get("/reports/sales")
def sales_report(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    _: User = Depends(require_reports_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return sales totals for a date range."""

    query = session.query(Sale).filter(Sale.status == "posted")
    query = _date_range_filter(query, Sale.doc_date, date_from, date_to)
    rows = query.all()
    return success_response(
        {
            "document_count": len(rows),
            "sales_total_tmt": _decimal(sum((money(row.total_amount_tmt) for row in rows), Decimal("0.00")), "0.01"),
            "cash_tmt": _decimal(sum((money(row.paid_cash_tmt) for row in rows), Decimal("0.00")), "0.01"),
            "transfer_tmt": _decimal(sum((money(row.paid_transfer_tmt) for row in rows), Decimal("0.00")), "0.01"),
            "bonus_tmt": _decimal(sum((money(row.paid_bonus_tmt) for row in rows), Decimal("0.00")), "0.01"),
            "debt_tmt": _decimal(sum((money(row.debt_amount_tmt) for row in rows), Decimal("0.00")), "0.01"),
        }
    )


@router.get("/reports/purchases")
def purchases_report(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    _: User = Depends(require_reports_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return purchase totals for a date range."""

    query = session.query(PurchaseInvoice).filter(PurchaseInvoice.status == "posted")
    if date_from is not None:
        query = query.filter(PurchaseInvoice.doc_date >= date_from.date())
    if date_to is not None:
        query = query.filter(PurchaseInvoice.doc_date <= date_to.date())
    rows = query.all()
    return success_response(
        {
            "document_count": len(rows),
            "purchase_total_tmt": _decimal(sum((money(row.total_amount_tmt) for row in rows), Decimal("0.00")), "0.01"),
            "unpaid_count": sum(1 for row in rows if row.payment_status == "unpaid"),
            "partial_count": sum(1 for row in rows if row.payment_status == "partial"),
            "paid_count": sum(1 for row in rows if row.payment_status == "paid"),
        }
    )


@router.get("/reports/debts")
def debts_report(
    _: User = Depends(require_reports_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return current receivable/payable balances."""

    counterparties = session.query(Counterparty).order_by(Counterparty.name).all()
    rows = []
    total_receivable = Decimal("0.00")
    total_payable = Decimal("0.00")
    for counterparty in counterparties:
        receivable = current_debt_balance(session, counterparty.id, "receivable")
        payable = current_debt_balance(session, counterparty.id, "payable")
        if receivable == Decimal("0.00") and payable == Decimal("0.00"):
            continue
        total_receivable += receivable
        total_payable += payable
        rows.append(
            {
                "counterparty_id": counterparty.id,
                "counterparty_name": counterparty.name,
                "receivable_tmt": _decimal(receivable, "0.01"),
                "payable_tmt": _decimal(payable, "0.01"),
            }
        )
    return success_response(
        {
            "total_receivable_tmt": _decimal(total_receivable, "0.01"),
            "total_payable_tmt": _decimal(total_payable, "0.01"),
            "rows": rows,
        }
    )


@router.get("/reports/cash-flow")
def cash_flow_report(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    _: User = Depends(require_reports_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return simple cash-flow totals."""

    sales_query = _date_range_filter(session.query(Sale).filter(Sale.status == "posted"), Sale.doc_date, date_from, date_to)
    sales = sales_query.all()
    payment_query = _date_range_filter(session.query(Payment).filter(Payment.status == "posted"), Payment.doc_date, date_from, date_to)
    payments = payment_query.all()
    operation_query = _date_range_filter(session.query(CashOperation), CashOperation.doc_date, date_from, date_to)
    operations = operation_query.all()

    sale_cash = sum((money(row.paid_cash_tmt) for row in sales), Decimal("0.00"))
    sale_transfer = sum((money(row.paid_transfer_tmt) for row in sales), Decimal("0.00"))
    incoming_payments = sum((money(row.amount_tmt) for row in payments if row.direction == "incoming"), Decimal("0.00"))
    outgoing_payments = sum((money(row.amount_tmt) for row in payments if row.direction == "outgoing"), Decimal("0.00"))
    collections = sum((money(row.amount_tmt) for row in operations if row.operation_type == "collection"), Decimal("0.00"))
    return success_response(
        {
            "sale_cash_tmt": _decimal(sale_cash, "0.01"),
            "sale_transfer_tmt": _decimal(sale_transfer, "0.01"),
            "incoming_payments_tmt": _decimal(incoming_payments, "0.01"),
            "outgoing_payments_tmt": _decimal(outgoing_payments, "0.01"),
            "collections_tmt": _decimal(collections, "0.01"),
            "net_cash_flow_tmt": _decimal(sale_cash + incoming_payments - outgoing_payments - collections, "0.01"),
        }
    )
