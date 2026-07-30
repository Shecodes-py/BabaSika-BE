# BabaSika Backend

Django 6 + DRF backend powering BabaSika, a micro-pension platform for Nigeria's informal workers. Every contribution is split **40% Contingent (emergency, unlocks after 90 days) / 60% Retirement (locked long-term)**. The backend orchestrates real accounts, wallets, and KYC on **BMONI's sandbox API**, and drives both the website and a WhatsApp/voice channel from one shared transaction engine.

---

## Apps

| App | Responsibility |
|---|---|
| `accounts` | `UserProfile`, `PFA` models; profile lookup, PFA listing, setup-status |
| `payments` | `Ledger`, `Transaction`, `TransactionAudit`; dashboard read model, money-movement (deposit/withdraw) |
| `bmoni` | `BMONIService` — the **only** module that calls BMONI; registration pipeline; AI intent/coach layer; API call logging |
| `bot` | Twilio WhatsApp webhook, 2-step confirm-before-execute flow, voice-note transcription |

---

## Quick Start

```bash
python -m venv venv
venv\Scripts\activate            # Windows; use `source venv/bin/activate` on macOS/Linux
pip install -r requirements.txt

cp .env.example .env             # then fill in real values, see below
python manage.py migrate
python manage.py runserver 8000
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BMONI_API_KEY` | **Yes** | — | Sandbox key for `x-api-key` header. Without this, every BMONI call gets a real `401`. |
| `BMONI_BASE_URL` | No | `https://embedded-dev.bmoni.com` | BMONI sandbox base URL |
| `BMONI_DEMO_FALLBACK` | No | `false` | **Read the warning below before enabling.** |
| `DJANGO_SECRET_KEY` | No | insecure dev key | Set a real value in production |
| `DJANGO_DEBUG` | No | `True` | Set `false` in production |
| `DATABASE_URL` | No | local SQLite | `postgres://user:pass@host:port/db` — used in production (Render) |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | No | — | Needed for the WhatsApp bot to actually send/receive |
| `TWILIO_WHATSAPP_NUMBER` | No | Twilio sandbox number | |
| `TWILIO_VALIDATE_SIGNATURE` | No | `false` | Set `true` once the webhook URL is public, or anyone can POST fake WhatsApp messages to it |
| `OPENAI_API_KEY` | No | — | Enables real Whisper transcription for voice notes |
| `STT_MOCK_MODE` | No | `true` | Set `false` (with a real `OPENAI_API_KEY`) to transcribe real audio instead of returning a canned transcript |
| `CONTINGENT_SPLIT_PCT` / `RETIREMENT_SPLIT_PCT` | No | `0.40` / `0.60` | The core split ratio |

### ⚠️ `BMONI_DEMO_FALLBACK`

When a BMONI call fails (network issue, sandbox downtime, unimplemented upstream feature), this flag decides what happens:

- **`false` (default):** the failure is real — logged, and returned to the caller as an honest error. Nothing is faked.
- **`true`:** registration, BVN lookup, and money-movement are guaranteed to report success even if the underlying BMONI call failed, so a demo never dies on stage. Every simulated response is still marked `"simulated": true` in the API payload and logged server-side, so it's always distinguishable from a genuine BMONI settlement if anyone inspects the response or the logs — it just isn't surfaced to the end user by default.

Turn this **off** for anything other than a live demo you can't afford to have interrupted by sandbox flakiness.

---

## API Reference

All routes below are mounted under `/api/v1/`.

### Accounts (`accounts/urls.py`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/pfas` | List active Pension Fund Administrators |
| GET | `/profile/<profile_id>` | Fetch a user profile |
| GET | `/account/setup-status` | Onboarding step status for a profile |

### Payments (`payments/urls.py`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/ledger/<profile_id>` | Contingent/Retirement/total balances |
| GET | `/transactions/<profile_id>` | Last 50 transactions |
| GET | `/dashboard?profile_id=...` | Combined dashboard read model |
| POST | `/money-movement/split` | Contribute — 40/60 split, custody settlement attempted on BMONI |
| POST | `/money-movement/withdraw` | Withdraw from Contingent (90-day cliff enforced unless `force_override`) |

### BMONI (`bmoni/urls.py`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/onboard` | Full registration: create BMONI user → provision smart wallets → sandbox KYC → activate Nigerian rail. **Resumable** — a retry after a partial failure picks up from whatever already succeeded instead of re-running steps BMONI will reject as duplicates. |
| POST | `/kyc/bvn-lookup` | BVN verification via BMONI sandbox |
| POST | `/bmoni/deposit` | Legacy single-endpoint deposit (superseded by `money-movement/split`, still active) |
| POST | `/bmoni/voice-webhook` | Text/voice command → intent → deposit |
| POST | `/bmoni/advisor` | AI financial advisor report |
| POST | `/ai-coach/ask` | Ask-a-question financial coach |
| POST | `/ai-coach/explain-transaction` | Plain-language explanation of a specific transaction |
| GET | `/bmoni/balances/<profile_id>` | Ledger balances + live BMONI wallet balances |
| GET | `/bmoni/transactions/<profile_id>` | Local audit trail + live BMONI transactions |
| GET | `/bmoni/api-log` | Last 50 real BMONI API calls (request/response/status/duration) — the transparency log |

### Bot (`bot/urls.py`, mounted at `/bot/`, not `/api/v1/`)
| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/bot/whatsapp/` | Twilio WhatsApp webhook — onboarding, 2-step confirm-then-execute money movement, voice note transcription |

---

## Architecture

```
Website ──┐
          ├──► Django backend ──► BMONIService (bmoni/client.py) ──► BMONI sandbox
WhatsApp ─┘         │
                     ├──► Ledger (40/60 allocation, authoritative)
                     └──► TransactionAudit (audit trail: SUCCESS / PENDING_SETTLEMENT / FAILED)
```

**Custody model:** BMONI's smart wallet is the custody account; BabaSika's `Ledger` is authoritative for how that balance is *allocated* 40/60. Every contribution attempts real BMONI settlement first (`BMONIService.execute_transfer` → `POST /v1/users/{id}/smart-wallets/fund`); the allocation is always recorded in the ledger regardless of whether settlement completes, and the `TransactionAudit.status` records which actually happened.

**Single transaction engine:** `payments.views.money_movement_split` (website) and `bmoni.views.process_pension_deposit` (WhatsApp) both perform the same 40/60 split and BMONI settlement attempt — kept in sync by hand today; a future pass should merge them into one shared function.

**AI is honestly a rules engine, not an LLM call.** `bmoni/ai_service.py` and `bmoni/financial_coach.py` do keyword/pattern matching against a curated multilingual answer bank (English/Pidgin/Yoruba/Hausa/Igbo) — no OpenAI/Claude/Gemini request happens in that path. The one place real model inference *can* run is `bot/services/stt.py`, which calls OpenAI Whisper for voice-note transcription when `STT_MOCK_MODE=false` and a real `OPENAI_API_KEY` is set. AI never decides the split, never calls BMONI, and never holds credentials — it only extracts structured intent (`{intent, amount, confidence}`) for the backend to validate.

---

## BMONI Endpoints Actually Used

Confirmed against BMONI's live OpenAPI spec (`https://embedded-dev.bmoni.com/docs/openapi.json`):

| Endpoint | Used for |
|---|---|
| `POST /v1/users` | Create user |
| `POST /v1/users/{id}/smart-wallets/owner-proof-challenges` + `.../create-managed` | Provision a smart wallet (ECDSA owner-proof signing) |
| `POST /v1/users/{id}/onboarding/start-nigeria` + `GET .../onboarding/status` | Sandbox KYC + Nigerian rail activation |
| `GET /v1/users/{id}/kyc/bvn-lookup/{bvn}` | BVN verification |
| `GET /v1/users/{id}/smart-wallets/account/wallets` / `.../account/balances` | Read wallet state |
| `GET /v1/users/{id}/smart-wallets/{walletId}/transactions` | Read wallet transactions |
| `POST /v1/users/{id}/smart-wallets/fund` | Fund a smart wallet from a personal wallet |

## Known Limitations

- **Wallet funding has no source in the sandbox.** `smart-wallets/fund` requires a `fromWalletId` (a *personal* wallet), and BMONI's partner API currently exposes no route to create one for partner-created users — so real settlement can't complete yet. This is a platform gap, not a bug; `BMONI_DEMO_FALLBACK` exists specifically to keep the product usable while this is unresolved upstream.
- **Wallet dedup bug:** `provision_smart_wallet()` has a "reuse existing wallet" shortcut that doesn't check *which* wallet it's returning, so a fresh registration's Contingent and Retirement `smart_wallet_id` can end up identical. Not yet fixed.
- Two files (`bmoni.views.process_pension_deposit`, `payments.views.money_movement_split`) independently implement the same transfer logic — a bug fix or split-ratio change currently has to be applied in both places.

---

## Deploy to Render

`render.yaml` is included for blueprint deploys. **Set these in the Render dashboard** (not committed — they're secrets):

- `BMONI_API_KEY`, `BMONI_BASE_URL`
- `BMONI_DEMO_FALLBACK` (recommended `true` for a live demo)
- Optionally `TWILIO_*`, `OPENAI_API_KEY`, `STT_MOCK_MODE=false` for WhatsApp/voice in production

Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
Start command: `gunicorn babasika_backend.wsgi:application --workers 4`
