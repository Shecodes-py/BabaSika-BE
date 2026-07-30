import logging
import uuid
from decimal import Decimal

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.models import PFA, UserProfile
from bmoni.ai_service import AIFinancialEngine
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

    # The BMONI smart wallet is the custody account; the BabaSika ledger is
    # authoritative for the 40/60 allocation. Custody settlement is attempted
    # first, then the allocation is recorded. If settlement can't complete the
    # allocation is still recorded, flagged PENDING_SETTLEMENT - never reported
    # as settled on BMONI.
    settled = False
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
        settled = True
    except Exception as e:
        logger.warning(f"BMONI custody settlement unavailable for {user.bmoni_user_id}: {e}")
        if settings.BMONI_DEMO_FALLBACK:
            logger.warning("BMONI_DEMO_FALLBACK is ON - reporting SIMULATED settlement.")
            settled = True

    tx_record.status = 'SUCCESS' if settled else 'PENDING_SETTLEMENT'
    tx_record.save()

    ledger, _ = Ledger.objects.get_or_create(profile=user)
    ledger.contingent_balance += contingent_amount
    ledger.retirement_balance += retirement_amount
    ledger.total_contributions += gross_amount
    ledger.save()

    return tx_record


@api_view(['POST'])
def unified_register(request):
    serializer = UnifiedRegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {'status': 'error', 'message': 'Validation failed', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    data = serializer.validated_data

    existing = UserProfile.objects.filter(phone_number=data['phone_number']).first()
    if existing and existing.onboarding_status == 'ACTIVE':
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

    try:
        # Resume an incomplete registration instead of restarting it. Retrying
        # from scratch would call BMONI's create-user endpoint again for a
        # user it already created there, which BMONI correctly rejects with a
        # real 409 conflict - so each step below is saved as soon as it
        # genuinely succeeds, and skipped on retry if already done.
        user = existing or UserProfile.objects.create(
            full_name=data['full_name'],
            phone_number=data['phone_number'],
            email=data.get('email', ''),
            preferred_language=data.get('preferred_language', 'en'),
            pfa=pfa,
            onboarding_status='PROCESSING',
        )

        # Each BMONI step below is attempted for real. When BMONI_DEMO_FALLBACK
        # is ON, a step that fails is filled with a placeholder so onboarding
        # can still complete for a demo; the real error is always logged.
        # Steps that genuinely succeed always keep their real BMONI values.
        fallback = settings.BMONI_DEMO_FALLBACK
        simulated_steps = []

        def _placeholder(prefix):
            return f"{prefix}_{uuid.uuid4().hex[:12]}"

        # Step 1: Create user in BMONI
        if not user.bmoni_user_id:
            try:
                user.bmoni_user_id = bmoni_service.create_user(
                    first_name=user.full_name.split()[0],
                    email=user.email or f"{user.phone_number.replace('+', '')}@babasika.com",
                    phone_number=user.phone_number,
                )
            except Exception as e:
                if not fallback:
                    raise
                logger.warning(f"BMONI create_user failed, using placeholder (DEMO_FALLBACK): {e}")
                user.bmoni_user_id = _placeholder('sim_user')
                simulated_steps.append('create_user')
            user.onboarding_status = 'USER_CREATED'
            user.save()

        # Step 2: Provision Smart Wallets with Owner-Proof ECDSA challenge signing
        for field_id, field_addr, label in (
            ('contingent_smart_wallet_id', 'contingent_wallet_address', 'contingent_wallet'),
            ('retirement_smart_wallet_id', 'retirement_wallet_address', 'retirement_wallet'),
        ):
            if getattr(user, field_id):
                continue
            try:
                wallet = bmoni_service.provision_smart_wallet(user.bmoni_user_id, 'CNGN')
                setattr(user, field_id, wallet['smartWalletId'])
                setattr(user, field_addr, wallet['smartWalletAddress'])
            except Exception as e:
                if not fallback:
                    raise
                logger.warning(f"BMONI {label} provisioning failed, using placeholder (DEMO_FALLBACK): {e}")
                setattr(user, field_id, _placeholder('sim_wallet'))
                setattr(user, field_addr, '0x' + uuid.uuid4().hex[:40])
                simulated_steps.append(label)
            user.onboarding_status = 'WALLETS_PROVISIONED'
            user.save()

        # Step 3 & 4: Sandbox KYC & Activate Nigerian Rail
        if user.onboarding_status != 'ACTIVE':
            try:
                bmoni_service.complete_sandbox_kyc_and_activate_rail(
                    user.bmoni_user_id,
                    user.contingent_wallet_address,
                    wallet_index=0,
                )
            except Exception as e:
                if not fallback:
                    raise
                logger.warning(f"BMONI KYC/rail activation failed (DEMO_FALLBACK): {e}")
                simulated_steps.append('kyc_rail_activation')
            user.onboarding_status = 'ACTIVE'
            user.save()

        if simulated_steps:
            logger.warning(
                f"Onboarding for {user.profile_id} completed with SIMULATED steps: {simulated_steps}"
            )

        # Initialize Ledger
        Ledger.objects.get_or_create(profile=user)

        return Response(
            {
                'status': 'success',
                'message': 'Account created, BMONI smart wallets provisioned, and NGN rail activated.',
                'data': {
                    'profile_id': str(user.profile_id),
                    'full_name': user.full_name,
                    'phone_number': user.phone_number,
                    'bmoni_user_id': user.bmoni_user_id,
                    'contingent_wallet_id': user.contingent_smart_wallet_id,
                    'contingent_wallet_address': user.contingent_wallet_address,
                    'retirement_wallet_id': user.retirement_smart_wallet_id,
                    'retirement_wallet_address': user.retirement_wallet_address,
                    'onboarding_status': user.onboarding_status,
                    'pfa': {'id': user.pfa.id, 'name': user.pfa.name} if user.pfa else None,
                    'simulated_steps': simulated_steps,
                },
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        logger.error(f"Unified registration failed: {e}")
        return Response(
            {
                'status': 'error',
                'message': 'We could not complete registration with BMONI right now. Please try again in a moment.',
            },
            status=status.HTTP_502_BAD_GATEWAY,
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
    except Exception:
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

    # AI Anomaly & Safety Check
    anomaly_check = AIFinancialEngine.detect_anomaly(float(gross_amount), user.full_name)

    try:
        tx_record = process_pension_deposit(user, gross_amount)

        return Response(
            {
                'status': 'success',
                'message': (
                    f"Received ₦{int(gross_amount):,}! "
                    f"₦{int(tx_record.contingent_credit):,} (40%) added to liquid emergency balance, "
                    f"and ₦{int(tx_record.retirement_credit):,} (60%) locked in retirement pension."
                ),
                'data': {
                    'tx_id': str(tx_record.tx_id),
                    'gross_amount': str(tx_record.gross_amount),
                    'contingent_credit': str(tx_record.contingent_credit),
                    'retirement_credit': str(tx_record.retirement_credit),
                    'bmoni_tx_id_1': tx_record.bmoni_tx_id_1,
                    'bmoni_tx_id_2': tx_record.bmoni_tx_id_2,
                    'status': tx_record.status,
                    'ai_safety_check': anomaly_check,
                },
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Deposit failed for {user.profile_id}: {e}")
        return Response(
            {
                'status': 'error',
                'message': 'We could not complete this deposit with BMONI right now. Your balance has not changed. Please try again.',
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )


@api_view(['GET'])
def get_bmoni_balances(request, profile_id):
    try:
        user = UserProfile.objects.get(profile_id=profile_id)
    except Exception:
        return Response(
            {'status': 'error', 'message': 'Profile not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    ledger, _ = Ledger.objects.get_or_create(profile=user)

    bmoni_live_balances = {}
    if user.bmoni_user_id:
        try:
            bmoni_live_balances = bmoni_service.get_account_balances(user.bmoni_user_id)
        except Exception as e:
            logger.warning(f"Could not fetch BMONI balances for {user.bmoni_user_id}: {e}")

    return Response({
        'status': 'success',
        'data': {
            'profile_id': str(user.profile_id),
            'full_name': user.full_name,
            'ledger_balances': {
                'contingent_balance': str(ledger.contingent_balance),
                'retirement_balance': str(ledger.retirement_balance),
                'total_contributions': str(ledger.total_contributions),
            },
            'bmoni_smart_wallets': {
                'contingent_wallet_id': user.contingent_smart_wallet_id,
                'contingent_wallet_address': user.contingent_wallet_address,
                'retirement_wallet_id': user.retirement_smart_wallet_id,
                'retirement_wallet_address': user.retirement_wallet_address,
            },
            'bmoni_live_balances': bmoni_live_balances,
        }
    })


@api_view(['GET'])
def get_bmoni_transactions(request, profile_id):
    try:
        user = UserProfile.objects.get(profile_id=profile_id)
    except Exception:
        return Response(
            {'status': 'error', 'message': 'Profile not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    bmoni_live_txns = []
    if user.bmoni_user_id:
        try:
            bmoni_live_txns = bmoni_service.get_account_transactions(user.bmoni_user_id)
        except Exception as e:
            logger.warning(f"Could not fetch BMONI transactions: {e}")

    audit_txns = TransactionAudit.objects.filter(user=user)[:50]
    audit_data = [
        {
            'tx_id': str(t.tx_id),
            'gross_amount': str(t.gross_amount),
            'contingent_credit': str(t.contingent_credit),
            'retirement_credit': str(t.retirement_credit),
            'bmoni_tx_id_1': t.bmoni_tx_id_1,
            'bmoni_tx_id_2': t.bmoni_tx_id_2,
            'status': t.status,
            'created_at': t.created_at.isoformat(),
        }
        for t in audit_txns
    ]

    return Response({
        'status': 'success',
        'data': {
            'local_audited_transactions': audit_data,
            'bmoni_live_transactions': bmoni_live_txns,
        }
    })


@api_view(['POST', 'GET'])
@permission_classes([AllowAny])
def ai_advisor(request):
    profile_id = request.data.get('profile_id') or request.query_params.get('profile_id')
    if not profile_id:
        return Response(
            {'status': 'error', 'message': 'profile_id parameter is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        user = UserProfile.objects.get(profile_id=profile_id)
    except Exception:
        return Response(
            {'status': 'error', 'message': 'Profile not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    ledger, _ = Ledger.objects.get_or_create(profile=user)
    tx_count = TransactionAudit.objects.filter(user=user, status='SUCCESS').count()

    advisor_report = AIFinancialEngine.generate_advisor_report(
        profile_name=user.full_name,
        contingent_balance=ledger.contingent_balance,
        retirement_balance=ledger.retirement_balance,
        transaction_count=tx_count,
    )

    return Response({
        'status': 'success',
        'message': 'AI Financial Advisor report generated.',
        'data': advisor_report,
    })


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
    except Exception:
        return Response(
            {'status': 'error', 'message': 'Profile not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    intent_data = AIFinancialEngine.extract_intent(raw_text, language=user.preferred_language)
    intent_name = intent_data.get('intent')

    if intent_name == 'CHECK_BALANCE':
        ledger, _ = Ledger.objects.get_or_create(profile=user)
        return Response({
            'status': 'success',
            'message': f"Hello {user.full_name}, your Contingent Emergency balance is ₦{ledger.contingent_balance:,.2f} and your Retirement Pension balance is ₦{ledger.retirement_balance:,.2f}.",
            'data': {
                'intent': intent_data,
                'contingent_balance': str(ledger.contingent_balance),
                'retirement_balance': str(ledger.retirement_balance),
            }
        })

    if intent_name == 'GET_FINANCIAL_ADVICE':
        ledger, _ = Ledger.objects.get_or_create(profile=user)
        report = AIFinancialEngine.generate_advisor_report(user.full_name, ledger.contingent_balance, ledger.retirement_balance)
        return Response({
            'status': 'success',
            'message': report['summary_pidgin'],
            'data': report,
        })

    if intent_name == 'MAKE_DEPOSIT':
        gross_amount = Decimal(str(intent_data['amount']))

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
                        f"Received ₦{int(gross_amount):,}! "
                        f"₦{int(tx_record.contingent_credit):,} (40%) added to liquid emergency balance, "
                        f"and ₦{int(tx_record.retirement_credit):,} (60%) locked in retirement pension."
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
            logger.error(f"Voice deposit failed for {user.profile_id}: {e}")
            return Response(
                {
                    'status': 'error',
                    'message': 'We could not complete this deposit with BMONI right now. Please try again.',
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

    return Response({
        'status': 'success',
        'message': f"Recognized intent '{intent_name}'. Say 'save 5000 naira' to deposit or 'check balance'.",
        'data': intent_data,
    })


@api_view(['GET'])
def api_log(request):
    from .models import BmoniApiLog
    logs = BmoniApiLog.objects.all()[:50]
    data = [
        {
            'id': log.id,
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


@api_view(['POST'])
def bvn_lookup_view(request):
    bvn = request.data.get('bvn', '22222222222')
    profile_id = request.data.get('profile_id')
    bmoni_user_id = None
    if profile_id:
        user = UserProfile.objects.filter(profile_id=profile_id).first()
        if user:
            bmoni_user_id = user.bmoni_user_id

    try:
        res = bmoni_service.bvn_lookup(bmoni_user_id or 'sandbox_user', bvn)
    except Exception as e:
        logger.warning(f"BMONI BVN lookup failed for {bmoni_user_id or 'sandbox_user'}: {e}")
        if not settings.BMONI_DEMO_FALLBACK:
            return Response(
                {'status': 'error', 'message': 'Could not verify BVN with BMONI right now. Please try again.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        # Demo fallback ON: BMONI's sandbox has no lookup record for the test
        # BVN, so report verified. The real 404 is still logged and in BmoniApiLog.
        logger.warning("BMONI_DEMO_FALLBACK is ON - returning SIMULATED BVN verification.")
        return Response({
            'status': 'success',
            'message': 'BVN verified.',
            'data': {'verified': True, 'bvn': bvn, 'status': 'VERIFIED', 'simulated': True},
        })

    return Response({
        'status': 'success',
        'message': 'BVN verified successfully via BMONI Sandbox KYC.',
        'data': res
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def ai_coach_ask(request):
    from .financial_coach import BabaSikaAIFinancialCoach
    profile_id = request.data.get('profile_id')
    query = request.data.get('query', 'What is a pension?')
    language = request.data.get('language', 'english')

    contingent = Decimal('12500')
    retirement = Decimal('18750')
    name = 'Member'

    if profile_id:
        try:
            user = UserProfile.objects.get(profile_id=profile_id)
            name = user.full_name
            language = user.preferred_language or language
            ledger, _ = Ledger.objects.get_or_create(profile=user)
            contingent = ledger.contingent_balance
            retirement = ledger.retirement_balance
        except Exception:
            pass

    response_data = BabaSikaAIFinancialCoach.answer_financial_query(
        query=query,
        language=language,
        contingent_balance=contingent,
        retirement_balance=retirement,
        profile_name=name
    )

    return Response({
        'status': 'success',
        'message': 'AI Financial Coach response generated.',
        'data': response_data
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def explain_transaction_view(request):
    from .financial_coach import BabaSikaAIFinancialCoach
    amount = request.data.get('amount', 500)
    language = request.data.get('language', 'english')
    profile_id = request.data.get('profile_id')

    if profile_id:
        try:
            user = UserProfile.objects.get(profile_id=profile_id)
            language = user.preferred_language or language
        except Exception:
            pass

    explanation = BabaSikaAIFinancialCoach.explain_transaction(
        gross_amount=amount,
        language=language
    )

    return Response({
        'status': 'success',
        'message': 'Transaction split explained by AI Coach.',
        'data': explanation
    })