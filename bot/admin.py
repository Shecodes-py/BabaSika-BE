from django.contrib import admin
from .models import WhatsAppOnboarding, WhatsAppPendingTransaction, InboundMessageLog


@admin.register(WhatsAppOnboarding)
class WhatsAppOnboardingAdmin(admin.ModelAdmin):
    list_display = (
        "phone_number",
        "full_name",
        "stage",
        "preferred_language",
        "created_at",
    )
    search_fields = ("phone_number", "full_name", "email")
    list_filter = ("stage", "preferred_language")


@admin.register(WhatsAppPendingTransaction)
class WhatsAppPendingTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "phone_number",
        "gross_amount",
        "contingent_amount",
        "retirement_amount",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    readonly_fields = [f.name for f in WhatsAppPendingTransaction._meta.fields]


@admin.register(InboundMessageLog)
class InboundMessageLogAdmin(admin.ModelAdmin):
    list_display = ("from_number", "body", "media_content_type", "processed", "created_at")
