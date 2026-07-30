import logging

from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from twilio.twiml.messaging_response import MessagingResponse

from .models import InboundMessageLog, OnboardingStage
from .services import conversation, intent as intent_service, ledger, stt
from .services.twilio_client import validate_twilio_request

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def whatsapp_webhook(request):
    """
    Twilio POSTs here on every inbound WhatsApp message. Flow:

      1. Look up / create the User by phone number.
      2. If there's audio media -> transcribe -> extract intent.
         Else -> if still onboarding, advance the state machine;
                 if onboarded, extract intent straight from the text body.
      3. MAKE_DEPOSIT intents go through the deterministic ledger, which is
         the only thing allowed to move money. Everything else just replies.
    """
    if not validate_twilio_request(request):
        return HttpResponseForbidden("Invalid Twilio signature")

    from_number = request.POST.get("From", "").replace("whatsapp:", "")
    body = request.POST.get("Body", "")
    num_media = int(request.POST.get("NumMedia", "0") or "0")
    media_url = request.POST.get("MediaUrl0", "") if num_media else ""
    media_content_type = request.POST.get("MediaContentType0", "") if num_media else ""

    user, _created = conversation.get_or_create_user(from_number)

    InboundMessageLog.objects.create(
        user=user,
        from_number=from_number,
        body=body,
        media_url=media_url,
        media_content_type=media_content_type,
    )

    is_voice_note = num_media > 0 and media_content_type.startswith("audio")

    if is_voice_note:
        reply = _handle_voice_note(user, media_url, media_content_type)
    elif not user.is_onboarded:
        reply = conversation.handle_onboarding_message(user, body)
    else:
        reply = _handle_onboarded_text(user, body)

    return _twiml_reply(reply)


def _handle_voice_note(user, media_url: str, content_type: str) -> str:
    transcript = stt.transcribe_media(media_url, content_type)
    parsed_intent = intent_service.extract_intent(transcript)
    return _act_on_intent(user, parsed_intent, source="VOICE_NOTE", raw_transcript=transcript)


def _handle_onboarded_text(user, body: str) -> str:
    parsed_intent = intent_service.extract_intent(body)
    return _act_on_intent(user, parsed_intent, source="TEXT", raw_transcript=body)


def _act_on_intent(user, parsed_intent: dict, source: str, raw_transcript: str) -> str:
    """Hands a structured {intent, amount, confidence} dict to the
    deterministic ledger. Never moves money itself."""
    intent_type = parsed_intent.get("intent")

    if intent_type == "CHECK_BALANCE":
        return (
            f"Here's where you stand, {user.display_name}:\n"
            f"Contingent: ₦{user.contingent_balance:,.2f}\n"
            f"Retirement: ₦{user.retirement_balance:,.2f}"
        )

    if intent_type == "MAKE_DEPOSIT":
        try:
            tx = ledger.process_deposit(
                user, parsed_intent, source=source, raw_transcript=raw_transcript
            )
        except ledger.LedgerValidationError as exc:
            logger.info("Deposit rejected for %s: %s", user.phone_number, exc)
            heard = parsed_intent.get("amount")
            if heard is None:
                return (
                    "I heard something about money but couldn't make out the "
                    "amount. Could you say the naira amount again?"
                )
            return (
                f"I heard ₦{heard:,} but I'm not confident enough to move it "
                "automatically. Reply with the exact amount to confirm, e.g. "
                f"\"save {heard}\"."
            )

        return (
            f"I heard ₦{tx.gross_amount:,.0f}.\n"
            f"I'm putting ₦{tx.contingent_credit:,.0f} into your Contingent wallet "
            f"and ₦{tx.retirement_credit:,.0f} into Retirement.\n\n"
            f"₦{tx.gross_amount:,.0f} saved."
        )

    return (
        "I didn't quite catch an action there. You can say things like "
        "\"I made 5,000 naira today, put something aside\" or ask for your balance."
    )


def _twiml_reply(message: str) -> HttpResponse:
    response = MessagingResponse()
    response.message(message)
    return HttpResponse(str(response), content_type="application/xml")
