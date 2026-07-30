from django.urls import path
from . import views

urlpatterns = [
    path("whatsapp/", views.whatsapp_webhook, name="whatsapp_webhook"),
    path("whatsapp/webhook", views.whatsapp_webhook, name="whatsapp_webhook_alias"),
    path("webhook", views.whatsapp_webhook, name="bot_webhook"),
]
