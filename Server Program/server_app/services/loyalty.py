"""Shared loyalty-program posting helpers."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from server_app.db.models import LoyaltyCard, LoyaltySetting, LoyaltyTransaction
from server_app.services.settlements import money


class LoyaltyBusinessError(RuntimeError):
    """Raised when a loyalty operation violates business rules."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def get_loyalty_settings(session: Session) -> LoyaltySetting:
    """Return the singleton loyalty settings row, creating defaults when absent."""

    row = session.query(LoyaltySetting).order_by(LoyaltySetting.id).first()
    if row is None:
        row = LoyaltySetting(earn_rate_percent=Decimal("0"), redemption_limit_percent=Decimal("100"), is_active=True)
        session.add(row)
        session.flush()
    return row


def post_loyalty_transaction(
    session: Session,
    card: LoyaltyCard,
    *,
    transaction_type: str,
    amount_tmt: Decimal,
    doc_type: str | None,
    doc_id: int | None,
    note: str | None,
    user_id: int | None,
) -> LoyaltyTransaction:
    """Append one bonus movement and update the card balance."""

    if not card.is_active:
        raise LoyaltyBusinessError("INACTIVE_LOYALTY_CARD", "Loyalty card is inactive.")
    amount = money(amount_tmt)
    new_balance = money(card.balance_tmt + amount)
    if new_balance < Decimal("0.00"):
        raise LoyaltyBusinessError("INSUFFICIENT_BONUS", "Loyalty card balance is insufficient.")
    card.balance_tmt = new_balance
    transaction = LoyaltyTransaction(
        loyalty_card_id=card.id,
        transaction_type=transaction_type,
        doc_type=doc_type,
        doc_id=doc_id,
        amount_tmt=amount,
        balance_after=new_balance,
        note=note,
        created_by_user_id=user_id,
    )
    session.add(transaction)
    session.flush()
    return transaction


def loyalty_transaction_total(
    session: Session,
    *,
    doc_type: str,
    doc_id: int,
    transaction_type: str | None = None,
) -> Decimal:
    """Return the signed total of loyalty movements for a document."""

    query = session.query(func.coalesce(func.sum(LoyaltyTransaction.amount_tmt), 0)).filter(
        LoyaltyTransaction.doc_type == doc_type,
        LoyaltyTransaction.doc_id == doc_id,
    )
    if transaction_type is not None:
        query = query.filter(LoyaltyTransaction.transaction_type == transaction_type)
    return money(query.scalar() or 0)


def reverse_loyalty_document(
    session: Session,
    card: LoyaltyCard,
    *,
    doc_type: str,
    doc_id: int,
    transaction_type: str,
    note: str,
    user_id: int | None,
) -> LoyaltyTransaction | None:
    """Post a balancing movement for all loyalty rows linked to one document."""

    total = loyalty_transaction_total(session, doc_type=doc_type, doc_id=doc_id)
    if total == Decimal("0.00"):
        return None
    return post_loyalty_transaction(
        session,
        card,
        transaction_type=transaction_type,
        amount_tmt=-total,
        doc_type=doc_type,
        doc_id=doc_id,
        note=note,
        user_id=user_id,
    )
