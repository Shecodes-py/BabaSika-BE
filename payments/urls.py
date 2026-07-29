from django.urls import path
from . import views

urlpatterns = [
    path('ledger/<uuid:profile_id>', views.get_ledger, name='get-ledger'),
    path('transactions/<uuid:profile_id>', views.get_transactions, name='get-transactions'),
    path('reserved-account/<uuid:profile_id>', views.get_reserved_account, name='get-reserved-account'),
    path('withdraw-emergency', views.withdraw_emergency, name='withdraw-emergency'),
]
