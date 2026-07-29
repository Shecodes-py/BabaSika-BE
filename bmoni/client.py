import json
import logging
import time
from urllib.parse import urljoin

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class BMONIService:
    def __init__(self):
        self.base_url = settings.BMONI_BASE_URL
        self.api_key = settings.BMONI_API_KEY

    def _headers(self):
        return {
            'x-api-key': self.api_key,
            'Content-Type': 'application/json',
        }

    def _log_call(self, endpoint, method, request_body, response_body, status_code, duration_ms, success):
        try:
            from .models import BmoniApiLog
            BmoniApiLog.objects.create(
                endpoint=endpoint,
                method=method,
                request_body=request_body,
                response_body=response_body,
                status_code=status_code,
                duration_ms=duration_ms,
                success=success,
            )
        except Exception as e:
            logger.warning(f"Failed to log BMONI API call: {e}")

    def _request(self, method, endpoint, payload=None):
        url = urljoin(self.base_url, endpoint)
        start = time.time()
        try:
            resp = requests.request(
                method=method,
                url=url,
                json=payload,
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            duration = int((time.time() - start) * 1000)
            self._log_call(endpoint, method, payload, result, resp.status_code, duration, True)
            return result
        except requests.RequestException as e:
            duration = int((time.time() - start) * 1000)
            error_body = {}
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_body = e.response.json()
                except (ValueError, AttributeError):
                    error_body = {'raw': str(e.response.text)}
            self._log_call(endpoint, method, payload, {'error': str(e), 'response': error_body}, 0, duration, False)
            logger.error(f"BMONI request failed: {method} {endpoint} - {e}")
            raise

    def create_user(self, first_name, email, phone_number):
        endpoint = '/v1/users'
        payload = {
            'firstName': first_name,
            'email': email,
            'phoneNumber': phone_number,
        }
        result = self._request('POST', endpoint, payload)
        return result.get('bmoniUserId')

    def provision_smart_wallet(self, bmoni_user_id, currency='CNGN'):
        user_owner_address = self._generate_owner_address()

        challenge_endpoint = f'/v1/users/{bmoni_user_id}/smart-wallets/owner-proof-challenges'
        challenge_payload = {
            'currency': currency,
            'userOwnerAddress': user_owner_address,
        }
        challenge_result = self._request('POST', challenge_endpoint, challenge_payload)
        challenge_string = challenge_result.get('challengeString', '')

        signed_challenge = self._sign_challenge(challenge_string)

        create_endpoint = f'/v1/users/{bmoni_user_id}/smart-wallets/create-managed'
        create_payload = {
            'currency': currency,
            'signedChallenge': signed_challenge,
            'userOwnerAddress': user_owner_address,
        }
        create_result = self._request('POST', create_endpoint, create_payload)

        return {
            'smartWalletId': create_result.get('smartWalletId'),
            'smartWalletAddress': create_result.get('smartWalletAddress'),
        }

    def _generate_owner_address(self):
        return '0x0000000000000000000000000000000000000000'

    def _sign_challenge(self, challenge_string):
        return '0x' + '0' * 130

    def complete_sandbox_kyc_and_activate_rail(self, bmoni_user_id, wallet_address):
        kyc_endpoint = f'/v1/users/{bmoni_user_id}/onboarding/start-nigeria'
        kyc_payload = {
            'bvn': '22222222222',
            'country': 'NGA',
        }
        self._request('POST', kyc_endpoint, kyc_payload)

        status_endpoint = f'/v1/users/{bmoni_user_id}/onboarding/status'
        status_result = self._request('GET', status_endpoint)

        return status_result

    def execute_transfer(self, bmoni_user_id, wallet_id, amount, currency='CNGN'):
        transfer_payload = {
            'userId': bmoni_user_id,
            'walletId': wallet_id,
            'amount': float(amount),
            'currency': currency,
        }
        result = self._request('POST', '/v1/transfers', transfer_payload)
        return result