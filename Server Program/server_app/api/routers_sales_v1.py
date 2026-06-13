"""API v1 routes for sales, cashier shifts, and first report summaries."""

from __future__ import annotations

from datetime import datetime, time, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from server_app.api.dependencies import get_db
from server_app.api.routers_v1 import error_detail, require_v1_permission, success_response
from server_app.db.models import (
    CashOperation,
    CashRegister,
    CashShift,
    Contract,
    Counterparty,
    Currency,
    DebtLedger,
    LoyaltyCard,
    Payment,
    Product,
    Promotion,
    ProductUom,
    PurchaseInvoice,
    Sale,
    SaleLine,
    SaleReturn,
    SaleReturnLine,
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
    SaleReturnCreate,
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
from server_app.services.loyalty import (
    LoyaltyBusinessError,
    get_loyalty_settings,
    loyalty_transaction_total,
    post_loyalty_transaction,
    reverse_loyalty_document,
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
require_sale_return_create = require_v1_permission("sale_return.create")
require_sale_return_post = require_v1_permission("sale_return.post")
require_sale_return_cancel = require_v1_permission("sale_return.cancel")
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


def _ensure_sale_contract_matches(
    session: Session,
    contract_id: int | None,
    *,
    counterparty_id: int | None,
    currency_id: int,
) -> Contract | None:
    """Validate an optional sale contract against the customer and currency."""

    if contract_id is None:
        return None
    if counterparty_id is None:
        raise HTTPException(status_code=400, detail=error_detail("COUNTERPARTY_REQUIRED", "Counterparty is required when a contract is selected."))
    contract = _get_or_404(session, Contract, contract_id, "Contract")
    if not contract.is_active:
        raise HTTPException(status_code=400, detail=error_detail("INACTIVE_CONTRACT", "Contract is inactive."))
    if contract.counterparty_id != counterparty_id:
        raise HTTPException(status_code=400, detail=error_detail("CONTRACT_COUNTERPARTY_MISMATCH", "Contract belongs to another counterparty."))
    if contract.currency_id is not None and contract.currency_id != currency_id:
        raise HTTPException(status_code=400, detail=error_detail("CONTRACT_CURRENCY_MISMATCH", "Contract currency differs from sale currency."))
    return contract


def _credit_limit_warning(session: Session, counterparty: Counterparty | None, added_debt: Decimal) -> dict[str, Any] | None:
    """Return a non-blocking credit-limit warning for sale creation."""

    if counterparty is None or added_debt <= Decimal("0.00"):
        return None
    credit_limit = money(counterparty.credit_limit_tmt)
    if credit_limit <= Decimal("0.00"):
        return None
    current = current_debt_balance(session, counterparty.id, "receivable")
    projected = money(current + added_debt)
    if projected <= credit_limit:
        return None
    return {
        "code": "CREDIT_LIMIT_EXCEEDED",
        "message": "Customer credit limit is exceeded.",
        "current_receivable_tmt": _decimal(current, "0.01"),
        "added_debt_tmt": _decimal(added_debt, "0.01"),
        "projected_receivable_tmt": _decimal(projected, "0.01"),
        "credit_limit_tmt": _decimal(credit_limit, "0.01"),
        "excess_tmt": _decimal(projected - credit_limit, "0.01"),
    }


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
        "promo_id": line.promo_id,
        "promotion_name": line.promotion.name if line.promotion else None,
        "parent_line_id": line.parent_line_id,
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
        "contract_id": row.contract_id,
        "contract_number": row.contract.number if row.contract else None,
        "warehouse_id": row.warehouse_id,
        "warehouse_name": row.warehouse.name if row.warehouse else None,
        "price_list_id": row.price_list_id,
        "currency_id": row.currency_id,
        "currency_code": row.currency.code if row.currency else None,
        "currency_rate": _decimal(row.currency_rate, "0.000001"),
        "loyalty_card_id": row.loyalty_card_id,
        "loyalty_card_number": row.loyalty_card.card_number if row.loyalty_card else None,
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


def _sale_return_line_payload(line: SaleReturnLine) -> dict[str, Any]:
    """Return a sale-return line payload."""

    return {
        "id": line.id,
        "source_sale_line_id": line.source_sale_line_id,
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
        "price_final": _decimal(line.price_final, "0.0001"),
        "amount_tmt": _decimal(line.amount_tmt, "0.01"),
        "avg_cost_tmt": _decimal(line.avg_cost_tmt, "0.0001"),
    }


def _sale_return_payload(row: SaleReturn) -> dict[str, Any]:
    """Return a sale-return payload."""

    return {
        "id": row.id,
        "doc_number": row.doc_number,
        "doc_date": row.doc_date.isoformat() if row.doc_date else None,
        "sale_id": row.sale_id,
        "cash_register_id": row.cash_register_id,
        "cash_register_name": row.cash_register.name if row.cash_register else None,
        "cash_shift_id": row.cash_shift_id,
        "counterparty_id": row.counterparty_id,
        "counterparty_name": row.counterparty.name if row.counterparty else None,
        "contract_id": row.sale.contract_id if row.sale else None,
        "contract_number": row.sale.contract.number if row.sale and row.sale.contract else None,
        "warehouse_id": row.warehouse_id,
        "warehouse_name": row.warehouse.name if row.warehouse else None,
        "currency_id": row.currency_id,
        "currency_code": row.currency.code if row.currency else None,
        "currency_rate": _decimal(row.currency_rate, "0.000001"),
        "total_amount_tmt": _decimal(row.total_amount_tmt, "0.01"),
        "refund_method": row.refund_method,
        "refund_cash_tmt": _decimal(row.refund_cash_tmt, "0.01"),
        "refund_transfer_tmt": _decimal(row.refund_transfer_tmt, "0.01"),
        "refund_bonus_tmt": _decimal(row.refund_bonus_tmt, "0.01"),
        "receivable_correction_tmt": _decimal(row.receivable_correction_tmt, "0.01"),
        "status": row.status,
        "note": row.note,
        "posted_at": row.posted_at.isoformat() if row.posted_at else None,
        "lines": [_sale_return_line_payload(line) for line in row.lines],
    }


def _sale_query(session: Session):
    """Return a sale query with relationships used by payloads."""

    return session.query(Sale).options(
        selectinload(Sale.cash_register),
        selectinload(Sale.cash_shift),
        selectinload(Sale.counterparty),
        selectinload(Sale.contract),
        selectinload(Sale.warehouse),
        selectinload(Sale.currency),
        selectinload(Sale.loyalty_card),
        selectinload(Sale.lines).selectinload(SaleLine.product),
        selectinload(Sale.lines).selectinload(SaleLine.service),
        selectinload(Sale.lines).selectinload(SaleLine.uom),
        selectinload(Sale.lines).selectinload(SaleLine.promotion),
    )


def _refresh_sale(session: Session, sale_id: int) -> Sale:
    """Reload one sale with payload relationships."""

    sale = _sale_query(session).filter(Sale.id == sale_id).one_or_none()
    if sale is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", "Sale not found."))
    return sale


def _sale_return_query(session: Session):
    """Return a sale-return query with relationships used by payloads."""

    return session.query(SaleReturn).options(
        selectinload(SaleReturn.sale).selectinload(Sale.contract),
        selectinload(SaleReturn.cash_register),
        selectinload(SaleReturn.cash_shift),
        selectinload(SaleReturn.counterparty),
        selectinload(SaleReturn.warehouse),
        selectinload(SaleReturn.currency),
        selectinload(SaleReturn.lines).selectinload(SaleReturnLine.product),
        selectinload(SaleReturn.lines).selectinload(SaleReturnLine.service),
        selectinload(SaleReturn.lines).selectinload(SaleReturnLine.uom),
    )


def _refresh_sale_return(session: Session, sale_return_id: int) -> SaleReturn:
    """Reload one sale return with payload relationships."""

    sale_return = _sale_return_query(session).filter(SaleReturn.id == sale_return_id).one_or_none()
    if sale_return is None:
        raise HTTPException(status_code=404, detail=error_detail("NOT_FOUND", "Sale return not found."))
    return sale_return


def _returned_quantity_for_sale_line(session: Session, sale_line_id: int) -> Decimal:
    """Return already posted return quantity for a sale line."""

    value = (
        session.query(func.coalesce(func.sum(SaleReturnLine.quantity), 0))
        .join(SaleReturn, SaleReturn.id == SaleReturnLine.sale_return_id)
        .filter(SaleReturn.status == "posted", SaleReturnLine.source_sale_line_id == sale_line_id)
        .scalar()
        or 0
    )
    return qty4(value)


def _sale_return_payment_split(payload: SaleReturnCreate, total: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Return normalized cash, transfer, bonus, and receivable-correction amounts."""

    zero = Decimal("0.00")
    if payload.refund_method == "cash":
        supplied = money(payload.refund_cash_tmt)
        if supplied not in (zero, total):
            raise HTTPException(status_code=400, detail=error_detail("REFUND_TOTAL_MISMATCH", "Cash refund must equal return total."))
        return total, zero, zero, zero
    if payload.refund_method == "transfer":
        supplied = money(payload.refund_transfer_tmt)
        if supplied not in (zero, total):
            raise HTTPException(status_code=400, detail=error_detail("REFUND_TOTAL_MISMATCH", "Transfer refund must equal return total."))
        return zero, total, zero, zero
    if payload.refund_method == "bonus":
        supplied = money(payload.refund_bonus_tmt)
        if supplied not in (zero, total):
            raise HTTPException(status_code=400, detail=error_detail("REFUND_TOTAL_MISMATCH", "Bonus refund must equal return total."))
        return zero, zero, total, zero
    if payload.refund_method == "debt_correction":
        supplied = money(payload.receivable_correction_tmt)
        if supplied not in (zero, total):
            raise HTTPException(status_code=400, detail=error_detail("REFUND_TOTAL_MISMATCH", "Receivable correction must equal return total."))
        return zero, zero, zero, total

    cash = money(payload.refund_cash_tmt)
    transfer = money(payload.refund_transfer_tmt)
    bonus = money(payload.refund_bonus_tmt)
    receivable = money(payload.receivable_correction_tmt)
    if money(cash + transfer + bonus + receivable) != total:
        raise HTTPException(status_code=400, detail=error_detail("REFUND_TOTAL_MISMATCH", "Mixed refund parts must equal return total."))
    return cash, transfer, bonus, receivable


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
    gross_amount = money(quantity * final_price)
    manual_discount = money((gross_amount * Decimal(payload.discount_percent) / Decimal("100")) + payload.discount_amount)
    if manual_discount > gross_amount:
        raise HTTPException(status_code=400, detail=error_detail("DISCOUNT_EXCEEDS_LINE", "Line discount exceeds line amount."))
    line_amount = money(gross_amount - manual_discount)
    effective_price = price(line_amount / quantity)

    product: Product | None = None
    service: Service | None = None
    resolved_uom_id = payload.uom_id
    if payload.product_id is not None:
        product = _get_or_404(session, Product, payload.product_id, "Product")
        if not product.is_active:
            raise HTTPException(status_code=400, detail=error_detail("INACTIVE_PRODUCT", "Product is inactive."))
        if payload.product_uom_id is not None:
            product_uom = _get_or_404(session, ProductUom, payload.product_uom_id, "Product UOM")
            resolved_uom_id = product_uom.uom_id
        elif resolved_uom_id is None:
            resolved_uom_id = product.base_uom_id
        line_type = payload.line_type or "product"
    else:
        service = _get_or_404(session, Service, payload.service_id, "Service")
        if not service.is_active:
            raise HTTPException(status_code=400, detail=error_detail("INACTIVE_SERVICE", "Service is inactive."))
        line_type = payload.line_type or "service"

    return SaleLine(
        line_type=line_type,
        product_id=payload.product_id,
        product=product,
        service_id=payload.service_id,
        service=service,
        product_uom_id=payload.product_uom_id,
        uom_id=resolved_uom_id,
        quantity=quantity,
        price_list_price=list_price,
        price_final=effective_price,
        discount_percent=payload.discount_percent,
        discount_amount=manual_discount,
        amount_tmt=line_amount,
        avg_cost_tmt=Decimal("0.0000"),
        price_override=payload.price_override,
    )


def _promotion_matches_product(promotion: Promotion, product: Product | None) -> bool:
    """Return whether a promotion targets the product on a sale line."""

    if product is None:
        return False
    if promotion.target_type == "all":
        return True
    if promotion.target_type == "product":
        return promotion.product_id == product.id
    if promotion.target_type == "group":
        return promotion.product_group_id == product.group_id
    return False


def _promotion_discount_amount(promotion: Promotion, line: SaleLine) -> Decimal:
    """Calculate the discount amount a promotion gives to one line."""

    current_amount = money(line.amount_tmt)
    if current_amount <= Decimal("0.00"):
        return Decimal("0.00")
    if promotion.discount_type == "percent":
        return min(current_amount, money(current_amount * Decimal(promotion.discount_value) / Decimal("100")))
    if promotion.discount_type == "fixed_amount":
        return min(current_amount, money(promotion.discount_value))
    if promotion.discount_type == "fixed_price":
        target_amount = money(line.quantity * price(promotion.discount_value))
        return max(Decimal("0.00"), money(current_amount - target_amount))
    return Decimal("0.00")


def _apply_promotions_to_lines(session: Session, lines: list[SaleLine], sale_date: datetime) -> list[SaleLine]:
    """Apply active discount and gift promotions to sale lines."""

    promotions = (
        session.query(Promotion)
        .filter(
            Promotion.is_active.is_(True),
            Promotion.valid_from <= sale_date,
            or_(Promotion.valid_to.is_(None), Promotion.valid_to >= sale_date),
        )
        .order_by(Promotion.id)
        .all()
    )
    if not promotions:
        return lines

    gift_lines: list[SaleLine] = []
    for line in lines:
        if line.product_id is None or line.line_type == "promo_gift":
            continue
        product = line.product or session.get(Product, line.product_id)
        matching = [row for row in promotions if qty4(line.quantity) >= qty4(row.min_quantity) and _promotion_matches_product(row, product)]

        best_discount: tuple[Decimal, Promotion] | None = None
        for promotion in matching:
            if promotion.promotion_type != "discount":
                continue
            discount_amount = _promotion_discount_amount(promotion, line)
            if discount_amount > Decimal("0.00") and (best_discount is None or discount_amount > best_discount[0]):
                best_discount = (discount_amount, promotion)
        if best_discount is not None:
            discount_amount, promotion = best_discount
            line.discount_amount = money(line.discount_amount + discount_amount)
            line.amount_tmt = money(line.amount_tmt - discount_amount)
            line.price_final = price(line.amount_tmt / line.quantity)
            line.promo_id = promotion.id
            if promotion.discount_type == "percent":
                line.discount_percent = min(Decimal("100"), Decimal(line.discount_percent) + Decimal(promotion.discount_value))

        for promotion in matching:
            if promotion.promotion_type != "gift" or promotion.gift_product_id is None:
                continue
            multiplier = int(qty4(line.quantity) // qty4(promotion.min_quantity))
            if multiplier <= 0:
                continue
            gift_product = session.get(Product, promotion.gift_product_id)
            if gift_product is None or not gift_product.is_active:
                continue
            gift_lines.append(
                SaleLine(
                    line_type="promo_gift",
                    product_id=gift_product.id,
                    product=gift_product,
                    uom_id=gift_product.base_uom_id,
                    quantity=qty4(promotion.gift_quantity * multiplier),
                    price_list_price=Decimal("0.0000"),
                    price_final=Decimal("0.0000"),
                    discount_percent=Decimal("0.00"),
                    discount_amount=Decimal("0.00"),
                    amount_tmt=Decimal("0.00"),
                    avg_cost_tmt=Decimal("0.0000"),
                    promo_id=promotion.id,
                    parent_line=line,
                    price_override=False,
                )
            )
    return [*lines, *gift_lines]


def _loyalty_http_error(exc: LoyaltyBusinessError) -> HTTPException:
    """Convert a loyalty business error into an API v1 envelope error."""

    return HTTPException(status_code=400, detail=error_detail(exc.code, exc.message))


def _validate_loyalty_payment(
    session: Session,
    payload: SaleCreate,
    counterparty: Counterparty | None,
    total: Decimal,
    paid_bonus: Decimal,
) -> LoyaltyCard | None:
    """Validate bonus redemption limits and selected loyalty card."""

    card: LoyaltyCard | None = None
    if payload.loyalty_card_id is not None:
        card = _get_or_404(session, LoyaltyCard, payload.loyalty_card_id, "Loyalty card")
        if not card.is_active:
            raise HTTPException(status_code=400, detail=error_detail("INACTIVE_LOYALTY_CARD", "Loyalty card is inactive."))
        if card.counterparty_id is not None and counterparty is not None and card.counterparty_id != counterparty.id:
            raise HTTPException(status_code=400, detail=error_detail("LOYALTY_COUNTERPARTY_MISMATCH", "Loyalty card belongs to another customer."))
    if paid_bonus <= Decimal("0.00"):
        return card
    if card is None:
        raise HTTPException(status_code=400, detail=error_detail("LOYALTY_CARD_REQUIRED", "Bonus payment requires a loyalty card."))
    settings = get_loyalty_settings(session)
    if not settings.is_active:
        raise HTTPException(status_code=400, detail=error_detail("LOYALTY_DISABLED", "Loyalty program is disabled."))
    if money(card.balance_tmt) < paid_bonus:
        raise HTTPException(status_code=400, detail=error_detail("INSUFFICIENT_BONUS", "Loyalty card balance is insufficient."))
    redemption_limit = money(total * Decimal(settings.redemption_limit_percent) / Decimal("100"))
    if paid_bonus > redemption_limit:
        raise HTTPException(status_code=400, detail=error_detail("BONUS_LIMIT_EXCEEDED", "Bonus payment exceeds the loyalty redemption limit."))
    return card


def _post_sale_loyalty(session: Session, sale: Sale, user_id: int | None) -> None:
    """Post loyalty redemption and accrual for a sale."""

    if sale.loyalty_card_id is None:
        return
    card = sale.loyalty_card or session.get(LoyaltyCard, sale.loyalty_card_id)
    if card is None:
        return
    settings = get_loyalty_settings(session)
    paid_bonus = money(sale.paid_bonus_tmt)
    if paid_bonus > Decimal("0.00") and not settings.is_active:
        raise LoyaltyBusinessError("LOYALTY_DISABLED", "Loyalty program is disabled.")
    if paid_bonus > Decimal("0.00"):
        post_loyalty_transaction(
            session,
            card,
            transaction_type="redemption",
            amount_tmt=-paid_bonus,
            doc_type="sale",
            doc_id=sale.id,
            note="Sale bonus redemption",
            user_id=user_id,
        )
    if not settings.is_active:
        return
    earn_base = money(sale.total_amount_tmt - paid_bonus)
    accrual = money(earn_base * Decimal(settings.earn_rate_percent) / Decimal("100"))
    if accrual > Decimal("0.00"):
        post_loyalty_transaction(
            session,
            card,
            transaction_type="accrual",
            amount_tmt=accrual,
            doc_type="sale",
            doc_id=sale.id,
            note="Sale bonus accrual",
            user_id=user_id,
        )


def _post_sale_return_loyalty(session: Session, sale_return: SaleReturn, user_id: int | None) -> None:
    """Post loyalty reversals and optional bonus refund for a sale return."""

    sale = sale_return.sale
    if sale is None or sale.loyalty_card_id is None:
        return
    card = sale.loyalty_card or session.get(LoyaltyCard, sale.loyalty_card_id)
    if card is None:
        return
    refund_bonus = money(sale_return.refund_bonus_tmt)
    if refund_bonus > Decimal("0.00"):
        post_loyalty_transaction(
            session,
            card,
            transaction_type="return_refund",
            amount_tmt=refund_bonus,
            doc_type="sale_return",
            doc_id=sale_return.id,
            note="Sale return bonus refund",
            user_id=user_id,
        )
    sale_total = money(sale.total_amount_tmt)
    if sale_total <= Decimal("0.00"):
        return
    ratio = money(sale_return.total_amount_tmt) / sale_total
    redeemed = -loyalty_transaction_total(session, doc_type="sale", doc_id=sale.id, transaction_type="redemption")
    redeemed_reversal = money(redeemed * ratio)
    if redeemed_reversal > Decimal("0.00"):
        post_loyalty_transaction(
            session,
            card,
            transaction_type="return_redemption_reversal",
            amount_tmt=redeemed_reversal,
            doc_type="sale_return",
            doc_id=sale_return.id,
            note="Sale return bonus redemption reversal",
            user_id=user_id,
        )
    accrued = loyalty_transaction_total(session, doc_type="sale", doc_id=sale.id, transaction_type="accrual")
    accrual_reversal = money(accrued * ratio)
    if accrual_reversal > Decimal("0.00"):
        post_loyalty_transaction(
            session,
            card,
            transaction_type="return_accrual_reversal",
            amount_tmt=-accrual_reversal,
            doc_type="sale_return",
            doc_id=sale_return.id,
            note="Sale return bonus accrual reversal",
            user_id=user_id,
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
        required=payload.sale_type == "wholesale" or payload.payment_type == "debt" or money(payload.debt_amount_tmt) > Decimal("0.00") or payload.contract_id is not None,
    )
    _ensure_sale_contract_matches(session, payload.contract_id, counterparty_id=payload.counterparty_id, currency_id=payload.currency_id)

    doc_number = payload.doc_number or generate_doc_number(session, Sale, "SAL")
    if session.query(Sale).filter(Sale.doc_number == doc_number).one_or_none() is not None:
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_DOC_NUMBER", "Sale number already exists."))

    sale_date = payload.doc_date or now_utc()
    lines = [_build_sale_line(session, item) for item in payload.lines]
    lines = _apply_promotions_to_lines(session, lines, sale_date)
    subtotal = money(sum((line.amount_tmt for line in lines), Decimal("0")))
    doc_discount = money((subtotal * money(payload.discount_percent) / Decimal("100")) + payload.discount_amount_tmt)
    if doc_discount > subtotal:
        raise HTTPException(status_code=400, detail=error_detail("DISCOUNT_EXCEEDS_TOTAL", "Document discount exceeds sale subtotal."))
    total = money(subtotal - doc_discount)
    paid_cash, paid_transfer, paid_bonus, debt = _payment_split(payload, total)
    if debt > Decimal("0.00") and counterparty is None:
        raise HTTPException(status_code=400, detail=error_detail("COUNTERPARTY_REQUIRED", "Counterparty is required for debt amount."))
    loyalty_card = _validate_loyalty_payment(session, payload, counterparty, total, paid_bonus)
    credit_warning = _credit_limit_warning(session, counterparty, debt)

    sale = Sale(
        doc_number=doc_number,
        doc_date=sale_date,
        sale_type=payload.sale_type,
        cash_register_id=payload.cash_register_id,
        cash_shift_id=payload.cash_shift_id,
        counterparty_id=payload.counterparty_id,
        contract_id=payload.contract_id,
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
        loyalty_card_id=loyalty_card.id if loyalty_card is not None else None,
        status="draft",
        created_by_user_id=current_user.id,
    )
    sale.lines.extend(lines)
    session.add(sale)
    session.commit()
    meta = {"warnings": [credit_warning]} if credit_warning is not None else None
    return success_response(_sale_payload(_refresh_sale(session, sale.id)), meta=meta)


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
            contract_id=sale.contract_id,
        )
    try:
        _post_sale_loyalty(session, sale, current_user.id)
    except LoyaltyBusinessError as exc:
        session.rollback()
        raise _loyalty_http_error(exc) from exc

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
        posted_returns = session.query(func.count(SaleReturn.id)).filter(SaleReturn.sale_id == sale.id, SaleReturn.status == "posted").scalar() or 0
        if posted_returns:
            raise HTTPException(status_code=400, detail=error_detail("SALE_HAS_RETURNS", "Cancel posted sale returns before cancelling this sale."))
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
                contract_id=sale.contract_id,
            )
        if sale.loyalty_card_id is not None:
            card = sale.loyalty_card or session.get(LoyaltyCard, sale.loyalty_card_id)
            if card is not None:
                try:
                    reverse_loyalty_document(
                        session,
                        card,
                        doc_type="sale",
                        doc_id=sale.id,
                        transaction_type="cancellation",
                        note="Sale cancelled",
                        user_id=current_user.id,
                    )
                except LoyaltyBusinessError as exc:
                    session.rollback()
                    raise _loyalty_http_error(exc) from exc
    sale.status = "cancelled"
    sale.cancelled_by_user_id = current_user.id
    sale.cancelled_at = now_utc()
    session.commit()
    return success_response(_sale_payload(_refresh_sale(session, sale.id)))


@router.get("/sale-returns")
def list_sale_returns(
    status_filter: str | None = Query(default=None, alias="status"),
    _: User = Depends(require_sale_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """List recent sale returns."""

    query = _sale_return_query(session)
    if status_filter is not None:
        query = query.filter(SaleReturn.status == status_filter)
    rows = query.order_by(SaleReturn.id.desc()).limit(200).all()
    return success_response([_sale_return_payload(row) for row in rows])


@router.get("/sale-returns/{sale_return_id}")
def get_sale_return(
    sale_return_id: int,
    _: User = Depends(require_sale_view),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Return one sale return."""

    return success_response(_sale_return_payload(_refresh_sale_return(session, sale_return_id)))


@router.post("/sale-returns", status_code=status.HTTP_201_CREATED)
def create_sale_return(
    payload: SaleReturnCreate,
    current_user: User = Depends(require_sale_return_create),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a draft sale return against a posted sale."""

    sale = _refresh_sale(session, payload.sale_id)
    if sale.status != "posted":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only posted sales can be returned."))
    register_id = payload.cash_register_id if payload.cash_register_id is not None else sale.cash_register_id
    shift_id = payload.cash_shift_id if payload.cash_shift_id is not None else sale.cash_shift_id
    if register_id is not None:
        register = _get_or_404(session, CashRegister, register_id, "Cash register")
        if register.warehouse_id != sale.warehouse_id:
            raise HTTPException(status_code=400, detail=error_detail("REGISTER_WAREHOUSE_MISMATCH", "Cash register belongs to another warehouse."))
    if shift_id is not None:
        _validate_shift_for_register(session, shift_id, register_id)

    source_lines = {line.id: line for line in sale.lines}
    seen_lines: set[int] = set()
    return_lines: list[SaleReturnLine] = []
    for line_payload in payload.lines:
        if line_payload.source_sale_line_id in seen_lines:
            raise HTTPException(status_code=400, detail=error_detail("DUPLICATE_RETURN_LINE", "A sale line can appear only once in a return."))
        seen_lines.add(line_payload.source_sale_line_id)
        source_line = source_lines.get(line_payload.source_sale_line_id)
        if source_line is None:
            raise HTTPException(status_code=400, detail=error_detail("SALE_LINE_MISMATCH", "Return line does not belong to the source sale."))
        returned_qty = _returned_quantity_for_sale_line(session, source_line.id)
        remaining_qty = qty4(source_line.quantity) - returned_qty
        return_qty = qty4(line_payload.quantity)
        if return_qty > remaining_qty:
            raise HTTPException(status_code=400, detail=error_detail("RETURN_EXCEEDS_SALE", "Return quantity exceeds the source sale quantity."))
        final_price = price(line_payload.price_final if line_payload.price_final is not None else source_line.price_final)
        return_lines.append(
            SaleReturnLine(
                source_sale_line_id=source_line.id,
                product_id=source_line.product_id,
                service_id=source_line.service_id,
                product_uom_id=source_line.product_uom_id,
                uom_id=source_line.uom_id,
                quantity=return_qty,
                price_final=final_price,
                amount_tmt=money(return_qty * final_price),
                avg_cost_tmt=source_line.avg_cost_tmt,
            )
        )

    total = money(sum((line.amount_tmt for line in return_lines), Decimal("0.00")))
    refund_cash, refund_transfer, refund_bonus, receivable_correction = _sale_return_payment_split(payload, total)
    if refund_cash > Decimal("0.00") and shift_id is None:
        raise HTTPException(status_code=400, detail=error_detail("SHIFT_NOT_OPEN", "Cash refund requires an open cash shift."))
    if refund_bonus > Decimal("0.00") and sale.loyalty_card_id is None:
        raise HTTPException(status_code=400, detail=error_detail("LOYALTY_CARD_REQUIRED", "Bonus refund requires the source sale to have a loyalty card."))
    if receivable_correction > Decimal("0.00") and sale.counterparty_id is None:
        raise HTTPException(status_code=400, detail=error_detail("COUNTERPARTY_REQUIRED", "Receivable correction requires a counterparty."))

    doc_number = payload.doc_number or generate_doc_number(session, SaleReturn, "SRT")
    if session.query(SaleReturn).filter(SaleReturn.doc_number == doc_number).one_or_none() is not None:
        raise HTTPException(status_code=409, detail=error_detail("DUPLICATE_DOC_NUMBER", "Sale return number already exists."))
    sale_return = SaleReturn(
        doc_number=doc_number,
        doc_date=payload.doc_date or now_utc(),
        sale_id=sale.id,
        cash_register_id=register_id,
        cash_shift_id=shift_id,
        counterparty_id=sale.counterparty_id,
        warehouse_id=sale.warehouse_id,
        currency_id=sale.currency_id,
        currency_rate=sale.currency_rate,
        total_amount_tmt=total,
        refund_method=payload.refund_method,
        refund_cash_tmt=refund_cash,
        refund_transfer_tmt=refund_transfer,
        refund_bonus_tmt=refund_bonus,
        receivable_correction_tmt=receivable_correction,
        note=payload.note,
        created_by_user_id=current_user.id,
    )
    sale_return.lines.extend(return_lines)
    session.add(sale_return)
    session.commit()
    return success_response(_sale_return_payload(_refresh_sale_return(session, sale_return.id)))


@router.post("/sale-returns/{sale_return_id}/post")
def post_sale_return(
    sale_return_id: int,
    current_user: User = Depends(require_sale_return_post),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Post a sale return into stock and receivable ledgers."""

    sale_return = _refresh_sale_return(session, sale_return_id)
    if sale_return.status != "draft":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Only draft sale returns can be posted."))
    if sale_return.cash_shift_id is not None:
        _validate_shift_for_register(session, sale_return.cash_shift_id, sale_return.cash_register_id)
    try:
        for line in sale_return.lines:
            if line.product_id is None:
                continue
            post_stock_movement(
                session,
                warehouse_id=sale_return.warehouse_id,
                product_id=line.product_id,
                uom_id=line.uom_id,
                movement_type="sale_return",
                document_type="sale_return",
                document_id=sale_return.id,
                quantity_delta=line.quantity,
                unit_cost_tmt=line.avg_cost_tmt,
                user_id=current_user.id,
            )
    except WarehouseBusinessError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=error_detail(exc.code, str(exc), exc.details)) from exc

    if money(sale_return.receivable_correction_tmt) > Decimal("0.00") and sale_return.counterparty_id is not None:
        post_debt_entry(
            session,
            counterparty_id=sale_return.counterparty_id,
            debt_type="receivable",
            doc_type="sale_return",
            doc_id=sale_return.id,
            doc_number=sale_return.doc_number,
            doc_date=sale_return.doc_date,
            amount_tmt=-money(sale_return.receivable_correction_tmt),
            currency_id=sale_return.currency_id,
            amount_cur=-money(sale_return.receivable_correction_tmt),
            note="Sale return posted",
            user_id=current_user.id,
            contract_id=sale_return.sale.contract_id if sale_return.sale else None,
        )
    try:
        _post_sale_return_loyalty(session, sale_return, current_user.id)
    except LoyaltyBusinessError as exc:
        session.rollback()
        raise _loyalty_http_error(exc) from exc

    sale_return.status = "posted"
    sale_return.posted_by_user_id = current_user.id
    sale_return.posted_at = now_utc()
    session.commit()
    return success_response(_sale_return_payload(_refresh_sale_return(session, sale_return.id)))


@router.post("/sale-returns/{sale_return_id}/cancel")
def cancel_sale_return(
    sale_return_id: int,
    current_user: User = Depends(require_sale_return_cancel),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Cancel a draft sale return or reverse a posted one."""

    sale_return = _refresh_sale_return(session, sale_return_id)
    if sale_return.status == "cancelled":
        raise HTTPException(status_code=400, detail=error_detail("INVALID_STATUS", "Sale return is already cancelled."))
    if sale_return.status == "posted":
        try:
            for line in sale_return.lines:
                if line.product_id is None:
                    continue
                post_stock_movement(
                    session,
                    warehouse_id=sale_return.warehouse_id,
                    product_id=line.product_id,
                    uom_id=line.uom_id,
                    movement_type="sale_return_cancel",
                    document_type="sale_return",
                    document_id=sale_return.id,
                    quantity_delta=-line.quantity,
                    unit_cost_tmt=line.avg_cost_tmt,
                    user_id=current_user.id,
                )
        except WarehouseBusinessError as exc:
            session.rollback()
            raise HTTPException(status_code=400, detail=error_detail(exc.code, str(exc), exc.details)) from exc
        if money(sale_return.receivable_correction_tmt) > Decimal("0.00") and sale_return.counterparty_id is not None:
            post_debt_entry(
                session,
                counterparty_id=sale_return.counterparty_id,
                debt_type="receivable",
                doc_type="sale_return",
                doc_id=sale_return.id,
                doc_number=sale_return.doc_number,
                doc_date=now_utc(),
                amount_tmt=money(sale_return.receivable_correction_tmt),
                currency_id=sale_return.currency_id,
                amount_cur=money(sale_return.receivable_correction_tmt),
                note="Sale return cancelled",
                user_id=current_user.id,
                contract_id=sale_return.sale.contract_id if sale_return.sale else None,
            )
        sale = sale_return.sale
        if sale is not None and sale.loyalty_card_id is not None:
            card = sale.loyalty_card or session.get(LoyaltyCard, sale.loyalty_card_id)
            if card is not None:
                try:
                    reverse_loyalty_document(
                        session,
                        card,
                        doc_type="sale_return",
                        doc_id=sale_return.id,
                        transaction_type="return_cancellation",
                        note="Sale return cancelled",
                        user_id=current_user.id,
                    )
                except LoyaltyBusinessError as exc:
                    session.rollback()
                    raise _loyalty_http_error(exc) from exc
    sale_return.status = "cancelled"
    sale_return.cancelled_by_user_id = current_user.id
    sale_return.cancelled_at = now_utc()
    session.commit()
    return success_response(_sale_return_payload(_refresh_sale_return(session, sale_return.id)))


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
    returns_total = session.query(func.coalesce(func.sum(SaleReturn.total_amount_tmt), 0)).filter(SaleReturn.status == "posted").scalar() or 0
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
            "returns_total_tmt": _decimal(returns_total, "0.01"),
            "net_sales_tmt": _decimal(money(sales_total) - money(returns_total), "0.01"),
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
    return_query = session.query(SaleReturn).filter(SaleReturn.status == "posted")
    return_query = _date_range_filter(return_query, SaleReturn.doc_date, date_from, date_to)
    return_rows = return_query.all()
    sales_total = sum((money(row.total_amount_tmt) for row in rows), Decimal("0.00"))
    returns_total = sum((money(row.total_amount_tmt) for row in return_rows), Decimal("0.00"))
    return success_response(
        {
            "document_count": len(rows),
            "sales_total_tmt": _decimal(sales_total, "0.01"),
            "returns_count": len(return_rows),
            "returns_amount_tmt": _decimal(returns_total, "0.01"),
            "net_amount_tmt": _decimal(sales_total - returns_total, "0.01"),
            "cash_tmt": _decimal(sum((money(row.paid_cash_tmt) for row in rows), Decimal("0.00")), "0.01"),
            "transfer_tmt": _decimal(sum((money(row.paid_transfer_tmt) for row in rows), Decimal("0.00")), "0.01"),
            "bonus_tmt": _decimal(sum((money(row.paid_bonus_tmt) for row in rows), Decimal("0.00")), "0.01"),
            "debt_tmt": _decimal(sum((money(row.debt_amount_tmt) for row in rows), Decimal("0.00")), "0.01"),
            "return_cash_tmt": _decimal(sum((money(row.refund_cash_tmt) for row in return_rows), Decimal("0.00")), "0.01"),
            "return_transfer_tmt": _decimal(sum((money(row.refund_transfer_tmt) for row in return_rows), Decimal("0.00")), "0.01"),
            "return_bonus_tmt": _decimal(sum((money(row.refund_bonus_tmt) for row in return_rows), Decimal("0.00")), "0.01"),
            "return_debt_correction_tmt": _decimal(sum((money(row.receivable_correction_tmt) for row in return_rows), Decimal("0.00")), "0.01"),
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
    return_query = _date_range_filter(session.query(SaleReturn).filter(SaleReturn.status == "posted"), SaleReturn.doc_date, date_from, date_to)
    sale_returns = return_query.all()

    sale_cash = sum((money(row.paid_cash_tmt) for row in sales), Decimal("0.00"))
    sale_transfer = sum((money(row.paid_transfer_tmt) for row in sales), Decimal("0.00"))
    incoming_payments = sum((money(row.amount_tmt) for row in payments if row.direction == "incoming"), Decimal("0.00"))
    outgoing_payments = sum((money(row.amount_tmt) for row in payments if row.direction == "outgoing"), Decimal("0.00"))
    collections = sum((money(row.amount_tmt) for row in operations if row.operation_type == "collection"), Decimal("0.00"))
    return_cash = sum((money(row.refund_cash_tmt) for row in sale_returns), Decimal("0.00"))
    return_transfer = sum((money(row.refund_transfer_tmt) for row in sale_returns), Decimal("0.00"))
    return success_response(
        {
            "sale_cash_tmt": _decimal(sale_cash, "0.01"),
            "sale_transfer_tmt": _decimal(sale_transfer, "0.01"),
            "return_cash_tmt": _decimal(return_cash, "0.01"),
            "return_transfer_tmt": _decimal(return_transfer, "0.01"),
            "incoming_payments_tmt": _decimal(incoming_payments, "0.01"),
            "outgoing_payments_tmt": _decimal(outgoing_payments, "0.01"),
            "collections_tmt": _decimal(collections, "0.01"),
            "net_cash_flow_tmt": _decimal(sale_cash + incoming_payments - outgoing_payments - collections - return_cash, "0.01"),
        }
    )
