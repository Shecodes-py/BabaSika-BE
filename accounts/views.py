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
