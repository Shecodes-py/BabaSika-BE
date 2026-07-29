import json
import logging
import time
from datetime import datetime
from decimal import Decimal

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from accounts.models import UserProfile
from monnify.client import MonnifyClient
from monnify.models import MonnifyApiLog
from payments.models import Transaction, Ledger, ReservedAccount

logger = logging.getLogger(__name__)


def process_monnify_payment(event_type, event_data):
    if event_type not in ('SUCCESSFUL_TRANSACTION', 'PAYMENT_MADE'):
        return {"status": "ignored", "message": f"Unhandled event type: {event_type}"}

    amount_paid = Decimal(str(event_data.get('amountPaid', 0)))
    payment_ref = event_data.get('paymentReference', '')
    account_ref = event_data.get('accountReference') or (event_data.get('product', {}) or {}).get('reference')

    if not account_ref:
        return {"status": "error", "message": "No account reference"}

    try:
        reserved_account = ReservedAccount.objects.get(account_reference=account_ref)
    except ReservedAccount.DoesNotExist:
        return {"status": "error", "message": f"Unknown account reference: {account_ref}"}

    profile = reserved_account.profile
    ledger, _ = Ledger.objects.get_or_create(profile=profile)

    if Transaction.objects.filter(monnify_payment_ref=payment_ref).exists():
        return {"status": "duplicate", "message": "Transaction already processed"}

    contingent_amount = (amount_paid * Decimal('0.40')).quantize(Decimal('0.01'))
    retirement_amount = (amount_paid * Decimal('0.60')).quantize(Decimal('0.01'))

    Transaction.objects.create(
        profile=profile, monnify_payment_ref=payment_ref,
        txn_type='deposit', wallet_type='contingent',
        amount=contingent_amount,
        description=f"40% contingent split from deposit of {amount_paid}",
        status='completed',
    )
    Transaction.objects.create(
        profile=profile, monnify_payment_ref=payment_ref,
        txn_type='deposit', wallet_type='retirement',
        amount=retirement_amount,
        description=f"60% retirement split from deposit of {amount_paid}",
        status='completed',
    )

    ledger.contingent_balance += contingent_amount
    ledger.retirement_balance += retirement_amount
    ledger.total_contributions += amount_paid
    ledger.save()

    if profile.pfa and retirement_amount > 0:
        client = MonnifyClient()
        transfer_ref = f"PFA-{profile.profile_id}-{payment_ref[:16]}"
        transfer_result = client.single_transfer(
            amount=retirement_amount,
            bank_code=profile.pfa.bank_code,
            account_number=profile.pfa.bank_account_number,
            account_name=profile.pfa.name,
            narration=f"BabaSika retirement transfer for {profile.full_name}",
            reference=transfer_ref,
        )

        Transaction.objects.create(
            profile=profile, monnify_payment_ref=payment_ref,
            txn_type='pfa_transfer', wallet_type='retirement',
            amount=retirement_amount,
            description=f"Transferred to PFA: {profile.pfa.name}",
            status='completed' if transfer_result.get('requestSuccessful') else 'failed',
        )

        if transfer_result.get('requestSuccessful'):
            ledger.retirement_balance -= retirement_amount
            ledger.save()

    return {"status": "success", "message": "Webhook processed"}


@api_view(['POST'])
@permission_classes([AllowAny])
def monnify_webhook(request):
    body = request.data
    logger.info(f"Monnify webhook received: {json.dumps(body, default=str)}")
    result = process_monnify_payment(body.get('eventType'), body.get('eventData', {}))
    status_code = status.HTTP_200_OK if result['status'] == 'success' else status.HTTP_400_BAD_REQUEST
    return Response(result, status=status_code)


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_payer(request):
    identifier = request.data.get('identifier')
    if not identifier:
        return Response(
            {"status": "error", "message": "identifier (phone or profile_id) required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    profile = UserProfile.objects.filter(
        phone_number=identifier
    ).first() or UserProfile.objects.filter(
        profile_id=identifier
    ).first()

    if not profile or not profile.is_active:
        return Response(
            {"status": "error", "message": "User not found or inactive"},
            status=status.HTTP_404_NOT_FOUND
        )

    account = ReservedAccount.objects.filter(profile=profile, is_active=True).first()

    return Response({
        "status": "success",
        "data": {
            "verified": True,
            "full_name": profile.full_name,
            "phone_number": profile.phone_number,
            "is_active": profile.is_active,
            "reserved_account": {
                "bank_name": account.bank_name,
                "account_number": account.account_number,
            } if account else None,
        }
    })


@api_view(['POST'])
def simulate_payment(request):
    profile_id = request.data.get('profile_id')
    amount = request.data.get('amount')

    if not profile_id or not amount:
        return Response(
            {"status": "error", "message": "profile_id and amount required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        profile = UserProfile.objects.get(profile_id=profile_id)
    except UserProfile.DoesNotExist:
        return Response(
            {"status": "error", "message": "Profile not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    account = ReservedAccount.objects.filter(profile=profile, is_active=True).first()
    if not account:
        return Response(
            {"status": "error", "message": "No reserved account for this user"},
            status=status.HTTP_400_BAD_REQUEST
        )

    event_data = {
        "amountPaid": float(amount),
        "paymentReference": f"SIM-{profile.profile_id}-{int(time.time())}",
        "accountReference": account.account_reference,
        "product": {"reference": account.account_reference},
        "paidOn": datetime.now().isoformat(),
        "paymentDescription": f"Test payment from {profile.full_name}",
        "paymentMethod": "CARD",
        "currency": "NGN",
        "customer": {
            "email": profile.email or f"{profile.phone_number}@babasika.com",
            "name": profile.full_name,
        },
    }

    result = process_monnify_payment('SUCCESSFUL_TRANSACTION', event_data)
    status_code = status.HTTP_200_OK if result['status'] == 'success' else status.HTTP_500_INTERNAL_SERVER_ERROR
    return Response(result, status=status_code)


@api_view(['GET'])
def api_log(request):
    logs = MonnifyApiLog.objects.all()[:50]
    data = [
        {
            "endpoint": log.endpoint,
            "method": log.method,
            "status_code": log.status_code,
            "success": log.success,
            "duration_ms": log.duration_ms,
            "request_body": log.request_body,
            "response_body": log.response_body,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
    return Response({"status": "success", "data": data})

