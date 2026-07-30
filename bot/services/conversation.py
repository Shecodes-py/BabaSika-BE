"""Conversational onboarding state machine.

Each inbound text message advances the user by exactly one stage. Deliberately
NOT a form dump — one question at a time, in plain language. Once every field
is collected we hand off to bmoni_client.register_new_saver() and reply with
the "you're in" moment from the PRD.

This module returns the WhatsApp reply text; it never sends messages itself
(views.py owns the actual Twilio response), which keeps it easy to unit test.
"""
import re

from ..models import Language, OnboardingStage, User
from . import bmoni_client

PFA_OPTIONS = ["ARM Pension", "Stanbic IBTC Pension", "Trustfund Pensions", "Leadway Pensure"]

LANGUAGE_ALIASES = {
    "english": Language.ENGLISH, "en": Language.ENGLISH,
    "yoruba": Language.YORUBA, "yo": Language.YORUBA,
    "hausa": Language.HAUSA, "ha": Language.HAUSA,
    "igbo": Language.IGBO, "ig": Language.IGBO,
    "pidgin": Language.PIDGIN, "pcm": Language.PIDGIN,
}


def get_or_create_user(phone_number: str) -> tuple[User, bool]:
    return User.objects.get_or_create(phone_number=phone_number)


def start_greeting() -> str:
    return (
        "Welcome to BabaSika.\n"
        "I can help you start saving for your future.\n"
        "You can type or send me a voice note.\n\n"
        "What should I call you?"
    )


def _looks_like_email(text: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text.strip()))


def _looks_like_nin_bvn(text: str) -> bool:
    digits = re.sub(r"\D", "", text)
    return len(digits) in (10, 11)  # BVN is 11 digits, NIN is 11; keep it loose for a demo


def handle_onboarding_message(user: User, body: str) -> str:
    """Advances the onboarding state machine by one step. Returns the reply."""
    text = (body or "").strip()
    stage = user.onboarding_stage

    if stage == OnboardingStage.NEW:
        user.onboarding_stage = OnboardingStage.ASK_NAME
        user.save(update_fields=["onboarding_stage"])
        return start_greeting()

    if stage == OnboardingStage.ASK_NAME:
        if not text:
            return "Sorry, I didn't catch that — what should I call you?"
        user.full_name = text.title()
        user.onboarding_stage = OnboardingStage.ASK_EMAIL
        user.save(update_fields=["full_name", "onboarding_stage"])
        return (
            f"Nice to meet you, {user.display_name}!\n"
            "What's your email address? (So I can send your statements.)"
        )

    if stage == OnboardingStage.ASK_EMAIL:
        if not _looks_like_email(text):
            return "That doesn't look like a valid email — mind sending it again?"
        user.email = text.lower()
        user.onboarding_stage = OnboardingStage.ASK_NIN
        user.save(update_fields=["email", "onboarding_stage"])
        return (
            "Got it. Now I need your NIN or BVN to register your retirement "
            "account with PenCom — it's just for verification, nothing leaves "
            "BabaSika."
        )

    if stage == OnboardingStage.ASK_NIN:
        if not _looks_like_nin_bvn(text):
            return "Hmm, that doesn't look like a valid NIN/BVN — it should be 10-11 digits. Try again?"
        user.nin_bvn = re.sub(r"\D", "", text)
        user.onboarding_stage = OnboardingStage.ASK_PFA
        user.save(update_fields=["nin_bvn", "onboarding_stage"])
        options = "\n".join(f"{i+1}. {name}" for i, name in enumerate(PFA_OPTIONS))
        return (
            "Do you already have a Pension Fund Administrator (PFA)? If not, "
            "here are a few good ones — just reply with a number or name:\n"
            f"{options}\n0. I don't know, pick one for me"
        )

    if stage == OnboardingStage.ASK_PFA:
        chosen = _resolve_pfa_choice(text)
        user.preferred_pfa = chosen
        user.onboarding_stage = OnboardingStage.ASK_LANGUAGE
        user.save(update_fields=["preferred_pfa", "onboarding_stage"])
        return (
            "Last thing — what language do you want me to speak with you in? "
            "English, Yoruba, Hausa, Igbo, or Pidgin?"
        )

    if stage == OnboardingStage.ASK_LANGUAGE:
        language = LANGUAGE_ALIASES.get(text.lower().strip())
        if not language:
            return "Just so I get it right — English, Yoruba, Hausa, Igbo, or Pidgin?"
        user.preferred_language = language
        user.onboarding_stage = OnboardingStage.PROVISIONING
        user.save(update_fields=["preferred_language", "onboarding_stage"])
        return _run_registration(user)

    # Already onboarded but somehow routed here — shouldn't normally happen.
    return "You're already all set up! Send me a voice note anytime to save."


def _resolve_pfa_choice(text: str) -> str:
    text = text.strip()
    if text == "0" or "don't know" in text.lower() or "dont know" in text.lower():
        return PFA_OPTIONS[0]
    if text.isdigit() and 1 <= int(text) <= len(PFA_OPTIONS):
        return PFA_OPTIONS[int(text) - 1]
    return text.title()  # user typed a PFA name we don't have listed — accept as free text


def _run_registration(user: User) -> str:
    """Runs the full BMONI orchestration chain and produces the
    "you're in" message. Synchronous for the hackathon demo; move to a
    Celery task if BMONI calls get slow in production."""
    try:
        bmoni_client.register_new_saver(user)
        user.onboarding_stage = OnboardingStage.ONBOARDED
        user.save()
    except bmoni_client.BMONIError:
        # Leave stage at PROVISIONING so the user can be nudged/retried.
        return (
            "I hit a snag registering your account with our banking partner. "
            "Give me a moment and try sending any message again."
        )

    return (
        f"You're in, {user.display_name}.\n"
        "Your BabaSika account is ready.\n\n"
        f"Contingent: ₦{user.contingent_balance:,.0f}\n"
        f"Retirement: ₦{user.retirement_balance:,.0f}\n\n"
        "When money comes in, BabaSika automatically puts 40% aside for "
        "emergencies and 60% toward retirement.\n\n"
        "Try it now — send me a voice note like: "
        "\"I made 4,850 naira today, put something aside for me.\""
    )
