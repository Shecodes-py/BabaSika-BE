from django.contrib import admin

from .models import InboundMessageLog, Transaction, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "phone_number",
        "full_name",
        "onboarding_stage",
        "kyc_status",
        "contingent_balance",
        "retirement_balance",
        "created_at",
    )
    search_fields = ("phone_number", "full_name", "email", "bmoni_user_id")
    list_filter = ("onboarding_stage", "kyc_status", "preferred_language")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "tx_id",
        "user",
        "gross_amount",
        "contingent_credit",
        "retirement_credit",
        "source",
        "status",
        "created_at",
    )
    list_filter = ("source", "status")
    readonly_fields = [f.name for f in Transaction._meta.fields]


@admin.register(InboundMessageLog)
class InboundMessageLogAdmin(admin.ModelAdmin):
    list_display = ("from_number", "body", "media_content_type", "created_at")
