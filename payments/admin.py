from django.contrib import admin
from .models import Transaction, Ledger, TransactionAudit

admin.site.register(Transaction)
admin.site.register(Ledger)
admin.site.register(TransactionAudit)