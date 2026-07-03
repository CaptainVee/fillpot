import os

import dj_database_url

from .base import *

DEBUG = True

SECRET_KEY = os.environ["SECRET_KEY"]

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")

# DATABASES = {
#     "default": dj_database_url.config(
#         default=os.environ["DATABASE_URL"],
#         conn_max_age=600,
#         conn_health_checks=True,
#     )
# }

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
] + MIDDLEWARE[1:]

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

NOMBA_BASE_URL = "https://api.nomba.com/v1"
NOMBA_ACCOUNT_ID = os.environ["NOMBA_ACCOUNT_ID"]
NOMBA_CLIENT_ID = os.environ["NOMBA_CLIENT_ID"]
NOMBA_CLIENT_SECRET = os.environ["NOMBA_CLIENT_SECRET"]
NOMBA_WEBHOOK_SECRET = os.environ["NOMBA_WEBHOOK_SECRET"]

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
