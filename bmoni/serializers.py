from rest_framework import serializers


class OnboardBMONISerializer(serializers.Serializer):
    profile_id = serializers.UUIDField()


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