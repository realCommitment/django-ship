# Production blocks adapted from cookiecutter-django, Copyright (c) 2013-2020 Daniel Roy Greenfeld, BSD-3-Clause.
import os

import sentry_sdk
from django.core.exceptions import ImproperlyConfigured
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

# settings.py derives the Vite dev server, browser reload, template caching and the cache backend from DEBUG
# when it is imported, so production turns DEBUG off before that, whatever the environment says.
os.environ["DEBUG"] = "False"

from .settings import *

# Note: it is recommended to use the "DEBUG" environment variable to override this value in your main settings.py file.
# A future release may remove it from here.
DEBUG = False

SECRET_KEY = env("SECRET_KEY")

# fix ssl mixed content issues
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Django security checklist settings.
# More details here: https://docs.djangoproject.com/en/stable/howto/deployment/checklist/
SECURE_SSL_REDIRECT = True
# Railway's health check uses plain HTTP and should get the real answer, not a redirect.
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HTTP Strict Transport Security settings
# https://docs.djangoproject.com/en/stable/ref/middleware/#http-strict-transport-security
# Raise SECURE_HSTS_SECONDS once go-live has proven HTTPS on every domain.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60)
# includeSubDomains and preload stay off: many unrelated domains share this deployment,
# and preload is a permanent commitment. These are their two check --deploy warnings.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]

USE_HTTPS_IN_ABSOLUTE_URLS = True

# Empty is allowed because the worker serves no requests. On the web service an empty list fails
# check --deploy (security.W020) and answers every request with 400.
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
# Railway's health checks arrive with this host (https://docs.railway.com/deployments/healthchecks),
# and the service's generated railway.app domain is set by Railway.
ALLOWED_HOSTS.append("healthcheck.railway.app")
if RAILWAY_PUBLIC_DOMAIN := env("RAILWAY_PUBLIC_DOMAIN", default=None):
    ALLOWED_HOSTS.append(RAILWAY_PUBLIC_DOMAIN)

DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
# A persistent connection dropped by a Postgres restart is replaced instead of failing the next request.
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# Static files are served by whitenoise. Not the Manifest variant: Pegasus warns it can break CSS image
# references, and Vite already hashes its chunks.
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1, "whitenoise.middleware.WhiteNoiseMiddleware"
)
STORAGES["staticfiles"] = {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"}

# Uploads go to the Railway storage bucket through django-storages' S3 backend. The bucket is required:
# without it uploads would land on the container disk and vanish at the next deploy.
# Railway buckets are private, so file URLs are presigned (django-storages' default) and use virtual-hosted style.
# https://docs.railway.com/storage-buckets
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME")
AWS_S3_ADDRESSING_STYLE = "virtual"
AWS_S3_FILE_OVERWRITE = False  # a second upload with the same name gets a new name instead of replacing the first
STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage"}

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
SERVER_EMAIL = env("SERVER_EMAIL")
# settings.py's *.localhost defaults are for development only.
SITES["directory"]["domain"] = env("DIRECTORY_DOMAIN")
SITES["directory"]["from_email"] = env("DIRECTORY_FROM_EMAIL")
SITES["productivity"]["domain"] = env("PRODUCTIVITY_DOMAIN")
SITES["productivity"]["from_email"] = env("PRODUCTIVITY_FROM_EMAIL")

# Billing needs the Stripe mode chosen, and the secret key of that mode; the other mode's key may stay empty.
STRIPE_LIVE_MODE = env.bool("STRIPE_LIVE_MODE")
if STRIPE_LIVE_MODE:
    STRIPE_LIVE_SECRET_KEY = env("STRIPE_LIVE_SECRET_KEY")
else:
    STRIPE_TEST_SECRET_KEY = env("STRIPE_TEST_SECRET_KEY")
# Without its own portal configuration a site gets Stripe's default portal, which can offer other sites' plans.
if missing := [key for key, site in SITES.items() if not site.get("stripe_portal_configuration")]:
    raise ImproperlyConfigured(
        f"No Stripe portal configuration for {', '.join(missing)}: run manage.py create_portal_configurations "
        "and set <SITE>_STRIPE_PORTAL_CONFIGURATION"
    )

# https://anymail.readthedocs.io/en/stable/esps/postmark/
EMAIL_BACKEND = "anymail.backends.postmark.EmailBackend"
ANYMAIL: dict[str, str] = {}
# Left out when unset, so the first send raises "Missing POSTMARK_SERVER_TOKEN" instead of posting without one.
if postmark_token := env("POSTMARK_SERVER_TOKEN", default=None):
    ANYMAIL["POSTMARK_SERVER_TOKEN"] = postmark_token

if SENTRY_DSN := env("SENTRY_DSN", default=None):
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        environment=env("SENTRY_ENVIRONMENT", default="production"),
        send_default_pii=False,
    )

ADMINS = env.list("ADMINS")
