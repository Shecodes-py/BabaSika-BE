import logging
import time

logger = logging.getLogger(__name__)


class BabaSikaConfigurationEngine:

    PERSONAS = {
        'iyabo': {
            'id': 'iyabo',
            'full_name': 'Iyabo Adebayo',
            'income_type': 'MARKET_SELLER',
            'income_title': 'Market Trader / Cash Sales',
            'preferred_currency': 'NGN',
            'savings_strategy': 'SPLIT_40_60',
            'saving_behavior': 'Voice + WhatsApp + Market Round-ups',
            'currency_symbol': '₦',
            'total_saved': 31250,
            'contingent_balance': 12500,
            'retirement_balance': 18750,
            'split_label': '40% Safety / 60% Future Pension',
        },
        'tunde': {
            'id': 'tunde',
            'full_name': 'Tunde Bakare',
            'income_type': 'DAILY_DRIVER',
            'income_title': 'Daily Driver / Transport',
            'preferred_currency': 'NGN',
            'savings_strategy': 'SPLIT_40_60',
            'saving_behavior': 'Automated Evening Daily Sweep',
            'currency_symbol': '₦',
            'total_saved': 45000,
            'contingent_balance': 18000,
            'retirement_balance': 27000,
            'split_label': '40% Safety / 60% Future Pension',
        },
        'thomas': {
            'id': 'thomas',
            'full_name': 'Thomas Chukwu',
            'income_type': 'FREELANCER_USD',
            'income_title': 'Online Freelancer / USD',
            'preferred_currency': 'USD',
            'savings_strategy': 'PERCENTAGE_20_80',
            'saving_behavior': '% of Foreign Payout (20% Future / 80% Available)',
            'currency_symbol': '$',
            'total_saved': 800,
            'contingent_balance': 160,
            'retirement_balance': 640,
            'split_label': '20% Future / 80% Available Income',
        }
    }

    @staticmethod
    def configure_user_bmoni_rails(user_profile, bmoni_service):
        try:
            currency = getattr(user_profile, 'preferred_currency', 'NGN')
            income_type = getattr(user_profile, 'income_type', 'MARKET_SELLER')

            # Provision USDB smart wallet if freelancer USD earner
            if currency == 'USD' or income_type == 'FREELANCER_USD':
                usdb_wallet = bmoni_service.provision_smart_wallet(user_profile.bmoni_user_id, currency='USDB')
                user_profile.usdb_smart_wallet_id = usdb_wallet['smartWalletId']
                user_profile.usdb_wallet_address = usdb_wallet['smartWalletAddress']
                user_profile.savings_strategy = 'PERCENTAGE_20_80'
                user_profile.save()

            return {
                'status': 'configured',
                'income_type': income_type,
                'currency': currency,
                'strategy': user_profile.savings_strategy,
            }
        except Exception as e:
            logger.warning(f"Configuration engine warning: {e}")
            return {'status': 'configured_with_fallbacks'}

    @staticmethod
    def get_persona(persona_id):
        return BabaSikaConfigurationEngine.PERSONAS.get(persona_id.lower(), BabaSikaConfigurationEngine.PERSONAS['iyabo'])
