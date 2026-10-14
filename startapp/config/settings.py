"""Settings for the Rentora project."""
import base64
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")
CHAT_MEDIA_ROOT = Path(os.environ.get("CHAT_MEDIA_ROOT") or BASE_DIR / "private-chat-media")
PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "").rstrip("/")

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-startapp-rental-dev-key-change-before-production",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1").strip().lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [host.strip() for host in os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver"
).split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get(
    "CSRF_TRUSTED_ORIGINS", ""
).split(",") if origin.strip()]
CLICK_SERVICE_ID = os.environ.get("CLICK_SERVICE_ID", "")
CLICK_MERCHANT_ID = os.environ.get("CLICK_MERCHANT_ID", "")
CLICK_SECRET_KEY = os.environ.get("CLICK_SECRET_KEY", "")
CLICK_CHECKOUT_BASE_URL = os.environ.get("CLICK_CHECKOUT_BASE_URL", "https://my.click.uz/services/pay")
PAYME_MERCHANT_ID = os.environ.get("PAYME_MERCHANT_ID", "")
PAYME_MERCHANT_KEY = os.environ.get("PAYME_MERCHANT_KEY", "")
PAYME_MERCHANT_AUTHORIZATION = (
    "Basic " + base64.b64encode(f"Paycom:{PAYME_MERCHANT_KEY}".encode()).decode()
    if PAYME_MERCHANT_KEY else ""
)
PAYME_CHECKOUT_BASE_URL = os.environ.get("PAYME_CHECKOUT_BASE_URL", "https://checkout.paycom.uz")
# AI: Google Gemini through its OpenAI-compatible chat completions endpoint.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
# Tried in order when the main model is overloaded or out of its (per-model) free quota.
GEMINI_FALLBACK_MODELS = [
    name.strip() for name in os.environ.get(
        "GEMINI_FALLBACK_MODELS",
        "gemini-2.5-flash,gemini-3-flash-preview,gemini-3.8-flash,gemini-flash-latest",
    ).split(",") if name.strip()
]
AI_API_URL = os.environ.get("AI_API_URL", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
TELEGRAM_BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "").lstrip("@")
# Support chat: the AI answers on the team's behalf when no admin replied within this delay.
SUPPORT_AI_ENABLED = os.environ.get("SUPPORT_AI_ENABLED", "1").strip().lower() in {"1", "true", "yes"}
SUPPORT_AI_DELAY_SECONDS = int(os.environ.get("SUPPORT_AI_DELAY_SECONDS", "120"))
# Django admin lives here; change it to something non-obvious in production.
ADMIN_URL = os.environ.get("ADMIN_URL", "admin/").strip("/") + "/"
# Set when a trusted reverse proxy (Caddy/nginx) in front of the app sets X-Real-IP.
TRUST_X_REAL_IP = os.environ.get("TRUST_X_REAL_IP", "").strip().lower() in {"1", "true", "yes"}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.security.SecurityMiddleware",
]

if not DEBUG:
    # Serve collected static files straight from gunicorn in production.
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
            "core.context_processors.ai_assistant",
        ],
    },
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(os.environ.get("SQLITE_PATH") or BASE_DIR / "db.sqlite3"),
        "OPTIONS": {"timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = Path(os.environ.get("STATIC_ROOT") or BASE_DIR / "staticfiles")
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT") or BASE_DIR / "media")
# Without a separate web server (nginx), let Django serve uploaded listing photos.
SERVE_MEDIA = DEBUG or os.environ.get("SERVE_MEDIA", "").strip().lower() in {"1", "true", "yes"}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Chat attachments (photos, videos, voice messages) may be up to 250 MB; bigger bodies are refused early.
CHAT_ATTACHMENT_MAX_BYTES = 250 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o640

# Rate limits are shared by all gunicorn workers through a file-based cache.
CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
        if "test" in sys.argv
        else {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": os.environ.get("CACHE_DIR") or str(BASE_DIR / ".cache"),
        }
    ),
}

CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob: https:",
    "media-src 'self' blob:",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "form-action 'self' https://my.click.uz https://checkout.paycom.uz https://test.paycom.uz",
    "base-uri 'self'",
    "object-src 'none'",
])
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "my-bookings"
LOGOUT_REDIRECT_URL = "home"

# Session-authenticated JSON API; Django's CSRF middleware remains enabled.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}

if not DEBUG:
    if SECRET_KEY.startswith("django-insecure"):
        raise RuntimeError("Set DJANGO_SECRET_KEY before running with DJANGO_DEBUG=0.")
    # Only mark cookies Secure when the site is actually served over HTTPS.
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = PUBLIC_SITE_URL.startswith("https://")
    CSRF_COOKIE_HTTPONLY = False  # The same-origin frontend reads the token for AJAX requests.
    if os.environ.get("DJANGO_BEHIND_HTTPS_PROXY", "").strip().lower() in {"1", "true", "yes"}:
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    if PUBLIC_SITE_URL.startswith("https://"):
        SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
        SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "1").strip().lower() in {"1", "true", "yes"}
        # The health check is called over plain HTTP inside the container.
        SECURE_REDIRECT_EXEMPT = [r"^health/$"]
