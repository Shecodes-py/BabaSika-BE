from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import UserProfile, PFA
from .serializers import OnboardUserSerializer, UserProfileSerializer, PFASerializer
from payments.models import ReservedAccount
from monnify.client import MonnifyClient


@api_view(['GET'])
def list_pfas(request):
    pfas = PFA.objects.filter(is_active=True)
    serializer = PFASerializer(pfas, many=True)
    return Response({"status": "success", "data": serializer.data})


@api_view(['POST'])
def onboard_user(request):
    serializer = OnboardUserSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"status": "error", "message": "Validation failed", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    data = serializer.validated_data

    if UserProfile.objects.filter(phone_number=data['phone_number']).exists():
        return Response(
            {"status": "error", "message": "Phone number already registered"},
            status=status.HTTP_409_CONFLICT
        )

    pfa = None
    if pfa_id := data.get('pfa_id'):
        pfa = PFA.objects.filter(id=pfa_id, is_active=True).first()

    profile = UserProfile.objects.create(
        full_name=data['full_name'],
        phone_number=data['phone_number'],
        preferred_language=data.get('preferred_language', 'en'),
        pfa=pfa
    )

    client = MonnifyClient()
    has_creds = bool(client.api_key and client.secret and client.contract_code)

    if not has_creds:
        return Response(
            {
                "status": "error",
                "message": "Monnify API credentials not configured. Set MONNIFY_API_KEY, MONNIFY_SECRET, and MONNIFY_CONTRACT_CODE in .env",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    result = client.create_reserved_account(profile)

    if not result or result.get('status') != 'success':
        return Response(
            {
                "status": "error",
                "message": result.get('message', 'Monnify API call failed'),
                "monnify_response": result,
            },
            status=status.HTTP_502_BAD_GATEWAY
        )

    profile_data = UserProfileSerializer(profile).data

    return Response(
        {
            "status": "success",
            "message": "User onboarded successfully",
            "data": {
                "profile": profile_data,
                "reserved_account": result.get('data'),
            }
        },
        status=status.HTTP_201_CREATED
    )


@api_view(['GET'])
def get_profile(request, profile_id):
    try:
        profile = UserProfile.objects.get(profile_id=profile_id)
    except UserProfile.DoesNotExist:
        return Response(
            {"status": "error", "message": "Profile not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = UserProfileSerializer(profile)

    try:
        account = ReservedAccount.objects.filter(profile=profile).first()
    except Exception:
        account = None

    return Response({
        "status": "success",
        "data": {
            "profile": serializer.data,
            "reserved_account": {
                "bank_name": account.bank_name,
                "account_number": account.account_number,
                "account_name": account.account_name,
            } if account else None
        }
    })
