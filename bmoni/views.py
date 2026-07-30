import logging
from decimal import Decimal

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.models import PFA, UserProfile
from bmoni.client import BMONIService
from bmoni.serializers import (
    PensionDepositSerializer,
    UnifiedRegisterSerializer,
    VoiceInputSerializer,
)
from payments.models import Ledger, TransactionAudit

logger = logging.getLogger(__name__)

bmoni_service = BMONIService()


def process_pension_deposit(user, gross_amount):
    contingent_amount = gross_amount * Decimal('0.40')
    retirement_amount = gross_amount * Decimal('0.60')

    tx_record = TransactionAudit.objects.create(
        user=user,
        gross_amount=gross_amount,
        contingent_credit=contingent_amount,
        retirement_credit=retirement_amount,
        status='PROCESSING',
    )

    try:
        res1 = bmoni_service.execute_transfer(
            user.bmoni_user_id,
            user.contingent_smart_wallet_id,
            contingent_amount,
        )

        res2 = bmoni_service.execute_transfer(
            user.bmoni_user_id,
            user.retirement_smart_wallet_id,
            retirement_amount,
        )

        tx_record.bmoni_tx_id_1 = str(res1.get('id', ''))
        tx_record.bmoni_tx_id_2 = str(res2.get('id', ''))
        tx_record.status = 'SUCCESS'
        tx_record.save()

        ledger, _ = Ledger.objects.get_or_create(profile=user)
        ledger.contingent_balance += contingent_amount
        ledger.retirement_balance += retirement_amount
        ledger.total_contributions += gross_amount
        ledger.save()

        return tx_record

    except Exception as e:
        tx_record.status = 'FAILED'
        tx_record.save()
        logger.error(f"Pension deposit failed for user {user.profile_id}: {e}")
        raise


@api_view(['POST'])
def unified_register(request):
    serializer = UnifiedRegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {'status': 'error', 'message': 'Validation failed', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    data = serializer.validated_data

    if UserProfile.objects.filter(phone_number=data['phone_number']).exists():
        return Response(
            {'status': 'error', 'message': 'Phone number already registered'},
            status=status.HTTP_409_CONFLICT,
        )

    if not bmoni_service.api_key:
        return Response(
            {'status': 'error', 'message': 'BMONI API key not configured. Set BMONI_API_KEY in .env'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    pfa = None
    if pfa_id := data.get('pfa_id'):
        pfa = PFA.objects.filter(id=pfa_id, is_active=True).first()

    bvn = data.get('bvn') or '22222222222'

    try:
        with transaction.atomic():
            user = UserProfile.objects.create(
                full_name=data['full_name'],
                phone_number=data['phone_number'],
                email=data.get('email', ''),
                preferred_language=data.get('preferred_language', 'en'),
                pfa=pfa,
                onboarding_status='PROCESSING',
            )

            bmoni_user_id = bmoni_service.create_user(
                first_name=user.full_name.split()[0],
                email=user.email or f'{user.phone_number}@babasika.com',
                phone_number=user.phone_number,
            )
            user.bmoni_user_id = bmoni_user_id
            user.onboarding_status = 'USER_CREATED'
            user.save()

            contingent_wallet = bmoni_service.provision_smart_wallet(bmoni_user_id, 'CNGN')
            user.contingent_smart_wallet_id = contingent_wallet['smartWalletId']
            user.contingent_wallet_address = contingent_wallet['smartWalletAddress']
            user.onboarding_status = 'WALLETS_PROVISIONED'
            user.save()

            retirement_wallet = bmoni_service.provision_smart_wallet(bmoni_user_id, 'CNGN')
            user.retirement_smart_wallet_id = retirement_wallet['smartWalletId']
            user.retirement_wallet_address = retirement_wallet['smartWalletAddress']
            user.save()

            bmoni_service.complete_sandbox_kyc_and_activate_rail(
                bmoni_user_id,
                contingent_wallet['smartWalletAddress'],
            )
            user.onboarding_status = 'ACTIVE'
            user.save()

        return Response(
            {
                'status': 'success',
                'message': 'Account, BMONI smart wallets, and KYC completed successfully.',
                'data': {
                    'profile_id': str(user.profile_id),
                    'full_name': user.full_name,
                    'phone_number': user.phone_number,
                    'bmoni_user_id': bmoni_user_id,
                    'contingent_wallet_id': contingent_wallet['smartWalletId'],
                    'contingent_wallet_address': contingent_wallet['smartWalletAddress'],
                    'retirement_wallet_id': retirement_wallet['smartWalletId'],
                    'retirement_wallet_address': retirement_wallet['smartWalletAddress'],
                    'onboarding_status': user.onboarding_status,
                    'pfa': {'id': pfa.id, 'name': pfa.name} if pfa else None,
                },
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        logger.error(f"Unified registration failed: {e}")
        return Response(
            {'status': 'error', 'message': f'Registration failed during execution: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )


@api_view(['POST'])
def deposit_pension(request):
    serializer = PensionDepositSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {'status': 'error', 'message': 'Validation failed', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = UserProfile.objects.get(profile_id=serializer.validated_data['profile_id'])
    except UserProfile.DoesNotExist:
        return Response(
            {'status': 'error', 'message': 'Profile not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if user.onboarding_status != 'ACTIVE':
        return Response(
            {'status': 'error', 'message': 'User onboarding not complete. Please onboard first.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    gross_amount = serializer.validated_data['gross_amount']

    try:
        tx_record = process_pension_deposit(user, gross_amount)

        return Response(
            {
                'status': 'success',
                'message': (
                    f"Received ₦{int(gross_amount)}! "
                    f"₦{int(tx_record.contingent_credit)} (40%) added to your liquid emergency balance, "
                    f"and ₦{int(tx_record.retirement_credit)} (60%) locked in your retirement pension."
                ),
                'data': {
                    'tx_id': str(tx_record.tx_id),
                    'gross_amount': str(tx_record.gross_amount),
                    'contingent_credit': str(tx_record.contingent_credit),
                    'retirement_credit': str(tx_record.retirement_credit),
                    'bmoni_tx_id_1': tx_record.bmoni_tx_id_1,
                    'bmoni_tx_id_2': tx_record.bmoni_tx_id_2,
                    'status': tx_record.status,
                },
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {'status': 'error', 'message': f'Deposit failed: {str(e)}'},
            status=status.HTTP_502_BAD_GATEWAY,
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def voice_webhook(request):
    serializer = VoiceInputSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {'status': 'error', 'message': 'Validation failed', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    data = serializer.validated_data
    raw_text = data.get('raw_text', '')
    audio_url = data.get('audio_url', '')

    if not raw_text and not audio_url:
        return Response(
            {'status': 'error', 'message': 'Either raw_text or audio_url is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = UserProfile.objects.get(profile_id=data['profile_id'])
    except UserProfile.DoesNotExist:
        return Response(
            {'status': 'error', 'message': 'Profile not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    intent_data = _extract_intent(raw_text, audio_url)

    if intent_data.get('intent') != 'DEPOSIT':
        return Response(
            {
                'status': 'success',
                'message': f"Intent '{intent_data.get('intent')}' recognized, but only DEPOSIT is supported currently.",
                'data': intent_data,
            }
        )

    gross_amount = Decimal(str(intent_data['gross_amount']))

    if user.onboarding_status != 'ACTIVE':
        return Response(
            {'status': 'error', 'message': 'User not fully onboarded. Please complete BMONI onboarding first.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        tx_record = process_pension_deposit(user, gross_amount)

        return Response(
            {
                'status': 'success',
                'message': (
                    f"Received ₦{int(gross_amount)}! "
                    f"₦{int(tx_record.contingent_credit)} (40%) added to your liquid emergency balance, "
                    f"and ₦{int(tx_record.retirement_credit)} (60%) locked in your retirement pension."
                ),
                'data': {
                    'tx_id': str(tx_record.tx_id),
                    'intent': intent_data,
                    'gross_amount': str(tx_record.gross_amount),
                    'contingent_credit': str(tx_record.contingent_credit),
                    'retirement_credit': str(tx_record.retirement_credit),
                    'status': tx_record.status,
                },
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {'status': 'error', 'message': f'Voice deposit failed: {str(e)}'},
            status=status.HTTP_502_BAD_GATEWAY,
        )


def _extract_intent(raw_text, audio_url=None):
    if not raw_text:
        intent_data = {
            'intent': 'UNKNOWN',
            'gross_amount': 0,
            'raw_text': '',
        }
        return intent_data

    normalized = raw_text.lower()
    words = normalized.split()
    amount = 0

    for i, word in enumerate(words):
        try:
            amount = int(word.replace(',', ''))
            break
        except ValueError:
            continue

    has_deposit_keywords = any(
        kw in normalized for kw in ['keep', 'save', 'deposit', 'put', 'add', 'pension']
    )

    if amount > 0 and has_deposit_keywords:
        intent = 'DEPOSIT'
    elif amount > 0:
        intent = 'DEPOSIT'
    else:
        intent = 'UNKNOWN'

    return {
        'intent': intent,
        'gross_amount': amount,
        'raw_text': raw_text,
    }


@api_view(['GET'])
def api_log(request):
    from .models import BmoniApiLog
    logs = BmoniApiLog.objects.all()[:50]
    data = [
        {
            'endpoint': log.endpoint,
            'method': log.method,
            'status_code': log.status_code,
            'success': log.success,
            'duration_ms': log.duration_ms,
            'request_body': log.request_body,
            'response_body': log.response_body,
            'created_at': log.created_at.isoformat(),
        }
        for log in logs
    ]
    return Response({'status': 'success', 'data': data})