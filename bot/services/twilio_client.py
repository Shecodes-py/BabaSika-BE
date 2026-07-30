"""Thin wrapper around Twilio's WhatsApp API.

Two jobs only:
1. Send outbound WhatsApp text (used for async replies, e.g. after slow
   BMONI provisioning completes).
2. Fetch inbound media (voice notes) so we can hand the raw bytes to STT.

Nothing here decides anything — it's I/O plumbing.
"""
import logging

import requests
from django.conf import settings
from twilio.request_validator import RequestValidator
from twilio.rest import Client

logger = logging.getLogger(__name__)


def get_twilio_client() -> Client:
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def send_whatsapp_message(to_number: str, body: str) -> None:
    """Send a WhatsApp message outside of a webhook response (e.g. from a
    background task once BMONI provisioning finishes)."""
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        logger.info("[TWILIO MOCK] to=%s body=%s", to_number, body)
        return

    client = get_twilio_client()
    to = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}"
    client.messages.create(from_=settings.TWILIO_WHATSAPP_NUMBER, to=to, body=body)


def validate_twilio_request(request) -> bool:
    """Verify the X-Twilio-Signature header so random POSTs to our webhook
    can't spoof BMONI-triggering messages. Toggle off for local dev."""
    if not settings.TWILIO_VALIDATE_SIGNATURE:
        return True

    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    signature = request.META.get("HTTP_X_TWILIO_SIGNATURE", "")
    url = request.build_absolute_uri()
    return validator.validate(url, request.POST.dict(), signature)


def download_media(media_url: str) -> bytes:
    """Twilio media URLs require basic auth with your account credentials."""
    response = requests.get(
        media_url,
        auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
        timeout=20,
    )
    response.raise_for_status()
    return response.content
