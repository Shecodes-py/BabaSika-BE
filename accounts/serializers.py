from rest_framework import serializers
from .models import UserProfile, PFA


class PFASerializer(serializers.ModelSerializer):
    class Meta:
        model = PFA
        fields = ['id', 'name', 'short_code', 'is_active']


class UserProfileSerializer(serializers.ModelSerializer):
    pfa = PFASerializer(read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'profile_id', 'full_name', 'phone_number', 'email',
            'preferred_language', 'pfa', 'bvn_verified', 'nin_verified',
            'is_active', 'created_at',
            'bmoni_user_id', 'contingent_smart_wallet_id',
            'retirement_smart_wallet_id', 'onboarding_status',
        ]
