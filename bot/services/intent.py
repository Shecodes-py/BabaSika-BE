"""Turns free text (from voice transcript or a typed WhatsApp message) into
a structured intent:

    {"intent": "MAKE_DEPOSIT", "amount": 4850, "confidence": 0.9}
    {"intent": "CHECK_BALANCE", "amount": None, "confidence": 0.95}
    {"intent": "UNKNOWN", "amount": None, "confidence": 0.0}

ARCHITECTURAL RULE (per the PRD): this module NEVER calls BMONI and NEVER
touches a wallet balance. It only returns data. bot/services/ledger.py is
the sole deterministic decision-maker that acts on that data — see
process_deposit_intent() in views.py for the handoff.

Two extraction strategies are provided:
  1. `_extract_rule_based` — regex + word-number parsing. Deterministic,
     free, and good enough for structured demo phrases. Used by default.
  2. `_extract_with_llm` — optional call to an LLM for messier phrasing
     (mixed Pidgin/English, unusual number formats). Enable by setting
     LLM_INTENT_EXTRACTION=true and ANTHROPIC_API_KEY.
"""
import os
import re

WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000,
}

DEPOSIT_KEYWORDS = ("put aside", "save", "made", "sold", "deposit", "earned", "collected")
BALANCE_KEYWORDS = ("balance", "how much", "how much i get", "wetin i get")

LLM_ENABLED = os.environ.get("LLM_INTENT_EXTRACTION", "false").lower() == "true"


def extract_intent(transcript: str) -> dict:
    transcript = (transcript or "").strip()
    if not transcript:
        return {"intent": "UNKNOWN", "amount": None, "confidence": 0.0}

    if LLM_ENABLED:
        try:
            return _extract_with_llm(transcript)
        except Exception:
            pass  # fall through to rule-based as a safety net

    return _extract_rule_based(transcript)


def _words_to_number(text: str) -> int | None:
    tokens = re.findall(r"[a-z]+", text.lower())
    total, current = 0, 0
    found_any = False
    for tok in tokens:
        if tok not in WORD_NUMBERS:
            continue
        found_any = True
        value = WORD_NUMBERS[tok]
        if value == 100:
            current = (current or 1) * 100
        elif value == 1000:
            total += (current or 1) * 1000
            current = 0
        else:
            current += value
    total += current
    return total if found_any else None


def _extract_rule_based(transcript: str) -> dict:
    lower = transcript.lower()

    # Amount: prefer an explicit digit amount (₦4,850 / 4850 naira), then
    # fall back to parsing spelled-out numbers ("four thousand eight
    # hundred and fifty").
    amount = None
    digit_match = re.search(r"[₦#]?\s?([\d][\d,]*)(?:\.\d+)?\s*(?:naira)?", transcript)
    if digit_match and any(ch.isdigit() for ch in digit_match.group(1)):
        cleaned = digit_match.group(1).replace(",", "")
        if cleaned.isdigit() and int(cleaned) > 0:
            amount = int(cleaned)

    if amount is None:
        amount = _words_to_number(lower)
        if amount == 0:
            amount = None

    if any(kw in lower for kw in BALANCE_KEYWORDS):
        return {"intent": "CHECK_BALANCE", "amount": None, "confidence": 0.9}

    if amount is not None and any(kw in lower for kw in DEPOSIT_KEYWORDS):
        return {"intent": "MAKE_DEPOSIT", "amount": amount, "confidence": 0.9}

    if amount is not None:
        # Number mentioned without a clear verb — still likely a deposit,
        # lower confidence so the webhook can ask for confirmation.
        return {"intent": "MAKE_DEPOSIT", "amount": amount, "confidence": 0.55}

    return {"intent": "UNKNOWN", "amount": None, "confidence": 0.0}


def _extract_with_llm(transcript: str) -> dict:
    """Optional LLM-backed extraction for messier phrasing. Requires the
    `anthropic` package and ANTHROPIC_API_KEY. Kept isolated so a provider
    outage never breaks the deposit flow — callers fall back to rule-based."""
    import json

    import anthropic

    client = anthropic.Anthropic()
    system = (
        "Extract a structured savings intent from the user's message. "
        "Respond ONLY with JSON: "
        '{"intent": "MAKE_DEPOSIT"|"CHECK_BALANCE"|"UNKNOWN", '
        '"amount": <integer naira amount or null>, "confidence": <0-1 float>}. '
        "No preamble, no markdown fences."
    )
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=system,
        messages=[{"role": "user", "content": transcript}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    data = json.loads(text.strip())
    return {
        "intent": data.get("intent", "UNKNOWN"),
        "amount": data.get("amount"),
        "confidence": float(data.get("confidence", 0.0)),
    }
