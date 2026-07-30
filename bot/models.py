import uuid

from django.db import models


class OnboardingStage(models.TextChoices):
    """Drives the conversational form-filling. Each inbound message advances
    the user exactly one stage (see services/conversation.py)."""

    NEW = "NEW", "New"
    ASK_NAME = "ASK_NAME", "Awaiting name"
    ASK_EMAIL = "ASK_EMAIL", "Awaiting email"
    ASK_NIN = "ASK_NIN", "Awaiting NIN/BVN"
    ASK_PFA = "ASK_PFA", "Awaiting preferred PFA"
    ASK_LANGUAGE = "ASK_LANGUAGE", "Awaiting preferred language"
    PROVISIONING = "PROVISIONING", "Registering with BMONI"
    ONBOARDED = "ONBOARDED", "Fully onboarded"


class KYCStatus(models.TextChoices):
    NOT_STARTED = "NOT_STARTED", "Not started"
    PENDING = "PENDING", "Pending"
    VERIFIED = "VERIFIED", "Verified"
    FAILED = "FAILED", "Failed"


class Language(models.TextChoices):
    ENGLISH = "ENGLISH", "English"
    YORUBA = "YORUBA", "Yoruba"
    HAUSA = "HAUSA", "Hausa"
    IGBO = "IGBO", "Igbo"
    PIDGIN = "PIDGIN", "Pidgin"


class User(models.Model):
    """A BabaSika saver. One row per WhatsApp phone number."""

    user_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # WhatsApp identity (the E.164 number Twilio gives us, e.g. "+2348012345678")
    phone_number = models.CharField(max_length=32, unique=True, db_index=True)

    # Collected conversationally during onboarding
    full_name = models.CharField(max_length=255, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    nin_bvn = models.CharField(max_length=32, blank=True, default="")  # consider field-level encryption in prod
    preferred_pfa = models.CharField(max_length=255, blank=True, default="")
    preferred_language = models.CharField(
        max_length=16, choices=Language.choices, default=Language.ENGLISH
    )

    onboarding_stage = models.CharField(
        max_length=20, choices=OnboardingStage.choices, default=OnboardingStage.NEW
    )
    kyc_status = models.CharField(
        max_length=20, choices=KYCStatus.choices, default=KYCStatus.NOT_STARTED
    )

    # BMONI-side identifiers, populated during registration orchestration
    bmoni_user_id = models.CharField(max_length=128, blank=True, default="")
    contingent_wallet_id = models.CharField(max_length=128, blank=True, default="")
    retirement_wallet_id = models.CharField(max_length=128, blank=True, default="")
    rsa_pin = models.CharField(max_length=64, blank=True, default="")

    # Cached balances. The source of truth for money is BMONI; these are a
    # local read model kept in sync by the ledger engine on every deposit.
    contingent_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    retirement_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.full_name or 'Unnamed'} ({self.phone_number})"

    @property
    def is_onboarded(self) -> bool:
        return self.onboarding_stage == OnboardingStage.ONBOARDED

    @property
    def display_name(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else "there"


class Transaction(models.Model):
    """Immutable audit record of every deposit and its 40/60 split.

    Created ONLY by the ledger engine (bot/services/ledger.py), never
    directly by the AI/intent layer. This is the deterministic source of
    truth the PRD's architecture rule is built around.
    """

    class Source(models.TextChoices):
        VOICE_NOTE = "VOICE_NOTE", "Voice note"
        TEXT = "TEXT", "Text message"
        ROUNDUP = "ROUNDUP", "Transaction round-up"
        EOD_SWEEP = "EOD_SWEEP", "End-of-day sweep"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETE = "COMPLETE", "Complete"
        FAILED = "FAILED", "Failed"

    tx_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="transactions")

    gross_amount = models.DecimalField(max_digits=14, decimal_places=2)
    contingent_credit = models.DecimalField(max_digits=14, decimal_places=2)
    retirement_credit = models.DecimalField(max_digits=14, decimal_places=2)

    source = models.CharField(max_length=20, choices=Source.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    raw_transcript = models.TextField(blank=True, default="")
    intent_confidence = models.FloatField(null=True, blank=True)
    bmoni_transfer_ref = models.CharField(max_length=128, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"₦{self.gross_amount} for {self.user.phone_number} ({self.status})"


class InboundMessageLog(models.Model):
    """Raw log of every inbound WhatsApp message/media for debugging and audit.
    Not used for decisioning — purely observability."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="inbound_messages", null=True, blank=True)
    from_number = models.CharField(max_length=32)
    body = models.TextField(blank=True, default="")
    media_url = models.URLField(blank=True, default="")
    media_content_type = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
