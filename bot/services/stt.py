"""Speech-to-text for inbound WhatsApp voice notes.

Swap `_transcribe_with_whisper` for whatever provider you land on (OpenAI
Whisper API, Google Speech-to-Text, an in-house Yoruba/Hausa/Igbo/Pidgin
model, etc.) — the webhook only ever calls `transcribe_media()`.
"""
import io
import logging

import requests
from django.conf import settings

from .twilio_client import download_media

logger = logging.getLogger(__name__)


def transcribe_media(media_url: str, content_type: str) -> str:
    if settings.STT_MOCK_MODE:
        logger.info("[STT MOCK] returning canned transcript for %s", media_url)
        return settings.STT_MOCK_TRANSCRIPT

    audio_bytes = download_media(media_url)
    return _transcribe_with_whisper(audio_bytes, content_type)


def _transcribe_with_whisper(audio_bytes: bytes, content_type: str) -> str:
    """OpenAI Whisper API transcription. Whisper auto-detects language,
    which covers Pidgin/English reasonably; Yoruba/Hausa/Igbo accuracy will
    vary and may need a specialized model down the line."""
    if not settings.OPENAI_API_KEY:
        raise RuntimeError(
            "STT_MOCK_MODE is off but OPENAI_API_KEY is not set. "
            "Set OPENAI_API_KEY or switch STT_MOCK_MODE back to true."
        )

    files = {"file": ("note.ogg", io.BytesIO(audio_bytes), content_type or "audio/ogg")}
    data = {"model": "whisper-1"}
    headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}

    response = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers=headers,
        files=files,
        data=data,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["text"]
