"""Warehouse stock posting helpers."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import json

from sqlalchemy.orm import Session

from server_app.db.models import Product, Setting, StockBalance, StockMovement


QTY_ZERO = Decimal("0.000")
COST_ZERO = Decimal("0.00")
QTY_QUANT = Decimal("0.001")
COST_QUANT = Decimal("0.01")


class WarehouseBusinessError(ValueError):
    """Raised when a warehouse business rule rejects an operation."""

    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def quantity(value: Decimal | int | str) -> Decimal:
    """Normalize a quantity to three decimal places."""

    return Decimal(value).quantize(QTY_QUANT, rounding=ROUND_HALF_UP)


def money(value: Decimal | int | str) -> Decimal:
    """Normalize a money amount to two decimal places."""

    return Decimal(value).quantize(COST_QUANT, rounding=ROUND_HALF_UP)


def allow_negative_stock(session: Session) -> bool:
    """Return the warehouse negative-stock setting, defaulting to false."""

    setting = session.query(Setting).filter(Setting.key == "warehouse").one_or_none()
    if setting is None:
        return False
    try:
        values = json.loads(setting.value_json)
    except json.JSONDecodeError:
        return False
    return bool(values.get("allow_negative_stock", False)) if isinstance(values, dict) else False


def get_or_create_balance(
    session: Session,
    warehouse_id: int,
    product_id: int,
    uom_id: int | None,
) -> StockBalance:
    """Return a stock balance row, creating it when absent."""

    balance = (
        session.query(StockBalance)
        .filter(
            StockBalance.warehouse_id == warehouse_id,
            StockBalance.product_id == product_id,
            StockBalance.uom_id == uom_id,
        )
        .one_or_none()
    )
    if balance is not None:
        return balance

    balance = StockBalance(
        warehouse_id=warehouse_id,
        product_id=product_id,
        uom_id=uom_id,
        quantity=QTY_ZERO,
        avg_cost_tmt=COST_ZERO,
    )
    session.add(balance)
    session.flush()
    return balance


def post_stock_movement(
    session: Session,
    *,
    warehouse_id: int,
    product_id: int,
    uom_id: int | None,
    movement_type: str,
    document_type: str,
    document_id: int | None,
    quantity_delta: Decimal,
    unit_cost_tmt: Decimal | None,
    user_id: int | None,
    allow_negative: bool | None = None,
) -> StockMovement:
    """Append one movement row and update the current stock balance."""

    delta = quantity(quantity_delta)
    if delta == QTY_ZERO:
        raise WarehouseBusinessError("ZERO_QUANTITY", "Stock movement quantity cannot be zero.")

    balance = get_or_create_balance(session, warehouse_id, product_id, uom_id)
    current_qty = quantity(balance.quantity)
    current_cost = money(balance.avg_cost_tmt)
    cost = money(unit_cost_tmt if unit_cost_tmt is not None else current_cost)
    new_qty = quantity(current_qty + delta)

    if allow_negative is None:
        allow_negative = allow_negative_stock(session)
    if new_qty < QTY_ZERO and not allow_negative:
        raise WarehouseBusinessError(
            "INSUFFICIENT_STOCK",
            "Insufficient stock balance for this operation.",
            {
                "warehouse_id": warehouse_id,
                "product_id": product_id,
                "uom_id": uom_id,
                "available": str(current_qty),
                "requested": str(abs(delta)),
            },
        )

    if delta > QTY_ZERO:
        if current_qty <= QTY_ZERO:
            new_cost = cost
        else:
            total_value = (current_qty * current_cost) + (delta * cost)
            new_cost = money(total_value / new_qty) if new_qty > QTY_ZERO else cost
        balance.avg_cost_tmt = new_cost
        if cost > COST_ZERO:
            product = session.get(Product, product_id)
            if product is not None:
                product.last_known_cost = cost
    else:
        cost = current_cost

    balance.quantity = new_qty
    amount = money(delta * cost)
    movement = StockMovement(
        warehouse_id=warehouse_id,
        product_id=product_id,
        uom_id=uom_id,
        movement_type=movement_type,
        document_type=document_type,
        document_id=document_id,
        quantity=delta,
        unit_cost_tmt=cost,
        amount_tmt=amount,
        created_by_user_id=user_id,
    )
    session.add(movement)
    session.flush()
    return movement
