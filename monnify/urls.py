from django.urls import path
from . import views

urlpatterns = [
    path('monnify/webhook', views.monnify_webhook, name='monnify-webhook'),
    path('monnify/verify-payer', views.verify_payer, name='verify-payer'),
    path('monnify/simulate-payment', views.simulate_payment, name='simulate-payment'),
    path('monnify/api-log', views.api_log, name='monnify-api-log'),
]
