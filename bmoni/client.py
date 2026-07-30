import json
import logging
import time
from decimal import Decimal
from urllib.parse import urljoin

import requests
from django.conf import settings
from eth_account import Account
from eth_account.messages import encode_defunct

logger = logging.getLogger(__name__)


class BMONIService:
    def __init__(self):
        self.base_url = getattr(settings, 'BMONI_BASE_URL', 'https://embedded-dev.bmoni.com').rstrip('/')
        self.api_key = getattr(settings, 'BMONI_API_KEY', '')

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

    def _request(self, method, endpoint, payload=None, params=None):
        url = f"{self.base_url}{endpoint}"
        start = time.time()
        try:
            resp = requests.request(
                method=method,
                url=url,
                json=payload,
                params=params,
                headers=self._headers(),
                timeout=30,
            )
            duration = int((time.time() - start) * 1000)
            
            try:
                result = resp.json()
            except ValueError:
                result = {'raw': resp.text}

            if resp.ok:
                self._log_call(endpoint, method, payload or params, result, resp.status_code, duration, True)
                return result
            else:
                self._log_call(endpoint, method, payload or params, result, resp.status_code, duration, False)
                logger.error(f"BMONI request failed: {method} {endpoint} ({resp.status_code}) - {result}")
                resp.raise_for_status()
                return result
        except requests.RequestException as e:
            duration = int((time.time() - start) * 1000)
            error_body = {}
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_body = e.response.json()
                except Exception:
                    error_body = {'raw': str(e.response.text)}
            self._log_call(endpoint, method, payload or params, {'error': str(e), 'response': error_body}, getattr(e.response, 'status_code', 0), duration, False)
            logger.error(f"BMONI request exception: {method} {endpoint} - {e}")
            raise

    # Step 1: Create a user
    def create_user(self, first_name, email, phone_number):
        formatted_phone = phone_number.strip().replace(' ', '').replace('-', '')
        if formatted_phone.startswith('0'):
            formatted_phone = '+234' + formatted_phone[1:]
        elif not formatted_phone.startswith('+'):
            formatted_phone = '+' + formatted_phone

        endpoint = '/v1/users'
        payload = {
            'firstName': first_name,
            'email': email or f"{formatted_phone.replace('+', '')}@babasika.com",
            'phoneNumber': formatted_phone,
        }
        result = self._request('POST', endpoint, payload)
        user_obj = result.get('user', {})
        bmoni_user_id = user_obj.get('bmoniUserId') or user_obj.get('id') or result.get('bmoniUserId')
        if not bmoni_user_id:
            raise RuntimeError(f"BMONI create_user response missing a user id: {result}")
        return bmoni_user_id

    # Step 2: Create managed smart wallet with owner-proof challenge
    def provision_smart_wallet(self, bmoni_user_id, currency='CNGN'):
        # Check if user already has wallets in BMONI
        try:
            existing = self.get_account_wallets(bmoni_user_id)
            if isinstance(existing, list) and len(existing) > 0:
                w = existing[0]
                return {
                    'smartWalletId': w.get('id'),
                    'smartWalletAddress': w.get('walletAddress') or w.get('address'),
                    'ownerAddress': None,
                }
        except Exception:
            pass

        # 1. Generate fresh Ethereum key pair for owner proof
        acct = Account.create()
        owner_address = acct.address

        # 2. Request owner-proof challenge
        challenge_endpoint = f'/v1/users/{bmoni_user_id}/smart-wallets/owner-proof-challenges'
        challenge_payload = {
            'currency': currency,
            'userOwnerAddress': owner_address,
        }
        challenge_result = self._request('POST', challenge_endpoint, challenge_payload)
        challenge_id = challenge_result.get('challengeId')
        message_to_sign = challenge_result.get('message', '')

        # 3. Sign exact challenge message using eth_account
        encoded_msg = encode_defunct(text=message_to_sign)
        signed_msg = acct.sign_message(encoded_msg)
        signature_hex = signed_msg.signature.hex()
        if not signature_hex.startswith('0x'):
            signature_hex = '0x' + signature_hex

        # 4. Create managed smart wallet
        create_endpoint = f'/v1/users/{bmoni_user_id}/smart-wallets/create-managed'
        create_payload = {
            'currency': currency,
            'userOwnerAddress': owner_address,
            'ownerProofChallengeId': challenge_id,
            'ownerProofSignature': signature_hex,
        }
        create_result = self._request('POST', create_endpoint, create_payload)

        wallet_id = (
            create_result.get('smartWalletId')
            or create_result.get('id')
            or create_result.get('smartWallet', {}).get('id')
        )
        wallet_address = (
            create_result.get('smartWalletAddress')
            or create_result.get('walletAddress')
            or create_result.get('address')
            or create_result.get('smartWallet', {}).get('walletAddress')
        )

        if not wallet_id:
            raise RuntimeError(f"BMONI smart wallet creation response missing wallet id: {create_result}")

        return {
            'smartWalletId': wallet_id,
            'smartWalletAddress': wallet_address,
            'ownerAddress': owner_address,
        }

    # Step 3 & 4: Sandbox KYC and Activate Nigerian Rail
    def complete_sandbox_kyc_and_activate_rail(self, bmoni_user_id, wallet_address, wallet_index=0):
        rail_endpoint = f'/v1/users/{bmoni_user_id}/onboarding/start-nigeria'
        rail_payload = {
            'bvn': '22222222222',
            'ngnWalletAddress': wallet_address,
            'ngnWalletIndex': wallet_index,
        }
        rail_result = self._request('POST', rail_endpoint, rail_payload)

        status_endpoint = f'/v1/users/{bmoni_user_id}/onboarding/status'
        status_result = self._request('GET', status_endpoint)

        return {
            'rail_activation': rail_result,
            'onboarding_status': status_result,
        }

    # Step 5: Read Wallet Data
    def get_account_wallets(self, bmoni_user_id):
        endpoint = f'/v1/users/{bmoni_user_id}/smart-wallets/account/wallets'
        return self._request('GET', endpoint)

    def get_account_balances(self, bmoni_user_id):
        endpoint = f'/v1/users/{bmoni_user_id}/smart-wallets/account/balances'
        return self._request('GET', endpoint)

    def get_account_transactions(self, bmoni_user_id, smart_wallet_id=None):
        """Transactions are read per smart wallet. BMONI has no account-wide
        transactions route (.../smart-wallets/account/transactions does not
        exist - it 400s because 'account' gets parsed as the wallet UUID), so
        when no wallet is given we read the user's first wallet."""
        if not smart_wallet_id:
            wallets = self.get_account_wallets(bmoni_user_id)
            if not wallets:
                return {'transactions': [], 'total': 0}
            smart_wallet_id = wallets[0].get('id')
        endpoint = f'/v1/users/{bmoni_user_id}/smart-wallets/{smart_wallet_id}/transactions'
        return self._request('GET', endpoint)

    # BVN Lookup
    def bvn_lookup(self, bmoni_user_id, bvn='22222222222'):
        endpoint = f'/v1/users/{bmoni_user_id}/kyc/bvn-lookup/{bvn}'
        return self._request('GET', endpoint)

    # Move Money / Transfers
    def execute_transfer(self, bmoni_user_id, wallet_id, amount, from_wallet_id=None, note=None):
        """Fund a smart wallet from the user's personal wallet.

        Real endpoint: POST /v1/users/{userId}/smart-wallets/fund
        Body: fromWalletId (personal wallet), groupWalletId (target smart
        wallet), amount (decimal string), note (optional).

        NOTE: the previously used POST /v1/transfers does not exist on BMONI
        (404 'Cannot POST /v1/transfers') - it never worked.

        `from_wallet_id` is a BMONI *personal* wallet. Partner-created users
        have smart wallets only, and the partner API exposes no route to
        create a personal wallet, so this stays unfunded until BMONI provides
        a funding source (see audit notes).
        """
        if not from_wallet_id:
            raise ValueError(
                "BMONI transfer needs a source personal wallet (fromWalletId). "
                "This user has smart wallets only - no funding source is provisioned yet."
            )

        payload = {
            'fromWalletId': from_wallet_id,
            'groupWalletId': wallet_id,
            'amount': str(amount),
        }
        if note:
            payload['note'] = note
        return self._request('POST', f'/v1/users/{bmoni_user_id}/smart-wallets/fund', payload)