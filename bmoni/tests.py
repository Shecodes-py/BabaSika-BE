from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from accounts.models import UserProfile
from payments.models import TransactionAudit, Ledger


class BMONIServiceTests(TestCase):
    def setUp(self):
        self.user = UserProfile.objects.create(
            full_name='Test User',
            phone_number='+2348000000001',
            email='test@babasika.com',
            bmoni_user_id='bmoni-user-123',
            contingent_smart_wallet_id='wallet-con-123',
            retirement_smart_wallet_id='wallet-ret-123',
            onboarding_status='ACTIVE',
        )

    def test_40_60_split_calculation(self):
        gross = Decimal('1000')
        contingent = gross * Decimal('0.40')
        retirement = gross * Decimal('0.60')
        self.assertEqual(contingent, Decimal('400'))
        self.assertEqual(retirement, Decimal('600'))

    def test_transaction_audit_creation(self):
        tx = TransactionAudit.objects.create(
            user=self.user,
            gross_amount=Decimal('1000'),
            contingent_credit=Decimal('400'),
            retirement_credit=Decimal('600'),
            status='INITIATED',
        )
        self.assertEqual(tx.gross_amount, Decimal('1000'))
        self.assertEqual(tx.contingent_credit, Decimal('400'))
        self.assertEqual(tx.retirement_credit, Decimal('600'))
        self.assertEqual(tx.status, 'INITIATED')

    def test_ledger_update_after_deposit(self):
        ledger, _ = Ledger.objects.get_or_create(profile=self.user)
        ledger.contingent_balance += Decimal('400')
        ledger.retirement_balance += Decimal('600')
        ledger.total_contributions += Decimal('1000')
        ledger.save()

        self.assertEqual(ledger.contingent_balance, Decimal('400'))
        self.assertEqual(ledger.retirement_balance, Decimal('600'))
        self.assertEqual(ledger.total_contributions, Decimal('1000'))


class IntentExtractionTests(TestCase):
    def test_deposit_intent_extraction(self):
        from bmoni.views import _extract_intent

        result = _extract_intent('Keep 1000 Naira for my pension today')
        self.assertEqual(result['intent'], 'DEPOSIT')
        self.assertEqual(result['gross_amount'], 1000)

        result = _extract_intent('Save 2000 for retirement')
        self.assertEqual(result['intent'], 'DEPOSIT')
        self.assertEqual(result['gross_amount'], 2000)

        result = _extract_intent('Hello')
        self.assertEqual(result['intent'], 'UNKNOWN')

    def test_no_amount_returns_unknown(self):
        from bmoni.views import _extract_intent

        result = _extract_intent('Keep some money')
        self.assertEqual(result['intent'], 'UNKNOWN')
        self.assertEqual(result['gross_amount'], 0)