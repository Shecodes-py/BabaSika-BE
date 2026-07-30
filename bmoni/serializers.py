from rest_framework import serializers


class UnifiedRegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    phone_number = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True)
    preferred_language = serializers.ChoiceField(
        choices=['en', 'pidgin', 'yoruba', 'hausa', 'igbo'],
        default='en',
    )
    pfa_id = serializers.IntegerField(required=False, allow_null=True)
    bvn = serializers.CharField(max_length=11, required=False, allow_blank=True)


class PensionDepositSerializer(serializers.Serializer):
    profile_id = serializers.UUIDField()
    gross_amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=0)


class VoiceInputSerializer(serializers.Serializer):
    profile_id = serializers.UUIDField()
    audio_url = serializers.URLField(required=False)
    raw_text = serializers.CharField(required=False)


class IntentResultSerializer(serializers.Serializer):
    intent = serializers.CharField()
    gross_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    raw_text = serializers.CharField()