import logging
from decimal import Decimal
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from twilio.twiml.messaging_response import MessagingResponse

from accounts.models import UserProfile
from .models import InboundMessageLog, WhatsAppPendingTransaction
from .services import conversation, intent as intent_service, ledger, stt
from .services.twilio_client import validate_twilio_request

logger = logging.getLogger(__name__)

CONFIRMATION_YES_PHRASES = ["yes", "confirm", "go ahead", "yes please", "do it", "yep", "sure", "proceed"]
CONFIRMATION_NO_PHRASES = ["no", "cancel", "don't", "dont", "stop", "nevermind"]


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    """
    Primary Twilio WhatsApp Webhook endpoint for BabaSika Phase 3.
    Supports GET (verification/healthcheck) and POST (incoming text & voice notes).
    """
    if request.method == "GET":
        return JsonResponse({"status": "active", "provider": "twilio_whatsapp"})

    if not validate_twilio_request(request):
        logger.warning("Twilio signature validation failed.")
        return HttpResponseForbidden("Invalid Twilio signature")

    message_sid = request.POST.get("MessageSid", "")
    from_number = request.POST.get("From", "").replace("whatsapp:", "").strip()
    body = request.POST.get("Body", "").strip()
    num_media = int(request.POST.get("NumMedia", "0") or "0")
    media_url = request.POST.get("MediaUrl0", "") if num_media else ""
    media_content_type = request.POST.get("MediaContentType0", "") if num_media else ""

    # Webhook Idempotency check to prevent duplicate message execution
    if message_sid and InboundMessageLog.objects.filter(message_sid=message_sid, processed=True).exists():
        logger.info(f"Duplicate Twilio webhook message received (MessageSid: {message_sid}). Ignoring.")
        return _twiml_reply("")

    user = conversation.get_user_by_phone(from_number)

    log_entry = InboundMessageLog.objects.create(
        user_profile=user,
        message_sid=message_sid,
        from_number=from_number,
        body=body,
        media_url=media_url,
        media_content_type=media_content_type,
        processed=True,
    )

    is_voice_note = num_media > 0 and media_content_type.startswith("audio")

    # 1. Unregistered User Flow -> Conversational Onboarding
    if not user:
        reply_text = conversation.handle_onboarding_message(from_number, body)
        return _twiml_reply(reply_text)

    # 2. Registered User Flow -> Check 2-Step Confirmation State
    clean_body = body.lower().strip()

    has_pending = WhatsAppPendingTransaction.objects.filter(
        user=user, status=WhatsAppPendingTransaction.Status.PENDING
    ).exists()

    if has_pending:
        if any(kw == clean_body or kw in clean_body.split() for kw in CONFIRMATION_YES_PHRASES):
            reply_text = ledger.confirm_pending_transaction(user)
            return _twiml_reply(reply_text)
        elif any(kw == clean_body or kw in clean_body.split() for kw in CONFIRMATION_NO_PHRASES):
            reply_text = ledger.cancel_pending_transaction(user)
            return _twiml_reply(reply_text)

    # 3. Process Input (Voice Note or Text Command)
    if is_voice_note:
        try:
            raw_transcript = stt.transcribe_media(media_url, media_content_type)
        except Exception as e:
            logger.error(f"STT transcription failed for {from_number}: {e}")
            return _twiml_reply("I couldn't receive or transcribe that voice note clearly. Please send it again or type your request.")
        parsed_intent = intent_service.extract_intent(raw_transcript, language=user.preferred_language)
    else:
        raw_transcript = body
        parsed_intent = intent_service.extract_intent(body, language=user.preferred_language)

    reply_text = _act_on_intent(user, parsed_intent, raw_transcript)
    return _twiml_reply(reply_text)


def _act_on_intent(user: UserProfile, parsed_intent: dict, raw_transcript: str) -> str:
    """Routes parsed NLU intents to the ledger engine."""
    intent_type = parsed_intent.get("intent")
    amount = parsed_intent.get("amount")
    currency = parsed_intent.get("currency", "NGN")

    if currency == "USD" or parsed_intent.get("error") == "UNSUPPORTED_CURRENCY":
        return "BabaSika currently handles savings in Nigerian Naira (₦). How much would you like to move in Naira?"

    if intent_type == "help":
        return (
            "I can help you with:\n\n"
            "1. Check my balance (e.g. \"how much do I have?\")\n"
            "2. Move/Save money (e.g. \"save 500 naira\")\n"
            "3. Check emergency savings (e.g. \"check contingent balance\")\n"
            "4. Check pension savings (e.g. \"check retirement balance\")\n"
            "5. View recent transactions\n\n"
            "You can type your request or send me a voice note!"
        )

    if intent_type == "check_balance":
        return ledger.get_balance_summary(user, filter_type="ALL")

    if intent_type == "check_contingent":
        return ledger.get_balance_summary(user, filter_type="CONTINGENT")

    if intent_type == "check_retirement":
        return ledger.get_balance_summary(user, filter_type="RETIREMENT")

    if intent_type == "transaction_history":
        return ledger.get_transaction_history_summary(user)

    if intent_type in ["move_money", "make_deposit"]:
        if not amount:
            return "How much would you like to save into your BabaSika micro-pension?"
        return ledger.propose_money_movement(user, Decimal(str(amount)), raw_transcript)

    if intent_type == "withdraw":
        return (
            f"Emergency withdrawal request for ₦{amount:,.2f} received. "
            f"Please specify your destination bank details or use the web dashboard."
            if amount else "How much would you like to withdraw from your liquid emergency buffer?"
        )

    return (
        "I didn't quite catch that action. You can send a voice note or type commands like:\n"
        "\"save 1000 naira\", \"check balance\", or type \"help\"."
    )


def _twiml_reply(message: str) -> HttpResponse:
    response = MessagingResponse()
    if message:
        response.message(message)
    return HttpResponse(str(response), content_type="application/xml")
