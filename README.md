# BabaSika Backend — Monnify Pension API

Django 6 + DRF backend that powers BabaSika's non-custodial micro-pension platform. Every deposit is split **40% emergency / 60% retirement** and the locked portion is disbursed to a licensed PFA custodian — all through Monnify's APIs.

---

## Quick Start

```bash
# Clone & enter
cd babasika-backend

# Install
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env with your Monnify sandbox keys

# Run
python manage.py migrate
python manage.py runserver 8000
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `MONNIFY_API_KEY` | Yes | — | Monnify sandbox API key |
| `MONNIFY_SECRET` | Yes | — | Monnify sandbox secret |
| `MONNIFY_CONTRACT_CODE` | Yes | — | Monnify contract code |
| `MONNIFY_BASE_URL` | No | `https://sandbox.monnify.com` | Monnify API base URL |
| `DJANGO_SECRET_KEY` | No | auto-generated | Django secret key |
| `DJANGO_DEBUG` | No | `True` | Debug mode |
| `DATABASE_URL` | No | SQLite local | PostgreSQL connection string (Render) |
| `CORS_ALLOWED_ORIGINS` | No | localhost + Vercel | Allowed frontend origins |

---

## API Reference

### Accounts

#### `GET /api/v1/pfas`
List all licensed PFAs.

**Response:**
```json
{
  "status": "success",
  "data": [
    { "id": 1, "name": "Trustcore PFA", "short_code": "TRUSTCORE", "is_active": true }
  ]
}
```

#### `POST /api/v1/onboard`
Create user + generate Monnify reserved account.

**Request:**
```json
{
  "full_name": "Chioma Okafor",
  "phone_number": "08012345678",
  "preferred_language": "en",
  "pfa_id": 1
}
```

**Response:**
```json
{
  "status": "success",
  "data": {
    "profile": { "profile_id": "uuid", "full_name": "...", ... },
    "reserved_account": {
      "accountReference": "BS-...",
      "accountName": "BabaSika - Chioma Okafor",
      "accounts": [
        { "bankName": "Wema Bank", "accountNumber": "9912345678", "bankCode": "035" }
      ]
    }
  }
}
```

#### `GET /api/v1/profile/:profile_id`
Get user profile + reserved account details.

---

### Ledger & Payments

#### `GET /api/v1/ledger/:profile_id`
Get wallet balances.

**Response:**
```json
{
  "status": "success",
  "data": {
    "contingent_balance": "4000.00",
    "retirement_balance": "6000.00",
    "total_contributions": "10000.00"
  }
}
```

#### `GET /api/v1/transactions/:profile_id`
Get last 50 transactions.

#### `GET /api/v1/reserved-account/:profile_id`
Get user's Monnify reserved account.

#### `POST /api/v1/withdraw-emergency`
Withdraw from emergency wallet to user's bank account via Monnify Single Transfer.

**Request:**
```json
{
  "profile_id": "uuid",
  "amount": 2000,
  "bank_code": "035",
  "account_number": "0123456789",
  "account_name": "Chioma Okafor"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "₦2000 disbursed to Chioma Okafor",
  "data": {
    "reference": "WTH-uuid-1234567890",
    "amount": "2000.00",
    "new_balance": "2000.00",
    "destination": { "bank_code": "035", "account_number": "0123456789", "account_name": "Chioma Okafor" },
    "monnify_response": { ... }
  }
}
```

---

### Monnify Integration

#### `POST /api/v1/monnify/webhook`
Receive Monnify payment notification. Processes 40/60 split and triggers PFA disbursement.

**Monnify sends:**
```json
{
  "eventType": "SUCCESSFUL_TRANSACTION",
  "eventData": {
    "amountPaid": 10000,
    "paymentReference": "MNFY-...",
    "accountReference": "BS-...",
    "paidOn": "2026-07-21T12:00:00",
    "paymentMethod": "TRANSFER",
    "customer": { "email": "...", "name": "..." }
  }
}
```

#### `POST /api/v1/monnify/verify-payer`
Verify user identity for POS agent pay-ins.

**Request:** `{ "identifier": "08012345678" }`

**Response:**
```json
{
  "status": "success",
  "data": {
    "verified": true,
    "full_name": "Chioma Okafor",
    "phone_number": "08012345678",
    "is_active": true,
    "reserved_account": { "bank_name": "Wema Bank", "account_number": "9912345678" }
  }
}
```

#### `POST /api/v1/monnify/simulate-payment`
Demo endpoint that simulates an incoming payment. Triggers the same webhook processing pipeline.

**Request:** `{ "profile_id": "uuid", "amount": 5000 }`

#### `GET /api/v1/monnify/api-log`
View last 50 Monnify API calls with full request/response bodies. Every outbound call to Monnify is logged here.

---

## Architecture

```
User sends money to Reserved Account
         │
Monnify fires webhook → POST /api/v1/monnify/webhook
         │
Backend splits: 40% contingent, 60% retirement
         │
Updates Ledger in PostgreSQL
         │
Calls POST /api/v2/disbursements/single → PFA custodian (60%)
         │
User clicks withdraw → POST /api/v1/withdraw-emergency
         │
Calls POST /api/v2/disbursements/single → user's bank (40%)
```

---

## Monnify APIs Used

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/auth/login` | Authentication (auto, cached) |
| `POST /api/v2/bank-transfer/reserved-accounts` | Virtual account per user |
| `POST /api/v1/vas/bvn-account-match` | KYC verification |
| `POST /api/v2/disbursements/single` | PFA payout & emergency withdrawal |
| `POST /api/v1/direct-debit/mandates` | Direct debit for gig workers |

---

## Deploy to Render

1. Push this repo to GitHub
2. On Render, create a **Web Service** pointing to the repo
3. Set build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
4. Set start command: `gunicorn babasika_backend.wsgi:application --workers 4`
5. Add a **PostgreSQL** database from Render's dashboard
6. Set environment variables: `MONNIFY_API_KEY`, `MONNIFY_SECRET`, `MONNIFY_CONTRACT_CODE`

A `render.yaml` is included for blueprint (Infrastructure-as-Code) deploys.
