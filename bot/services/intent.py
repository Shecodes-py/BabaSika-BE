import re
import logging
from bmoni.ai_service import AIFinancialEngine

logger = logging.getLogger(__name__)


def extract_intent(transcript: str, language: str = "en") -> dict:
    """
    Extracts structured intent for Phase 3 WhatsApp commands.
    Supported intents:
      - move_money (or MAKE_DEPOSIT)
      - check_balance
      - check_contingent
      - check_retirement
      - transaction_history
      - withdraw
      - help
      - unknown
    The AI returns structured data ONLY — it NEVER authorizes or moves money.
    """
    text = (transcript or "").strip()
    if not text:
        return {
            "intent": "unknown",
            "amount": None,
            "currency": "NGN",
            "confidence": 0.0,
            "raw_text": "",
        }

    lower = text.lower()

    # Currency safety check ($ vs NGN)
    if "$" in text or "dollar" in lower or "usd" in lower:
        return {
            "intent": "move_money",
            "amount": None,
            "currency": "USD",
            "confidence": 0.9,
            "raw_text": text,
            "error": "UNSUPPORTED_CURRENCY",
        }

    # 1. Help intent
    if lower in ["help", "menu", "commands", "what can you do", "options"]:
        return {
            "intent": "help",
            "amount": None,
            "currency": "NGN",
            "confidence": 1.0,
            "raw_text": text,
        }

    # 2. Check balance intents
    if any(kw in lower for kw in ["contingent balance", "emergency balance", "liquid balance"]):
        return {
            "intent": "check_contingent",
            "amount": None,
            "currency": "NGN",
            "confidence": 0.95,
            "raw_text": text,
        }

    if any(kw in lower for kw in ["retirement balance", "pension balance", "locked balance"]):
        return {
            "intent": "check_retirement",
            "amount": None,
            "currency": "NGN",
            "confidence": 0.95,
            "raw_text": text,
        }

    if any(kw in lower for kw in ["balance", "how much", "wetin i get", "my money", "total"]):
        return {
            "intent": "check_balance",
            "amount": None,
            "currency": "NGN",
            "confidence": 0.95,
            "raw_text": text,
        }

    # 3. Transaction History intent
    if any(kw in lower for kw in ["transaction", "history", "recent", "statement", "activity"]):
        return {
            "intent": "transaction_history",
            "amount": None,
            "currency": "NGN",
            "confidence": 0.95,
            "raw_text": text,
        }

    # 4. Withdraw intent
    if any(kw in lower for kw in ["withdraw", "pull out", "collect emergency"]):
        amount = _extract_amount(lower)
        return {
            "intent": "withdraw",
            "amount": amount,
            "currency": "NGN",
            "confidence": 0.9 if amount else 0.5,
            "raw_text": text,
        }

    # 5. Move Money / Deposit intent
    deposit_kws = ["save", "move", "deposit", "put", "keep", "add", "pension", "waka", "hold"]
    has_deposit = any(kw in lower for kw in deposit_kws)
    amount = _extract_amount(lower)

    if has_deposit and amount:
        return {
            "intent": "move_money",
            "amount": amount,
            "currency": "NGN",
            "confidence": 0.95,
            "raw_text": text,
        }

    if has_deposit and not amount:
        return {
            "intent": "move_money",
            "amount": None,
            "currency": "NGN",
            "confidence": 0.5,
            "raw_text": text,
            "ambiguous": True,
        }

    if amount:
        # Number mentioned without clear verb
        return {
            "intent": "move_money",
            "amount": amount,
            "currency": "NGN",
            "confidence": 0.6,
            "raw_text": text,
        }

    # Default to AIFinancialEngine parser fallback
    parsed = AIFinancialEngine.extract_intent(text, language=language)
    return {
        "intent": parsed.get("intent", "unknown").lower(),
        "amount": parsed.get("amount") if parsed.get("amount") > 0 else None,
        "currency": "NGN",
        "confidence": parsed.get("confidence", 0.0),
        "raw_text": text,
    }


def _extract_amount(text: str) -> float | None:
    # 5k / 5.5k format
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*k\b", text)
    if k_match:
        return float(k_match.group(1)) * 1000.0

    # Digits format: ₦500 / 500 naira / 5,000
    num_match = re.search(r"[₦#]?\s*(\d[\d,]*)(?:\.\d+)?", text)
    if num_match:
        clean = num_match.group(1).replace(",", "")
        try:
            val = float(clean)
            if val > 0:
                return val
        except ValueError:
            pass

    # Spelled-out English words
    word_map = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "hundred": 100, "thousand": 1000,
    }
    tokens = re.findall(r"[a-z]+", text)
    if "hundred" in tokens or "thousand" in tokens:
        total = 0
        curr = 0
        for t in tokens:
            if t in word_map:
                v = word_map[t]
                if v == 100:
                    curr = (curr or 1) * 100
                elif v == 1000:
                    total += (curr or 1) * 1000
                    curr = 0
                else:
                    curr += v
        total += curr
        if total > 0:
            return float(total)

    return None
