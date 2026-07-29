from django.urls import path
from . import views

urlpatterns = [
    path('bmoni/onboard', views.onboard_user_bmoni, name='bmoni-onboard'),
    path('bmoni/deposit', views.deposit_pension, name='bmoni-deposit'),
    path('bmoni/voice-webhook', views.voice_webhook, name='bmoni-voice-webhook'),
    path('bmoni/api-log', views.api_log, name='bmoni-api-log'),
]