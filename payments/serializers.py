from rest_framework import serializers
from .models import Transaction, Ledger, ReservedAccount


class ReservedAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservedAccount
        fields = ['account_reference', 'account_name', 'account_number', 'bank_name', 'bank_code', 'created_at']


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            'transaction_ref', 'monnify_payment_ref', 'txn_type',
            'wallet_type', 'amount', 'fee', 'description', 'status', 'created_at'
        ]


class LedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ledger
        fields = ['contingent_balance', 'retirement_balance', 'total_contributions', 'updated_at']
