import uuid
import logging
from decimal import Decimal
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from accounts.models import UserProfile
from .models import Ledger, Transaction, TransactionAudit
from .serializers import LedgerSerializer, TransactionSerializer
from bmoni.views import bmoni_service

logger = logging.getLogger(__name__)


@api_view(['GET'])
def get_ledger(request, profile_id):
    try:
        profile = UserProfile.objects.get(profile_id=profile_id)
    except Exception:
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
    except Exception:
        return Response(
            {"status": "error", "message": "Profile not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    txns = Transaction.objects.filter(profile=profile)[:50]
    serializer = TransactionSerializer(txns, many=True)
    return Response({"status": "success", "data": serializer.data})


@api_view(['GET'])
def get_dashboard_data(request):
    profile_id = request.query_params.get('profile_id')
    user = None
    if profile_id:
        try:
            user = UserProfile.objects.get(profile_id=profile_id)
        except Exception:
            pass

    if user:
        ledger, _ = Ledger.objects.get_or_create(profile=user)
        contingent = float(ledger.contingent_balance)
        retirement = float(ledger.retirement_balance)
        total = float(ledger.total_contributions)
        txns = Transaction.objects.filter(profile=user)[:10]
        tx_data = [
            {
                "id": str(t.id),
                "type": t.txn_type,
                "amount": float(t.amount),
                "contingentAmount": float(t.amount) * 0.4,
                "retirementAmount": float(t.amount) * 0.6,
                "currency": "NGN",
                "description": t.description or "Pension contribution",
                "status": "SUCCESS",
                "createdAt": t.created_at.timestamp() * 1000 if hasattr(t, 'created_at') else 0
            }
            for t in txns
        ]
    else:
        contingent = 12500.0
        retirement = 18750.0
        total = 31250.0
        tx_data = [
            {
                "id": "txn_001",
                "type": "round_up",
                "amount": 500,
                "contingentAmount": 200,
                "retirementAmount": 300,
                "currency": "NGN",
                "description": "Market sale contribution",
                "status": "SUCCESS",
                "createdAt": 1722300000000
            },
            {
                "id": "txn_002",
                "type": "sweep",
                "amount": 1000,
                "contingentAmount": 400,
                "retirementAmount": 600,
                "currency": "NGN",
                "description": "Daily auto-sweep",
                "status": "SUCCESS",
                "createdAt": 1722200000000
            }
        ]

    return Response({
        "status": "success",
        "data": {
            "totalSaved": total,
            "contingentBalance": contingent,
            "retirementBalance": retirement,
            "contingentPercentage": 40,
            "retirementPercentage": 60,
            "growthPeriodDays": 90,
            "growthDaysElapsed": 45,
            "isContingentUnlocked": False,
            "transactions": tx_data
        }
    })


@api_view(['POST'])
def money_movement_split(request):
    profile_id = request.data.get('profile_id')
    amount_raw = request.data.get('amount')
    operation_id = request.data.get('operation_id') or f"babasika-move-{uuid.uuid4()}"

    if not amount_raw or float(amount_raw) <= 0:
        return Response(
            {"status": "error", "code": "INVALID_AMOUNT", "message": "Amount must be greater than zero."},
            status=status.HTTP_400_BAD_REQUEST
        )

    amount = Decimal(str(amount_raw))
    
    # Precise 40/60 integer split invariant
    contingent_credit = Decimal(int(amount * Decimal('0.40')))
    retirement_credit = amount - contingent_credit

    user = None
    if profile_id:
        try:
            user = UserProfile.objects.get(profile_id=profile_id)
        except Exception:
            pass

    # Optional BMONI live balance check if user exists
    if user and user.bmoni_user_id:
        try:
            bmoni_balances = bmoni_service.get_account_balances(user.bmoni_user_id)
            available = float(bmoni_balances.get('availableBalance', 1000000))
            if float(amount) > available:
                return Response(
                    {
                        "status": "error",
                        "code": "INSUFFICIENT_BALANCE",
                        "message": "You don't have enough available funds for this move."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            logger.warning(f"Could not verify BMONI balance for {user.bmoni_user_id}: {e}")

    # Process local transaction & BMONI transfer orchestration
    tx_audit = None
    if user:
        tx_audit = TransactionAudit.objects.create(
            user=user,
            gross_amount=amount,
            contingent_credit=contingent_credit,
            retirement_credit=retirement_credit,
            status='PROCESSING'
        )

        try:
            # Transfer to Contingent Smart Wallet
            if user.contingent_smart_wallet_id:
                res1 = bmoni_service.execute_transfer(user.bmoni_user_id, user.contingent_smart_wallet_id, contingent_credit)
                tx_audit.bmoni_tx_id_1 = str(res1.get('id', ''))
            
            # Transfer to Retirement Smart Wallet
            if user.retirement_smart_wallet_id:
                res2 = bmoni_service.execute_transfer(user.bmoni_user_id, user.retirement_smart_wallet_id, retirement_credit)
                tx_audit.bmoni_tx_id_2 = str(res2.get('id', ''))

            tx_audit.status = 'SUCCESS'
            tx_audit.save()

            ledger, _ = Ledger.objects.get_or_create(profile=user)
            ledger.contingent_balance += contingent_credit
            ledger.retirement_balance += retirement_credit
            ledger.total_contributions += amount
            ledger.save()

            Transaction.objects.create(
                profile=user,
                txn_type='deposit',
                amount=amount,
                description='BabaSika 40/60 pension split move'
            )
            
            new_contingent = float(ledger.contingent_balance)
            new_retirement = float(ledger.retirement_balance)
            new_total = float(ledger.total_contributions)
        except Exception as e:
            if tx_audit:
                tx_audit.status = 'FAILED'
                tx_audit.save()
            logger.error(f"Money movement failed: {e}")
            return Response(
                {"status": "error", "code": "TRANSFER_FAILED", "message": f"We couldn't complete the move. {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY
            )
    else:
        new_contingent = 12500.0 + float(contingent_credit)
        new_retirement = 18750.0 + float(retirement_credit)
        new_total = 31250.0 + float(amount)

    return Response({
        "status": "success",
        "message": f"Money moved successfully. ₦{int(contingent_credit):,} -> Contingent, ₦{int(retirement_credit):,} -> Retirement.",
        "data": {
            "success": True,
            "operationId": operation_id,
            "requestedAmount": float(amount),
            "contingentAmount": float(contingent_credit),
            "retirementAmount": float(retirement_credit),
            "totalSaved": new_total,
            "contingentBalance": new_contingent,
            "retirementBalance": new_retirement,
            "bmoniTxId": str(tx_audit.tx_id) if tx_audit else f"bmoni_{int(amount)}"
        }
    })


@api_view(['POST'])
def move_money(request):
    return money_movement_split(request)


@api_view(['POST'])
def money_movement_withdraw(request):
    from django.utils import timezone
    profile_id = request.data.get('profile_id')
    amount_raw = request.data.get('amount')
    force_override = request.data.get('force_override', False)

    if not amount_raw or float(amount_raw) <= 0:
        return Response(
            {"status": "error", "code": "INVALID_AMOUNT", "message": "Amount must be greater than zero."},
            status=status.HTTP_400_BAD_REQUEST
        )

    amount = Decimal(str(amount_raw))

    user = None
    if profile_id:
        try:
            user = UserProfile.objects.get(profile_id=profile_id)
        except Exception:
            pass

    if user:
        ledger, _ = Ledger.objects.get_or_create(profile=user)
        if ledger.contingent_balance < amount:
            return Response(
                {"status": "error", "code": "INSUFFICIENT_FUNDS", "message": f"Insufficient Contingent funds. Available: ₦{ledger.contingent_balance:,.2f}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 90-day cliff check (unless force_override is true for hackathon testing)
        days_elapsed = (timezone.now() - user.created_at).days if user.created_at else 0
        if days_elapsed < 90 and not force_override:
            return Response(
                {
                    "status": "error",
                    "code": "CLIFF_LOCKED",
                    "message": f"Your Contingent savings are in their 3-month growth period ({days_elapsed} of 90 days elapsed). Use Fast-Forward in Demo Mode to override.",
                    "daysElapsed": days_elapsed,
                    "daysRemaining": 90 - days_elapsed
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        ledger.contingent_balance -= amount
        ledger.save()

        Transaction.objects.create(
            profile=user,
            txn_type='withdrawal',
            amount=amount,
            description='Contingent emergency withdrawal'
        )

        if user.bmoni_user_id and user.contingent_smart_wallet_id:
            try:
                bmoni_service.execute_transfer(user.bmoni_user_id, user.contingent_smart_wallet_id, amount)
            except Exception as e:
                logger.warning(f"BMONI withdrawal execution warning: {e}")

        return Response({
            "status": "success",
            "message": f"Successfully withdrew ₦{int(amount):,} from Contingent wallet.",
            "data": {
                "success": True,
                "amount": float(amount),
                "remainingContingent": float(ledger.contingent_balance),
                "totalSaved": float(ledger.total_contributions)
            }
        })
    else:
        return Response({
            "status": "success",
            "message": f"Demo withdrawal of ₦{int(amount):,} successful.",
            "data": {
                "success": True,
                "amount": float(amount),
                "remainingContingent": max(0.0, 12500.0 - float(amount)),
                "totalSaved": max(0.0, 31250.0 - float(amount))
            }
        })