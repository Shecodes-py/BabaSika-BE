from decimal import Decimal

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from accounts.models import UserProfile
from monnify.client import MonnifyClient
from .models import Ledger, Transaction, ReservedAccount
from .serializers import LedgerSerializer, TransactionSerializer, ReservedAccountSerializer


@api_view(['GET'])
def get_ledger(request, profile_id):
    try:
        profile = UserProfile.objects.get(profile_id=profile_id)
    except UserProfile.DoesNotExist:
        return Response(
            {"status": "error", "message": "Profile not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    ledger, _ = Ledger.objects.get_or_create(profile=profile)
    serializer = LedgerSerializer(ledger)
    return Response({"status": "success", "data": serializer.data})


@api_view(['GET'])
def get_transactions(request, profile_id):
    try:
        profile = UserProfile.objects.get(profile_id=profile_id)
    except UserProfile.DoesNotExist:
        return Response(
            {"status": "error", "message": "Profile not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    txns = Transaction.objects.filter(profile=profile)[:50]
    serializer = TransactionSerializer(txns, many=True)
    return Response({"status": "success", "data": serializer.data})


@api_view(['GET'])
def get_reserved_account(request, profile_id):
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
            {"status": "error", "message": "No reserved account found"},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = ReservedAccountSerializer(account)
    return Response({"status": "success", "data": serializer.data})


@api_view(['POST'])
def withdraw_emergency(request):
    profile_id = request.data.get('profile_id')
    amount = request.data.get('amount')
    bank_code = request.data.get('bank_code')
    account_number = request.data.get('account_number')
    account_name = request.data.get('account_name')

    if not all([profile_id, amount, bank_code, account_number, account_name]):
        return Response(
            {"status": "error", "message": "profile_id, amount, bank_code, account_number, and account_name are required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        profile = UserProfile.objects.get(profile_id=profile_id)
    except UserProfile.DoesNotExist:
        return Response(
            {"status": "error", "message": "Profile not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    ledger, _ = Ledger.objects.get_or_create(profile=profile)
    withdraw_amount = Decimal(str(amount))

    if withdraw_amount <= 0:
        return Response(
            {"status": "error", "message": "Amount must be greater than 0"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if withdraw_amount > ledger.contingent_balance:
        return Response(
            {
                "status": "error",
                "message": f"Insufficient emergency balance. Available: ₦{ledger.contingent_balance}, Requested: ₦{withdraw_amount}",
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    client = MonnifyClient()
    reference = f"WTH-{profile.profile_id}-{int(__import__('time').time())}"
    result = client.single_transfer(
        amount=withdraw_amount,
        bank_code=bank_code,
        account_number=account_number,
        account_name=account_name,
        narration=f"BabaSika emergency withdrawal for {profile.full_name}",
        reference=reference,
    )

    if not result.get('requestSuccessful'):
        return Response(
            {
                "status": "error",
                "message": result.get('responseMessage', 'Monnify transfer failed'),
                "monnify_response": result,
            },
            status=status.HTTP_502_BAD_GATEWAY
        )

    ledger.contingent_balance -= withdraw_amount
    ledger.save()

    Transaction.objects.create(
        profile=profile,
        transaction_ref=reference,
        txn_type='withdrawal',
        wallet_type='contingent',
        amount=withdraw_amount,
        description=f"Emergency withdrawal to {account_name} ({account_number})",
        status='completed',
    )

    return Response({
        "status": "success",
        "message": f"₦{withdraw_amount} disbursed to {account_name}",
        "data": {
            "reference": reference,
            "amount": str(withdraw_amount),
            "new_balance": str(ledger.contingent_balance),
            "destination": {
                "bank_code": bank_code,
                "account_number": account_number,
                "account_name": account_name,
            },
            "monnify_response": result,
        }
    })
