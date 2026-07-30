from rest_framework import serializers
from .models import Transaction, Ledger


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'transaction_ref', 'txn_type',
            'wallet_type', 'amount', 'fee', 'description', 'status', 'created_at'
        ]


class LedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ledger
        fields = ['contingent_balance', 'retirement_balance', 'total_contributions', 'updated_at']
