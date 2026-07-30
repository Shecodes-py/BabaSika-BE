import uuid
from django.db import models
from accounts.models import UserProfile


class Transaction(models.Model):
    TXN_TYPES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('split_40', '40% Contingent Split'),
        ('split_60', '60% Retirement Split'),
        ('pfa_transfer', 'PFA Transfer'),
    ]

    WALLET_TYPES = [
        ('contingent', 'Contingent (40%)'),
        ('retirement', 'Retirement (60%)'),
    ]

    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='transactions')
    transaction_ref = models.CharField(max_length=255, unique=True, default=uuid.uuid4)
    txn_type = models.CharField(max_length=20, choices=TXN_TYPES)
    wallet_type = models.CharField(max_length=20, choices=WALLET_TYPES, blank=True, null=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    fee = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='completed')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.txn_type} - {self.amount} - {self.transaction_ref}"


class Ledger(models.Model):
    profile = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name='ledger')
    contingent_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    retirement_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_contributions = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ledger"
        verbose_name_plural = "Ledgers"

    def __str__(self):
        return f"{self.profile.full_name}: {self.total_contributions} total"


class TransactionAudit(models.Model):
    TX_STATUS_CHOICES = [
        ('INITIATED', 'Initiated'),
        ('PROCESSING', 'Processing'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    ]

    tx_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='transaction_audits')
    gross_amount = models.DecimalField(max_digits=15, decimal_places=2)
    contingent_credit = models.DecimalField(max_digits=15, decimal_places=2)
    retirement_credit = models.DecimalField(max_digits=15, decimal_places=2)
    bmoni_tx_id_1 = models.CharField(max_length=255, null=True, blank=True)
    bmoni_tx_id_2 = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=20, choices=TX_STATUS_CHOICES, default='INITIATED')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Transaction Audit"
        verbose_name_plural = "Transaction Audits"

    def __str__(self):
        return f"{self.tx_id} - {self.gross_amount} ({self.status})"
