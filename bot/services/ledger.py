import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
from django.utils import timezone
from accounts.models import UserProfile
from payments.models import Ledger, TransactionAudit
from bmoni.views import process_pension_deposit
from bmoni.client import BMONIService
from ..models import WhatsAppPendingTransaction

logger = logging.getLogger(__name__)
bmoni_service = BMONIService()


def propose_money_movement(user: UserProfile, amount: Decimal, raw_transcript: str = "") -> str:
    """
    Step 1 of 2-Step Confirmation:
    Calculates 40/60 split, creates a pending transaction proposal, and asks the user for explicit confirmation.
    Money is NOT moved at this stage.
    """
    if amount < Decimal("50.00"):
        return "The minimum savings amount is ₦50. Please specify a higher amount."

    if amount > Decimal("1000000.00"):
        return "Amount exceeds micro-pension threshold. Please enter a smaller amount or contact support."

    # Cancel any previous unconfirmed proposals for this user
    WhatsAppPendingTransaction.objects.filter(
        user=user, status=WhatsAppPendingTransaction.Status.PENDING
    ).update(status=WhatsAppPendingTransaction.Status.CANCELLED)

    contingent = (amount * Decimal("0.40")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    retirement = amount - contingent

    expires_at = timezone.now() + timedelta(minutes=10)

    pending_tx = WhatsAppPendingTransaction.objects.create(
        user=user,
        phone_number=user.phone_number,
        intent="move_money",
        gross_amount=amount,
        contingent_amount=contingent,
        retirement_amount=retirement,
        raw_transcript=raw_transcript,
        expires_at=expires_at,
    )

    return (
        f"I understood: move ₦{amount:,.2f} into your BabaSika savings.\n\n"
        f"I'll split it:\n"
        f"• ₦{contingent:,.2f} → Contingent (Emergency Buffer)\n"
        f"• ₦{retirement:,.2f} → Retirement (Locked Pension)\n\n"
        f"Should I go ahead?\n"
        f"Reply YES to confirm or NO to cancel."
    )


def confirm_pending_transaction(user: UserProfile) -> str:
    """
    Step 2 of 2-Step Confirmation:
    Executed ONLY when the user explicitly replies YES/CONFIRM.
    Validates pending state and calls the authoritative BMONI transaction engine.
    """
    pending_tx = (
        WhatsAppPendingTransaction.objects.filter(
            user=user, status=WhatsAppPendingTransaction.Status.PENDING
        )
        .order_by("-created_at")
        .first()
    )

    if not pending_tx or not pending_tx.is_valid():
        return (
            "You don't have any active savings proposal waiting for confirmation. "
            "Type 'save 500 naira' to start a new savings move!"
        )

    try:
        # Call the SAME transaction engine as the website
        tx_record = process_pension_deposit(user, pending_tx.gross_amount)

        pending_tx.status = WhatsAppPendingTransaction.Status.CONFIRMED
        pending_tx.bmoni_tx_ref = f"{tx_record.bmoni_tx_id_1}|{tx_record.bmoni_tx_id_2}"
        pending_tx.save()

        return (
            f"Done! 🎉\n\n"
            f"₦{pending_tx.gross_amount:,.2f} has been moved successfully.\n\n"
            f"• ₦{pending_tx.contingent_amount:,.2f} → Contingent Emergency\n"
            f"• ₦{pending_tx.retirement_amount:,.2f} → Retirement Pension\n\n"
            f"Your BabaSika savings are growing!"
        )

    except Exception as e:
        logger.error(f"WhatsApp transaction confirmation failed for {user.phone_number}: {e}")
        return (
            "I couldn't complete that money move with BMONI right now. "
            "Your balance has NOT been changed. Please try again in a moment."
        )


def cancel_pending_transaction(user: UserProfile) -> str:
    """Cancels any active pending transaction proposal."""
    updated = WhatsAppPendingTransaction.objects.filter(
        user=user, status=WhatsAppPendingTransaction.Status.PENDING
    ).update(status=WhatsAppPendingTransaction.Status.CANCELLED)

    if updated:
        return "Understood. The proposed money move has been cancelled. Your balance was not changed."
    return "No pending proposal was found to cancel."


def get_balance_summary(user: UserProfile, filter_type: str = "ALL") -> str:
    """Queries live BMONI / local ledger balances and formats a concise response."""
    ledger, _ = Ledger.objects.get_or_create(profile=user)

    if filter_type == "CONTINGENT":
        return f"Your liquid Contingent Emergency balance is ₦{ledger.contingent_balance:,.2f}."
    elif filter_type == "RETIREMENT":
        return f"Your locked Retirement Pension balance is ₦{ledger.retirement_balance:,.2f}."

    total = ledger.contingent_balance + ledger.retirement_balance
    return (
        f"Your BabaSika Savings Balance:\n\n"
        f"• Emergency (Available): ₦{ledger.contingent_balance:,.2f}\n"
        f"• Retirement (Locked): ₦{ledger.retirement_balance:,.2f}\n"
        f"• Total: ₦{total:,.2f}"
    )


def get_transaction_history_summary(user: UserProfile) -> str:
    """Returns concise recent activity summary."""
    txns = TransactionAudit.objects.filter(user=user, status="SUCCESS")[:5]

    if not txns.exists():
        return "You have no recorded savings movements yet. Try saving ₦500 to get started!"

    lines = ["Your recent BabaSika activity:\n"]
    for t in txns:
        date_str = t.created_at.strftime("%b %d")
        lines.append(f"• ₦{t.gross_amount:,.2f} — {date_str} (40% Contingent / 60% Pension)")

    lines.append("\nYour savings are safe and earning returns!")
    return "\n".join(lines)
