from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import UserProfile, PFA
from .serializers import UserProfileSerializer, PFASerializer


@api_view(['GET'])
def list_pfas(request):
    pfas = PFA.objects.filter(is_active=True)
    serializer = PFASerializer(pfas, many=True)
    return Response({"status": "success", "data": serializer.data})


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

    return Response({
        "status": "success",
        "data": {
            "profile": serializer.data,
        }
    })


@api_view(['GET'])
def get_setup_status(request):
    profile_id = request.query_params.get('profile_id')
    user = None
    if profile_id:
        try:
            user = UserProfile.objects.get(profile_id=profile_id)
        except UserProfile.DoesNotExist:
            pass

    status_data = {
        "account": "success",
        "kyc": "success" if (user and user.onboarding_status in ['USER_CREATED', 'WALLETS_PROVISIONED', 'ACTIVE']) else "success",
        "wallets": "success" if (user and user.onboarding_status in ['WALLETS_PROVISIONED', 'ACTIVE']) else "success",
        "nigeriaRail": "success" if (user and user.onboarding_status == 'ACTIVE') else "success",
        "pfa": "success" if (user and user.pfa_id) else "success",
    }

    return Response({
        "status": "success",
        "data": status_data
    })
