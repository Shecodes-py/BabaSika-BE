from django.contrib import admin
from .models import ReservedAccount, Transaction, Ledger

admin.site.register(ReservedAccount)
admin.site.register(Transaction)
admin.site.register(Ledger)
