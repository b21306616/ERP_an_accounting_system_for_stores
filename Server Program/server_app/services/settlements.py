"""Settlement and document-number helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from server_app.db.models import DebtLedger, Payment, PaymentAllocation, PurchaseInvoice


MONEY_QUANT = Decimal("0.01")
PRICE_QUANT = Decimal("0.0001")
QTY4_QUANT = Decimal("0.0001")


def now_utc() -> datetime:
    """Return timezone-aware UTC now."""

    return datetime.now(timezone.utc)


def money(value: Decimal | int | str) -> Decimal:
    """Normalize a monetary value to two decimal places."""

    return Decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def price(value: Decimal | int | str) -> Decimal:
    """Normalize a unit price to four decimal places."""

    return Decimal(value).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)


def qty4(value: Decimal | int | str) -> Decimal:
    """Normalize a document quantity to four decimal places."""

    return Decimal(value).quantize(QTY4_QUANT, rounding=ROUND_HALF_UP)


def generate_doc_number(session: Session, model: type[Any], prefix: str) -> str:
    """Generate a simple sequential document number for one table."""

    next_number = (session.query(func.count(model.id)).scalar() or 0) + 1
    return f"{prefix}-{next_number:06d}"


def current_debt_balance(session: Session, counterparty_id: int, debt_type: str) -> Decimal:
    """Return current debt balance for one counterparty and debt side."""

    value = (
        session.query(func.coalesce(func.sum(DebtLedger.amount_tmt), 0))
        .filter(DebtLedger.counterparty_id == counterparty_id, DebtLedger.debt_type == debt_type)
        .scalar()
    )
    return money(value or 0)


def post_debt_entry(
    session: Session,
    *,
    counterparty_id: int,
    debt_type: str,
    doc_type: str,
    doc_id: int,
    doc_number: str,
    doc_date: datetime,
    amount_tmt: Decimal,
    currency_id: int | None,
    amount_cur: Decimal | None,
    note: str | None,
    user_id: int | None,
) -> DebtLedger:
    """Append one debt ledger entry and snapshot the resulting balance."""

    amount = money(amount_tmt)
    balance_after = money(current_debt_balance(session, counterparty_id, debt_type) + amount)
    entry = DebtLedger(
        counterparty_id=counterparty_id,
        debt_type=debt_type,
        doc_type=doc_type,
        doc_id=doc_id,
        doc_number=doc_number,
        doc_date=doc_date,
        amount_tmt=amount,
        balance_after=balance_after,
        currency_id=currency_id,
        amount_cur=money(amount_cur) if amount_cur is not None else None,
        note=note,
        created_by_user_id=user_id,
    )
    session.add(entry)
    session.flush()
    return entry


def update_purchase_invoice_payment_status(session: Session, invoice: PurchaseInvoice) -> None:
    """Set unpaid/partial/paid according to posted allocations."""

    paid = (
        session.query(func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .filter(
            Payment.status == "posted",
            PaymentAllocation.doc_type == "purchase_invoice",
            PaymentAllocation.doc_id == invoice.id,
        )
        .scalar()
        or 0
    )
    paid_amount = money(paid)
    total = abs(money(invoice.total_amount_tmt))
    if paid_amount <= Decimal("0.00"):
        invoice.payment_status = "unpaid"
    elif paid_amount >= total:
        invoice.payment_status = "paid"
    else:
        invoice.payment_status = "partial"
