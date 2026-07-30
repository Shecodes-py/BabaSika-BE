from django.urls import path
from . import views

urlpatterns = [
    path('ledger/<uuid:profile_id>', views.get_ledger, name='get-ledger'),
    path('transactions/<uuid:profile_id>', views.get_transactions, name='get-transactions'),
    path('dashboard', views.get_dashboard_data, name='get-dashboard'),
    path('money/move', views.move_money, name='move-money'),
    path('money-movement/split', views.money_movement_split, name='money-movement-split'),
    path('money-movement/withdraw', views.money_movement_withdraw, name='money-movement-withdraw'),
]
