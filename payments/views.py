from decimal import Decimal

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from accounts.models import UserProfile
from .models import Ledger, Transaction
from .serializers import LedgerSerializer, TransactionSerializer


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