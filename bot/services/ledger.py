"""The deterministic ledger & optimization controller from the PRD.

    AI  ->  {intent, amount, confidence}  ->  BabaSika backend
                                              -> validate
                                              -> 40/60 split
                                              -> BMONI transfer
                                              -> DB transaction

The AI/intent layer never calls BMONI and never touches a balance. This
module is the sole owner of both. Every deposit — whether triggered by a
voice note, typed message, transaction round-up, or end-of-day sweep —
must go through `process_deposit`.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction as db_transaction

from ..models import Transaction, User
from . import bmoni_client

MIN_DEPOSIT = Decimal("50")
MAX_DEPOSIT = Decimal("10000000")  # sanity ceiling; guards against garbled STT output


class LedgerValidationError(Exception):
    """Raised when an intent fails validation and must NOT move money."""


def _split(gross_amount: Decimal) -> tuple[Decimal, Decimal]:
    contingent = (gross_amount * Decimal(str(settings.CONTINGENT_SPLIT_PCT))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    retirement = gross_amount - contingent  # guarantees the two halves sum exactly to gross
    return contingent, retirement


def validate_deposit_intent(user: User, intent: dict) -> Decimal:
    """Raises LedgerValidationError on anything that shouldn't touch money."""
    if intent.get("intent") != "MAKE_DEPOSIT":
        raise LedgerValidationError("Not a deposit intent")

    if not user.is_onboarded:
        raise LedgerValidationError("User has not completed onboarding")

    amount = intent.get("amount")
    if amount is None:
        raise LedgerValidationError("No amount extracted")

    try:
        amount = Decimal(str(amount))
    except Exception as exc:
        raise LedgerValidationError("Amount is not numeric") from exc

    if amount < MIN_DEPOSIT or amount > MAX_DEPOSIT:
        raise LedgerValidationError(f"Amount ₦{amount} outside allowed range")

    confidence = intent.get("confidence", 0)
    if confidence < 0.5:
        raise LedgerValidationError("Confidence too low to act on automatically")

    return amount


@db_transaction.atomic
def process_deposit(
    user: User,
    intent: dict,
    source: str,
    raw_transcript: str = "",
) -> Transaction:
    """Validates the intent, computes the regulatory 40/60 split, moves the
    money via BMONI, and writes the audit trail. Returns the Transaction."""
    amount = validate_deposit_intent(user, intent)
    contingent_credit, retirement_credit = _split(amount)

    tx = Transaction.objects.create(
        user=user,
        gross_amount=amount,
        contingent_credit=contingent_credit,
        retirement_credit=retirement_credit,
        source=source,
        raw_transcript=raw_transcript,
        intent_confidence=intent.get("confidence"),
        status=Transaction.Status.PENDING,
    )

    try:
        contingent_ref = bmoni_client.transfer(user.contingent_wallet_id, contingent_credit)
        retirement_ref = bmoni_client.transfer(user.retirement_wallet_id, retirement_credit)
    except bmoni_client.BMONIError:
        tx.status = Transaction.Status.FAILED
        tx.save(update_fields=["status"])
        raise

    tx.bmoni_transfer_ref = f"{contingent_ref}|{retirement_ref}"
    tx.status = Transaction.Status.COMPLETE
    tx.save(update_fields=["bmoni_transfer_ref", "status"])

    user.contingent_balance += contingent_credit
    user.retirement_balance += retirement_credit
    user.save(update_fields=["contingent_balance", "retirement_balance"])

    return tx
