import re
import logging
from django.db import transaction
from accounts.models import UserProfile, PFA
from payments.models import Ledger
from bmoni.client import BMONIService
from ..models import WhatsAppOnboarding, OnboardingStage

logger = logging.getLogger(__name__)
bmoni_service = BMONIService()

PFA_OPTIONS = ["ARM Pension", "Stanbic IBTC Pension", "Trustfund Pensions", "Leadway Pensure"]

LANGUAGE_ALIASES = {
    "english": "en", "en": "en",
    "pidgin": "pidgin", "pcm": "pidgin",
    "yoruba": "yoruba", "yo": "yoruba",
    "hausa": "hausa", "ha": "hausa",
    "igbo": "igbo", "ig": "igbo",
}


def get_user_by_phone(phone_number: str) -> UserProfile | None:
    """Look up active UserProfile by E.164 phone number."""
    clean_phone = phone_number.strip()
    return UserProfile.objects.filter(phone_number=clean_phone).first()


def handle_onboarding_message(phone_number: str, body: str) -> str:
    """
    Drives conversational onboarding for unregistered WhatsApp phone numbers.
    Once complete, executes the exact same BMONI registration pipeline as the website.
    """
    text = (body or "").strip()
    onboarding, _ = WhatsAppOnboarding.objects.get_or_create(phone_number=phone_number)
    stage = onboarding.stage

    if stage == OnboardingStage.NEW:
        onboarding.stage = OnboardingStage.ASK_NAME
        onboarding.save(update_fields=["stage"])
        return (
            "Welcome to BabaSika! 🌾\n"
            "I can help you build automatic savings (40% liquid emergency / 60% locked retirement pension).\n\n"
            "I don't have an account for this phone number yet. Let's create one right here!\n"
            "First, what is your full name?"
        )

    if stage == OnboardingStage.ASK_NAME:
        if not text or len(text) < 2:
            return "Sorry, I didn't catch that — what is your full name?"
        onboarding.full_name = text.title()
        onboarding.stage = OnboardingStage.ASK_EMAIL
        onboarding.save(update_fields=["full_name", "stage"])
        return (
            f"Nice to meet you, {onboarding.full_name.split()[0]}!\n"
            "What's your email address? (Reply 'skip' if you don't have one)"
        )

    if stage == OnboardingStage.ASK_EMAIL:
        if text.lower() != "skip" and not _looks_like_email(text):
            return "That doesn't look like a valid email address. Mind sending it again or reply 'skip'?"
        onboarding.email = text.lower() if text.lower() != "skip" else ""
        onboarding.stage = OnboardingStage.ASK_PFA
        onboarding.save(update_fields=["email", "stage"])
        options = "\n".join(f"{i+1}. {name}" for i, name in enumerate(PFA_OPTIONS))
        return (
            "Which Pension Fund Administrator (PFA) would you like to use?\n"
            f"{options}\n0. Pick one for me"
        )

    if stage == OnboardingStage.ASK_PFA:
        chosen_pfa = _resolve_pfa_choice(text)
        onboarding.preferred_pfa = chosen_pfa
        onboarding.stage = OnboardingStage.ASK_LANGUAGE
        onboarding.save(update_fields=["preferred_pfa", "stage"])
        return (
            "What language do you prefer to speak with me in?\n"
            "English, Pidgin, Yoruba, Hausa, or Igbo?"
        )

    if stage == OnboardingStage.ASK_LANGUAGE:
        lang = LANGUAGE_ALIASES.get(text.lower().strip(), "en")
        onboarding.preferred_language = lang
        onboarding.stage = OnboardingStage.PROVISIONING
        onboarding.save(update_fields=["preferred_language", "stage"])
        return _execute_unified_bmoni_onboarding(onboarding)

    return "Your onboarding is being processed. Send any message to retry."


def _looks_like_email(text: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text.strip()))


def _resolve_pfa_choice(text: str) -> str:
    text = text.strip()
    if text == "0" or "don't know" in text.lower() or "pick" in text.lower():
        return PFA_OPTIONS[0]
    if text.isdigit() and 1 <= int(text) <= len(PFA_OPTIONS):
        return PFA_OPTIONS[int(text) - 1]
    return text.title()


def _execute_unified_bmoni_onboarding(onboarding: WhatsAppOnboarding) -> str:
    """
    Executes the exact same BMONI onboarding pipeline used by the website:
    Create User -> Provision Smart Wallets via Owner Proof -> Complete Sandbox KYC -> Activate NGN Rail.
    """
    try:
        with transaction.atomic():
            pfa = PFA.objects.filter(is_active=True).first()

            user = UserProfile.objects.create(
                full_name=onboarding.full_name,
                phone_number=onboarding.phone_number,
                email=onboarding.email or f"{onboarding.phone_number.replace('+', '')}@babasika.com",
                preferred_language=onboarding.preferred_language,
                pfa=pfa,
                onboarding_status='PROCESSING',
            )

            # Step 1: Create BMONI user
            bmoni_user_id = bmoni_service.create_user(
                first_name=user.full_name.split()[0],
                email=user.email,
                phone_number=user.phone_number,
            )
            user.bmoni_user_id = bmoni_user_id
            user.onboarding_status = 'USER_CREATED'
            user.save()

            # Step 2: Provision Smart Wallets via ECDSA owner proof challenge
            contingent_wallet = bmoni_service.provision_smart_wallet(bmoni_user_id, 'CNGN')
            user.contingent_smart_wallet_id = contingent_wallet['smartWalletId']
            user.contingent_wallet_address = contingent_wallet['smartWalletAddress']

            retirement_wallet = bmoni_service.provision_smart_wallet(bmoni_user_id, 'CNGN')
            user.retirement_smart_wallet_id = retirement_wallet['smartWalletId']
            user.retirement_wallet_address = retirement_wallet['smartWalletAddress']
            user.save()

            # Step 3 & 4: Sandbox KYC & Activate Nigerian NGN Rail
            bmoni_service.complete_sandbox_kyc_and_activate_rail(
                bmoni_user_id,
                contingent_wallet['smartWalletAddress'],
                wallet_index=0,
            )
            user.onboarding_status = 'ACTIVE'
            user.save()

            # Initialize Ledger
            Ledger.objects.get_or_create(profile=user)

            onboarding.stage = OnboardingStage.COMPLETED
            onboarding.save()

        first_name = user.full_name.split()[0]
        return (
            f"You're all set, {first_name}! 🎉\n"
            "Your BabaSika micro-pension account and BMONI smart wallets are ready.\n\n"
            "Every deposit is split:\n"
            "• 40% → Liquid Emergency Buffer\n"
            "• 60% → Locked Retirement Pension\n\n"
            "Try it now! Send a text or voice note like:\n"
            "\"save 500 naira\" or \"what's my balance?\""
        )

    except Exception as e:
        logger.error(f"WhatsApp unified onboarding failed: {e}")
        onboarding.stage = OnboardingStage.ASK_LANGUAGE
        onboarding.save()
        return (
            "I hit a snag completing your BMONI account registration. "
            "Please send any message to try again."
        )
