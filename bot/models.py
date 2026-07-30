import uuid
from django.db import models
from django.utils import timezone
from datetime import timedelta
from accounts.models import UserProfile


class OnboardingStage(models.TextChoices):
    NEW = "NEW", "New"
    ASK_NAME = "ASK_NAME", "Awaiting name"
    ASK_EMAIL = "ASK_EMAIL", "Awaiting email"
    ASK_PFA = "ASK_PFA", "Awaiting preferred PFA"
    ASK_LANGUAGE = "ASK_LANGUAGE", "Awaiting preferred language"
    PROVISIONING = "PROVISIONING", "Registering with BMONI"
    COMPLETED = "COMPLETED", "Fully onboarded"


class WhatsAppOnboarding(models.Model):
    """Tracks step-by-step onboarding for an unknown WhatsApp phone number."""
    phone_number = models.CharField(max_length=32, unique=True, db_index=True)
    full_name = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    preferred_pfa = models.CharField(max_length=255, blank=True, default="")
    preferred_language = models.CharField(max_length=20, default="en")
    stage = models.CharField(
        max_length=20, choices=OnboardingStage.choices, default=OnboardingStage.NEW
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Onboarding {self.phone_number} ({self.stage})"


class WhatsAppPendingTransaction(models.Model):
    """
    Stores 2-step confirmation proposals for money movement.
    Money is NEVER moved directly on initial AI intent recognition.
    User MUST explicitly reply YES/CONFIRM before expiration.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Confirmation"
        CONFIRMED = "CONFIRMED", "Confirmed & Executed"
        CANCELLED = "CANCELLED", "Cancelled by User"
        EXPIRED = "EXPIRED", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="whatsapp_pending_txns"
    )
    phone_number = models.CharField(max_length=32, db_index=True)
    intent = models.CharField(max_length=50, default="move_money")
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2)
    contingent_amount = models.DecimalField(max_digits=14, decimal_places=2)
    retirement_amount = models.DecimalField(max_digits=14, decimal_places=2)
    raw_transcript = models.TextField(blank=True, default="")
    confidence = models.FloatField(default=0.9)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    bmoni_tx_ref = models.CharField(max_length=255, blank=True, default="")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self) -> bool:
        return self.status == self.Status.PENDING and timezone.now() <= self.expires_at

    def __str__(self):
        return f"Pending ₦{self.gross_amount} for {self.phone_number} [{self.status}]"


class InboundMessageLog(models.Model):
    """Raw log of every inbound WhatsApp message/media for idempotency and debugging."""
    user_profile = models.ForeignKey(
        UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="whatsapp_logs"
    )
    message_sid = models.CharField(max_length=128, unique=True, null=True, blank=True, db_index=True)
    from_number = models.CharField(max_length=32)
    body = models.TextField(blank=True, default="")
    media_url = models.URLField(max_length=500, blank=True, default="")
    media_content_type = models.CharField(max_length=64, blank=True, default="")
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Msg {self.message_sid or 'NoSid'} from {self.from_number}"
