from django.urls import path
from . import views

urlpatterns = [
    path('onboard', views.unified_register, name='unified-register'),
    path('kyc/bvn-lookup', views.bvn_lookup_view, name='bvn-lookup'),
    path('bmoni/deposit', views.deposit_pension, name='bmoni-deposit'),
    path('bmoni/voice-webhook', views.voice_webhook, name='bmoni-voice-webhook'),
    path('bmoni/advisor', views.ai_advisor, name='bmoni-ai-advisor'),
    path('ai-coach/ask', views.ai_coach_ask, name='ai-coach-ask'),
    path('ai-coach/explain-transaction', views.explain_transaction_view, name='explain-transaction'),
    path('bmoni/balances/<uuid:profile_id>', views.get_bmoni_balances, name='bmoni-balances'),
    path('bmoni/transactions/<uuid:profile_id>', views.get_bmoni_transactions, name='bmoni-transactions'),
    path('bmoni/api-log', views.api_log, name='bmoni-api-log'),
]