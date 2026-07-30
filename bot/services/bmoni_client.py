"""BMONI open-banking / PFA integration layer.

This is the ONLY module allowed to talk to BMONI. It exposes the exact
orchestration steps from the PRD:

    POST /users -> BMONI user ID
    -> Create Contingent Smart Wallet
    -> Create Retirement Smart Wallet
    -> BMONI Nigeria onboarding
    -> KYC verification
    -> Mock PFA registration
    -> RSA PIN
    -> transfer (used later by the ledger engine on every deposit)

BMONI_MOCK_MODE=True (the default) fabricates realistic responses so the
registration flow and voice-note demo work end-to-end with zero external
dependencies. Flip it off and set BMONI_API_KEY/BMONI_BASE_URL to hit the
real API — the call sites in conversation.py and ledger.py don't change.
"""
import logging
import random
import string
import uuid

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class BMONIError(Exception):
    pass


def _mock_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _request(method: str, path: str, **kwargs) -> dict:
    if settings.BMONI_MOCK_MODE:
        raise BMONIError("_request() should not be called in mock mode")

    url = f"{settings.BMONI_BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {settings.BMONI_API_KEY}"}
    response = requests.request(method, url, headers=headers, timeout=15, **kwargs)
    if not response.ok:
        raise BMONIError(f"BMONI {method} {path} failed: {response.status_code} {response.text}")
    return response.json()


def create_bmoni_user(user) -> str:
    """POST /users -> BMONI user ID."""
    if settings.BMONI_MOCK_MODE:
        return _mock_id("bmoni_user")
    data = _request(
        "POST",
        "/users",
        json={"full_name": user.full_name, "email": user.email, "phone": user.phone_number},
    )
    return data["id"]


def create_wallet(bmoni_user_id: str, wallet_type: str) -> str:
    """wallet_type: 'CONTINGENT' or 'RETIREMENT'."""
    if settings.BMONI_MOCK_MODE:
        return _mock_id(f"wallet_{wallet_type.lower()}")
    data = _request(
        "POST",
        f"/users/{bmoni_user_id}/wallets",
        json={"type": wallet_type},
    )
    return data["id"]


def run_nigeria_onboarding(bmoni_user_id: str, nin_bvn: str) -> dict:
    """BMONI Nigeria onboarding step (BVN/NIN linkage, tier assignment)."""
    if settings.BMONI_MOCK_MODE:
        return {"status": "SUBMITTED", "tier": 2}
    return _request("POST", f"/users/{bmoni_user_id}/onboarding/ng", json={"nin_bvn": nin_bvn})


def verify_kyc(bmoni_user_id: str) -> str:
    """Returns one of: VERIFIED, PENDING, FAILED."""
    if settings.BMONI_MOCK_MODE:
        return "VERIFIED"
    data = _request("GET", f"/users/{bmoni_user_id}/kyc")
    return data["status"]


def register_pfa(bmoni_user_id: str, preferred_pfa: str) -> dict:
    """Mock PFA registration per the PRD's PenCom PPP flow. Even in real
    mode this typically returns a pending reference since PFA registration
    is asynchronous/batched."""
    if settings.BMONI_MOCK_MODE or True:
        # PFA registration is always simulated for the hackathon build —
        # real PFA APIs are batch/async and out of scope for the demo.
        return {"pfa": preferred_pfa or "Default PFA", "status": "REGISTERED", "ref": _mock_id("pfa")}
    return _request("POST", f"/users/{bmoni_user_id}/pfa", json={"pfa": preferred_pfa})


def issue_rsa_pin(bmoni_user_id: str) -> str:
    """Retirement Savings Account PIN — the PenCom-recognizable identifier."""
    if settings.BMONI_MOCK_MODE:
        digits = "".join(random.choices(string.digits, k=10))
        return f"PEN{digits}"
    data = _request("POST", f"/users/{bmoni_user_id}/rsa-pin")
    return data["rsa_pin"]


def transfer(wallet_id: str, amount) -> str:
    """Move `amount` into the given wallet. Returns a transfer reference.
    This is the ONLY function the ledger engine calls to actually move money —
    it never receives a raw AI instruction, only a validated amount."""
    if settings.BMONI_MOCK_MODE:
        logger.info("[BMONI MOCK] transfer ₦%s -> wallet %s", amount, wallet_id)
        return _mock_id("txn")
    data = _request("POST", f"/wallets/{wallet_id}/transfers", json={"amount": str(amount)})
    return data["reference"]


def register_new_saver(user) -> None:
    """Full registration orchestration exactly as sequenced in the PRD.
    Mutates `user` in place with BMONI identifiers; caller is responsible
    for saving."""
    user.bmoni_user_id = create_bmoni_user(user)
    user.contingent_wallet_id = create_wallet(user.bmoni_user_id, "CONTINGENT")
    user.retirement_wallet_id = create_wallet(user.bmoni_user_id, "RETIREMENT")

    run_nigeria_onboarding(user.bmoni_user_id, user.nin_bvn)
    user.kyc_status = verify_kyc(user.bmoni_user_id)

    pfa_result = register_pfa(user.bmoni_user_id, user.preferred_pfa)
    user.preferred_pfa = pfa_result["pfa"]

    user.rsa_pin = issue_rsa_pin(user.bmoni_user_id)
