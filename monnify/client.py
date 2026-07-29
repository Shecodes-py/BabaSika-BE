import base64
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class MonnifyClient:
    def __init__(self):
        self.api_key = settings.MONNIFY_API_KEY
        self.secret = settings.MONNIFY_SECRET
        self.contract_code = settings.MONNIFY_CONTRACT_CODE
        self.base_url = settings.MONNIFY_BASE_URL
        self._token = None
        self._token_expiry = None

    def _log_call(self, endpoint, method, request_body, response_body, status_code, duration_ms, success):
        try:
            from .models import MonnifyApiLog
            MonnifyApiLog.objects.create(
                endpoint=endpoint,
                method=method,
                request_body=request_body,
                response_body=response_body,
                status_code=status_code,
                duration_ms=duration_ms,
                success=success,
            )
        except Exception as e:
            logger.warning(f"Failed to log Monnify API call: {e}")

    def _get_token(self):
        if self._token and self._token_expiry and datetime.now(timezone.utc) < self._token_expiry:
            return self._token

        start = time.time()
        credentials = f"{self.api_key}:{self.secret}"
        encoded = base64.b64encode(credentials.encode()).decode()

        url = 'POST /api/v1/auth/login'
        try:
            resp = requests.post(
                urljoin(self.base_url, '/api/v1/auth/login'),
                headers={'Authorization': f'Basic {encoded}'},
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data['responseBody']['accessToken']
            expires_in = data['responseBody'].get('expiresIn', 3600)
            self._token_expiry = datetime.now(timezone.utc).replace(second=0) + timedelta(seconds=expires_in - 60)
            self._log_call(url, 'POST', {'apiKey': '***', 'secret': '***'}, data, resp.status_code,
                           int((time.time() - start) * 1000), True)
            return self._token
        except Exception as e:
            self._log_call(url, 'POST', {'apiKey': '***', 'secret': '***'}, {'error': str(e)}, 0,
                           int((time.time() - start) * 1000), False)
            logger.error(f"Monnify auth failed: {e}")
            return None

    def _headers(self):
        token = self._get_token()
        if not token:
            return {'Content-Type': 'application/json'}
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }

    def create_reserved_account(self, profile):
        url_path = 'POST /api/v2/bank-transfer/reserved-accounts'
        url = urljoin(self.base_url, '/api/v2/bank-transfer/reserved-accounts')
        payload = {
            "accountReference": f"BS-{profile.profile_id}-{int(datetime.now().timestamp())}",
            "accountName": f"BabaSika - {profile.full_name}",
            "currencyCode": "NGN",
            "contractCode": self.contract_code,
            "customerEmail": profile.email or f"{profile.phone_number}@babasika.com",
            "customerName": profile.full_name,
            "getAllAvailableBanks": True,
        }

        start = time.time()
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            result = resp.json()
            duration = int((time.time() - start) * 1000)

            if result.get('requestSuccessful'):
                from payments.models import ReservedAccount
                body = result['responseBody']
                for account in body.get('accounts', []):
                    ReservedAccount.objects.update_or_create(
                        account_reference=body['accountReference'],
                        defaults={
                            'profile': profile,
                            'account_name': body['accountName'],
                            'account_number': account['accountNumber'],
                            'bank_name': account['bankName'],
                            'bank_code': account['bankCode'],
                        }
                    )
                self._log_call(url_path, 'POST', payload, result, resp.status_code, duration, True)
                return {"status": "success", "data": body}

            self._log_call(url_path, 'POST', payload, result, resp.status_code, duration, False)
            return {"status": "error", "message": result.get('responseMessage', 'Unknown error')}
        except requests.RequestException as e:
            duration = int((time.time() - start) * 1000)
            self._log_call(url_path, 'POST', payload, {'error': str(e)}, 0, duration, False)
            logger.error(f"Monnify create_reserved_account failed: {e}")
            return {"status": "error", "message": str(e)}

    def verify_bvn_account(self, bvn, account_number, bank_code):
        url_path = 'POST /api/v1/vas/bvn-account-match'
        url = urljoin(self.base_url, '/api/v1/vas/bvn-account-match')
        payload = {
            "bvn": bvn,
            "accountNumber": account_number,
            "bankCode": bank_code,
        }

        start = time.time()
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            result = resp.json()
            duration = int((time.time() - start) * 1000)
            self._log_call(url_path, 'POST', {'bvn': '***', 'accountNumber': account_number, 'bankCode': bank_code},
                           result, resp.status_code, duration, result.get('requestSuccessful', False))
            return result
        except requests.RequestException as e:
            duration = int((time.time() - start) * 1000)
            self._log_call(url_path, 'POST', {'bvn': '***', 'accountNumber': account_number, 'bankCode': bank_code},
                           {'error': str(e)}, 0, duration, False)
            logger.error(f"Monnify BVN match failed: {e}")
            return {"requestSuccessful": False, "responseMessage": str(e)}

    def single_transfer(self, amount, bank_code, account_number, account_name, narration, reference):
        url_path = 'POST /api/v2/disbursements/single'
        url = urljoin(self.base_url, '/api/v2/disbursements/single')
        payload = {
            "amount": float(amount),
            "reference": reference,
            "narration": narration,
            "destinationBankCode": bank_code,
            "destinationAccountNumber": account_number,
            "destinationAccountName": account_name,
            "currency": "NGN",
            "sourceAccountNumber": self.contract_code,
        }

        start = time.time()
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            result = resp.json()
            duration = int((time.time() - start) * 1000)
            success = result.get('requestSuccessful', False)
            self._log_call(url_path, 'POST', payload, result, resp.status_code, duration, success)
            return result
        except requests.RequestException as e:
            duration = int((time.time() - start) * 1000)
            self._log_call(url_path, 'POST', payload, {'error': str(e)}, 0, duration, False)
            logger.error(f"Monnify single transfer failed: {e}")
            return {"requestSuccessful": False, "responseMessage": str(e)}

    def create_direct_debit_mandate(self, profile, bank_code, account_number, max_amount):
        url_path = 'POST /api/v1/direct-debit/mandates'
        url = urljoin(self.base_url, '/api/v1/direct-debit/mandates')
        payload = {
            "customerEmail": profile.email or f"{profile.phone_number}@babasika.com",
            "customerName": profile.full_name,
            "accountNumber": account_number,
            "bankCode": bank_code,
            "mandateReference": f"MD-{profile.profile_id}-{int(datetime.now().timestamp())}",
            "maxAmount": float(max_amount),
            "currency": "NGN",
            "startDate": datetime.now().strftime('%Y-%m-%d'),
            "frequency": "Daily",
        }

        start = time.time()
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            result = resp.json()
            duration = int((time.time() - start) * 1000)
            success = result.get('requestSuccessful', False)
            self._log_call(url_path, 'POST', payload, result, resp.status_code, duration, success)
            return result
        except requests.RequestException as e:
            duration = int((time.time() - start) * 1000)
            self._log_call(url_path, 'POST', payload, {'error': str(e)}, 0, duration, False)
            logger.error(f"Monnify direct debit mandate failed: {e}")
            return {"requestSuccessful": False, "responseMessage": str(e)}
