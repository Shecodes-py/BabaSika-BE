import logging
import re
from decimal import Decimal

logger = logging.getLogger(__name__)

MULTILINGUAL_TRANSLATIONS = {
    'pidgin': {
        'pension_definition': "Pension na money wey you dey put aside now so say when you no dey work again, you still get money to take care of yourself.",
        'why_split': "BabaSika dey split your money 40% into Contingent (Emergency money for 3 months time) and 60% into Retirement (locked pension for future). This means you dey build your future without locking all your money out of reach.",
        'rsa_explanation': "RSA (Retirement Savings Account) na your special pension account where your retirement money dey grow safely with your PFA.",
        'compound_growth': "Compound growth mean say your money dey born pikin! The gain wey your money make will make another gain as time dey go.",
    },
    'yoruba': {
        'pension_definition': "Pension ni owo ti o pamọ nisinsinyi ki o le ri nkan lo nigbati o ba dagba ti o ko ri iṣẹ ṣe mọ.",
        'why_split': "BabaSika n pin owo rẹ si 40% (Contingent fun pajawiri) ati 60% (Retirement fun ọjọ iwaju). Eyi n jẹ ki o kọ ọjọ iwaju rẹ pẹlu alaafia.",
        'rsa_explanation': "RSA jẹ akọọlẹ fẹsẹmiji ti o wa fun fẹsẹmiji rẹ pẹlu PFA rẹ.",
        'compound_growth': "Ere lori ere n jẹ ki owo rẹ gbooro sii nigbati o ba tẹsiwaju lati tọjú rẹ.",
    },
    'hausa': {
        'pension_definition': "Pension shine kudin da kake adanawa yanzu don lokacin da ba zaka iya aiki ba a nan gaba.",
        'why_split': "BabaSika yana raba kudin ku 40% zuwa Contingent (kudin gaggawa) da 60% zuwa Retirement (kudin ritaya).",
        'rsa_explanation': "RSA asusun ritaya ne wanda ke kare kudin ku tare da PFA dinku.",
        'compound_growth': "Haɓaka kudin ku yana karuwa a kan lokaci yayin da kuke ci gaba da adana kudi.",
    },
    'igbo': {
        'pension_definition': "Pension bu ego i na-edobe ugbu a ka i nwee ike iji ya lekota onwe gi mgbe i mepere agadi.",
        'why_split': "BabaSika na-ekewa ego gi 40% gaa Contingent (ego mberede) yana 60% gaa Retirement (ego ezumike nká).",
        'rsa_explanation': "RSA bu akaụntụ ezumike nká pụrụ iche ebe ego gi na-eto n'enweghị nsogbu.",
        'compound_growth': "Ego gi na-amụ nwa ka oge na-aga ma i nọgide na-edobe ego.",
    },
    'english': {
        'pension_definition': "A pension is a dedicated savings structure that ensures you maintain income and dignity when you stop active working.",
        'why_split': "BabaSika automatically splits your money 40% into Contingent (accessible after 3 months for short-term liquidity) and 60% into Retirement (locked long-term pension). This balances immediate security with future independence.",
        'rsa_explanation': "An RSA (Retirement Savings Account) is your official pension account managed by your chosen Pension Fund Administrator (PFA).",
        'compound_growth': "Compound growth means earning interest on both your original savings and the interest previously earned over time.",
    }
}

UNSAFE_KEYWORDS = [
    'crypto', 'bitcoin', 'borrow to invest', 'guaranteed 100%', 'ponzi',
    'take loan', 'doubling money', 'arbitrage'
]


class BabaSikaAIFinancialCoach:

    @staticmethod
    def is_safe_prompt(user_query):
        query_lower = user_query.lower()
        for kw in UNSAFE_KEYWORDS:
            if kw in query_lower:
                return False
        return True

    @staticmethod
    def explain_transaction(gross_amount, language='english', profile_name='Member'):
        try:
            amount = Decimal(str(gross_amount))
        except Exception:
            amount = Decimal('500')

        contingent = Decimal(int(amount * Decimal('0.40')))
        retirement = amount - contingent

        lang_key = language.lower() if language.lower() in MULTILINGUAL_TRANSLATIONS else 'english'
        base_split = MULTILINGUAL_TRANSLATIONS[lang_key]['why_split']

        if lang_key == 'pidgin':
            summary = f"You put ₦{int(amount):,} into BabaSika! We kept ₦{int(contingent):,} (40%) inside your Contingent Emergency wallet and put ₦{int(retirement):,} (60%) inside your Retirement wallet."
        elif lang_key == 'yoruba':
            summary = f"O fi ₦{int(amount):,} si BabaSika. A pa ₦{int(contingent):,} mọ fun pajawiri ati ₦{int(retirement):,} fun ọjọ iwaju rẹ."
        elif lang_key == 'hausa':
            summary = f"Ka saka ₦{int(amount):,} a BabaSika. Mun ajiye ₦{int(contingent):,} don gaggawa da ₦{int(retirement):,} don ritaya."
        elif lang_key == 'igbo':
            summary = f"I tinyere ₦{int(amount):,} na BabaSika. Anyị debere ₦{int(contingent):,} maka mberede na ₦{int(retirement):,} maka ezumike nká."
        else:
            summary = f"You contributed ₦{int(amount):,} to BabaSika! We allocated ₦{int(contingent):,} (40%) to your Contingent safety wallet and ₦{int(retirement):,} (60%) to your Retirement wallet."

        return {
            'gross_amount': float(amount),
            'contingent_amount': float(contingent),
            'retirement_amount': float(retirement),
            'summary': summary,
            'rationale': base_split,
            'language': lang_key,
        }

    @staticmethod
    def answer_financial_query(query, language='english', contingent_balance=0, retirement_balance=0, profile_name='Member'):
        if not BabaSikaAIFinancialCoach.is_safe_prompt(query):
            return {
                'status': 'refused',
                'answer': "BabaSika Financial Coach is designed for educational guidance on micro-pensions, savings, and budgeting. We do not provide speculative investment or borrowing advice.",
                'is_safe': False,
            }

        q_lower = query.lower()
        lang_key = language.lower() if language.lower() in MULTILINGUAL_TRANSLATIONS else 'english'
        dict_trans = MULTILINGUAL_TRANSLATIONS[lang_key]

        # USD Freelance Income Detection Prompt
        usd_match = re.search(r'\$(\d+(?:\.\d+)?)|\b(\d+)\s*dollars?', q_lower)
        if ('paid' in q_lower or 'got' in q_lower or 'client' in q_lower or 'freelance' in q_lower) and usd_match:
            val = float(usd_match.group(1) or usd_match.group(2) or 1200)
            future = round(val * 0.20, 2)
            available = round(val - future, 2)
            answer = (
                f"Congratulations on your freelance payout of ${val:,.2f}! "
                f"Based on your USD freelancer savings plan, BabaSika allocates 20% (${future:,.2f}) toward your future micro-pension "
                f"and leaves 80% (${available:,.2f}) as your available income."
            )
            return {
                'status': 'success',
                'query': query,
                'answer': answer,
                'language': lang_key,
                'is_safe': True,
                'usd_allocation': {
                    'payout': val,
                    'future_20_percent': future,
                    'available_80_percent': available,
                }
            }

        total_saved = float(contingent_balance) + float(retirement_balance)

        # Contextual Money Awareness
        context_intro = f"You have saved a total of ₦{int(total_saved):,} with BabaSika (₦{int(contingent_balance):,} Contingent / ₦{int(retirement_balance):,} Retirement)."

        if 'pension' in q_lower or 'wetin be' in q_lower or 'kini' in q_lower:
            answer = f"{context_intro} {dict_trans['pension_definition']} {dict_trans['why_split']}"
        elif 'split' in q_lower or '40/60' in q_lower or 'why' in q_lower or 'contingent' in q_lower:
            answer = f"{context_intro} {dict_trans['why_split']}"
        elif 'rsa' in q_lower or 'pfa' in q_lower:
            answer = dict_trans['rsa_explanation']
        elif 'compound' in q_lower or 'growth' in q_lower or 'interest' in q_lower:
            answer = f"{dict_trans['compound_growth']} For example, if you save ₦500 daily for 5 years, your money grows exponentially with investment returns!"
        else:
            answer = f"{context_intro} {dict_trans['why_split']}"

        return {
            'status': 'success',
            'query': query,
            'answer': answer,
            'language': lang_key,
            'user_context': {
                'total_saved': total_saved,
                'contingent_balance': float(contingent_balance),
                'retirement_balance': float(retirement_balance),
            },
            'is_safe': True,
        }
