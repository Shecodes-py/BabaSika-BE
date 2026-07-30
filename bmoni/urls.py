from django.urls import path
from . import views

urlpatterns = [
    path('onboard', views.unified_register, name='unified-register'),
    path('bmoni/deposit', views.deposit_pension, name='bmoni-deposit'),
    path('bmoni/voice-webhook', views.voice_webhook, name='bmoni-voice-webhook'),
    path('bmoni/api-log', views.api_log, name='bmoni-api-log'),
]