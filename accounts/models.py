import uuid
from django.db import models


class PFA(models.Model):
    name = models.CharField(max_length=255)
    short_code = models.CharField(max_length=20, unique=True)
    bank_name = models.CharField(max_length=255)
    bank_account_number = models.CharField(max_length=20)
    bank_code = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "PFA"
        verbose_name_plural = "PFAs"

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    LANG_CHOICES = [
        ('en', 'English'),
        ('pidgin', 'Pidgin'),
        ('yoruba', 'Yoruba'),
        ('hausa', 'Hausa'),
        ('igbo', 'Igbo'),
    ]

    ONBOARDING_CHOICES = [
        ('PENDING', 'Pending'),
        ('USER_CREATED', 'User Created'),
        ('WALLETS_PROVISIONED', 'Wallets Provisioned'),
        ('KYC_COMPLETED', 'KYC Completed'),
        ('ACTIVE', 'Active'),
    ]

    profile_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, unique=True)
    email = models.EmailField(blank=True)
    preferred_language = models.CharField(max_length=10, choices=LANG_CHOICES, default='en')
    pfa = models.ForeignKey(PFA, on_delete=models.SET_NULL, null=True, blank=True)
    bvn_verified = models.BooleanField(default=False)
    nin_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    bmoni_user_id = models.CharField(max_length=255, null=True, blank=True)
    contingent_smart_wallet_id = models.CharField(max_length=255, null=True, blank=True)
    contingent_wallet_address = models.CharField(max_length=255, null=True, blank=True)
    retirement_smart_wallet_id = models.CharField(max_length=255, null=True, blank=True)
    retirement_wallet_address = models.CharField(max_length=255, null=True, blank=True)
    onboarding_status = models.CharField(
        max_length=20, choices=ONBOARDING_CHOICES, default='PENDING'
    )

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"
