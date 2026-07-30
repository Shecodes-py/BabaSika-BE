import re
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class AIFinancialEngine:
    """
    AI Financial Advisor & Voice/NLU Engine for BabaSika.
    Combines Natural Language Understanding (NLU) for voice/text inputs
    with an AI Financial Literacy & Micro-Pension Optimization Advisor.
    """

    SUPPORTED_LANGUAGES = ['en', 'pidgin', 'hausa', 'yoruba', 'igbo']

    @staticmethod
    def extract_intent(raw_text: str, language: str = 'en') -> dict:
        """
        Extracts financial intent, target amount, confidence score, and language context
        from user voice-to-text transcripts or typed text commands.
        """
        if not raw_text or not raw_text.strip():
            return {
                'intent': 'UNKNOWN',
                'amount': 0.0,
                'confidence': 0.0,
                'raw_text': raw_text or '',
                'language': language,
                'explanation': 'No input provided.',
            }

        text = raw_text.lower().strip()

        # Regex pattern matching numbers with optional commas or k/kera suffixes (e.g., 5k = 5000)
        amount = 0.0
        k_match = re.search(r'(\d+(?:\.\d+)?)\s*k\b', text)
        if k_match:
            amount = float(k_match.group(1)) * 1000.0
        else:
            num_match = re.search(r'(\d[\d,]*)(?:\.\d+)?', text)
            if num_match:
                clean_num = num_match.group(1).replace(',', '')
                try:
                    amount = float(clean_num)
                except ValueError:
                    amount = 0.0

        # Keywords for intent detection across English, Pidgin, and local terms
        deposit_keywords = [
            'keep', 'save', 'deposit', 'put', 'add', 'pension', 'contribute',
            'waka', 'hold', 'set aside', 'baba sika', 'store', 'lock'
        ]
        balance_keywords = [
            'balance', 'how much', 'remain', 'left', 'check', 'wetin I get',
            'my money', 'show me', 'account'
        ]
        withdraw_keywords = [
            'withdraw', 'collect', 'pull', 'emergency', 'take out', 'need cash',
            'remove'
        ]
        advice_keywords = [
            'advice', 'help', 'plan', 'retire', 'how to', 'tip', 'guide',
            'explain', 'future'
        ]

        has_deposit = any(kw in text for kw in deposit_keywords)
        has_balance = any(kw in text for kw in balance_keywords)
        has_withdraw = any(kw in text for kw in withdraw_keywords)
        has_advice = any(kw in text for kw in advice_keywords)

        confidence = 0.85

        if has_deposit and amount > 0:
            intent = 'MAKE_DEPOSIT'
            explanation = f"Detected request to save ₦{amount:,.2f} with 40/60 emergency/pension allocation."
        elif has_withdraw and amount > 0:
            intent = 'WITHDRAW_EMERGENCY'
            explanation = f"Detected emergency withdrawal request of ₦{amount:,.2f} from liquid contingent wallet."
        elif has_balance:
            intent = 'CHECK_BALANCE'
            explanation = "Detected request to query live BMONI smart wallet balances."
        elif has_advice:
            intent = 'GET_FINANCIAL_ADVICE'
            explanation = "Detected request for AI financial advice and micro-pension planning."
        elif amount > 0:
            intent = 'MAKE_DEPOSIT'
            confidence = 0.70
            explanation = f"Extracted amount ₦{amount:,.2f}. Defaulting to savings deposit."
        else:
            intent = 'UNKNOWN'
            confidence = 0.30
            explanation = "Could not clearly identify financial intent."

        return {
            'intent': intent,
            'amount': amount,
            'confidence': confidence,
            'raw_text': raw_text,
            'language': language,
            'explanation': explanation,
        }

    @staticmethod
    def generate_advisor_report(profile_name: str, contingent_balance: Decimal, retirement_balance: Decimal, transaction_count: int = 0) -> dict:
        """
        Evaluates user's live BMONI smart wallet balances and generates tailored financial advice,
        emergency coverage metrics, retirement readiness score, and actionable tips.
        """
        c_bal = float(contingent_balance or 0)
        r_bal = float(retirement_balance or 0)
        total_bal = c_bal + r_bal

        # Calculate Financial Safety Score (0 - 100)
        # Weighting: Contingent emergency buffer (40%) + Retirement accumulation (60%)
        contingent_score = min(40.0, (c_bal / 50000.0) * 40.0)
        retirement_score = min(60.0, (r_bal / 100000.0) * 60.0)
        safety_score = int(round(contingent_score + retirement_score))

        # Generate contextual recommendations
        insights = []
        if total_bal == 0:
            insights.append("🌟 Welcome to BabaSika! Make your first deposit to activate your 40% emergency liquid fund and 60% locked pension.")
        elif c_bal < 10000:
            insights.append(f"💡 Your liquid emergency buffer is ₦{c_bal:,.2f}. Consider saving ₦5,000 more to handle sudden business expenses.")
        else:
            insights.append(f"✅ Great job! You have ₦{c_bal:,.2f} safely buffered in your liquid contingent wallet for unexpected needs.")

        if r_bal > 0:
            growth_projection_10yr = r_bal * (1.10 ** 10)  # Assume 10% compound annual return via PFA custodian
            insights.append(f"📈 Micro-Pension Forecast: Your locked ₦{r_bal:,.2f} retirement fund is projected to grow to ~₦{growth_projection_10yr:,.2f} in 10 years with PenCom licensed custodians.")

        if transaction_count >= 5:
            insights.append("🔥 High Saver Streak: You are building strong discipline! Regular micro-savings protect gig workers against income volatility.")

        summary_pidgin = (
            f"Hello {profile_name}! You get total ₦{total_bal:,.2f} inside BabaSika. "
            f"₦{c_bal:,.2f} dey inside your Emergency wallet where you fit collect anytime, "
            f"and ₦{r_bal:,.2f} dey locked inside your Pension wallet for your future. Keep am up!"
        )

        return {
            'profile_name': profile_name,
            'total_balance': f"{total_bal:,.2f}",
            'contingent_balance': f"{c_bal:,.2f}",
            'retirement_balance': f"{r_bal:,.2f}",
            'safety_score': safety_score,
            'safety_level': 'EXCELLENT' if safety_score > 75 else 'GOOD' if safety_score > 40 else 'BUILDING',
            'insights': insights,
            'summary_pidgin': summary_pidgin,
        }

    @staticmethod
    def detect_anomaly(amount: float, profile_name: str) -> dict:
        """
        Evaluates a transaction for financial safety & fraud prevention.
        """
        if amount > 500000.0:
            return {
                'is_anomaly': True,
                'risk_level': 'HIGH',
                'reason': f"Deposit amount ₦{amount:,.2f} exceeds standard micro-pension threshold.",
                'recommendation': 'Requires additional confirmation.',
            }
        return {
            'is_anomaly': False,
            'risk_level': 'LOW',
            'reason': 'Transaction is within normal micro-pension ranges.',
            'recommendation': 'Approved for processing.',
        }
