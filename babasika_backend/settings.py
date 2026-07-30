import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-change-me-in-production')

DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'accounts',
    'payments',
    'bmoni',
    "bot",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'babasika_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'babasika_backend.wsgi.application'

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

import re

DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    m = re.match(r'postgres://(.+):(.+)@(.+):(\d+)/(.+)', DATABASE_URL)
    if m:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': m.group(5),
                'USER': m.group(1),
                'PASSWORD': m.group(2),
                'HOST': m.group(3),
                'PORT': m.group(4),
            }
        }
    else:
        DATABASES = {
            'default': {
                'ENGINE': os.getenv('DB_ENGINE', 'django.db.backends.postgresql'),
                'NAME': os.getenv('DB_NAME', 'babasika'),
                'USER': os.getenv('DB_USER', 'babasika_user'),
                'PASSWORD': os.getenv('DB_PASSWORD', ''),
                'HOST': os.getenv('DB_HOST', 'localhost'),
                'PORT': os.getenv('DB_PORT', '5432'),
            }
        }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Lagos'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
}

BMONI_BASE_URL = os.getenv('BMONI_BASE_URL', 'https://embedded-dev.bmoni.com')
BMONI_API_KEY = os.getenv('BMONI_API_KEY', '')

# Demo fallback for BMONI sandbox gaps.
#
# When True, BMONI operations that cannot complete against the sandbox
# (transfer settlement, BVN lookup, onboarding steps) return a SIMULATED
# success instead of an error, so a live demo cannot be blocked by a sandbox
# limitation.
#
# IMPORTANT: with this ON the UI will report these operations as succeeding
# even though no BMONI call succeeded. Real API failures are still recorded
# truthfully in BmoniApiLog, and simulated results are marked `simulated: True`
# in API responses. Set to false to see true BMONI behaviour.
BMONI_DEMO_FALLBACK = os.getenv('BMONI_DEMO_FALLBACK', 'false').lower() == 'true'

# --- Twilio ---------------------------------------------------------------
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
TWILIO_VALIDATE_SIGNATURE = os.environ.get("TWILIO_VALIDATE_SIGNATURE", "false").lower() == "true"

# --- Speech-to-text provider ------------------------------------------------
STT_MOCK_MODE = os.environ.get("STT_MOCK_MODE", "true").lower() == "true"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
STT_MOCK_TRANSCRIPT = os.environ.get(
    "STT_MOCK_TRANSCRIPT",
    "BabaSika, I made four thousand eight hundred and fifty naira today. Put something aside for me.",
)

# --- Ledger config ----------------------------------------------------------
CONTINGENT_SPLIT_PCT = float(os.environ.get("CONTINGENT_SPLIT_PCT", "0.40"))
RETIREMENT_SPLIT_PCT = float(os.environ.get("RETIREMENT_SPLIT_PCT", "0.60"))
