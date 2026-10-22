# 01-production: production settings and the Render Blueprint

Product spec: `docs/specs/00-product/spec.md`. Context map: `docs/specs/00-saas-layer/spec.md`.

**Superseded in part by 08-railway (2026-10-19):** `render.yaml` and `deploy/build.sh` are gone, the Dockerfile anti-goal is reversed, and uploads go to a Railway bucket instead of R2. The production settings, health check, whitenoise, Anymail and Sentry parts still stand.

## Goal

Everything needed to run django-ship in production on Render, proven locally: production settings that fail loudly without a secret key, serve static files through whitenoise, store uploads in Cloudflare R2 when configured, send email through Postmark via Anymail, report errors to Sentry (web and Celery), answer a health check, keep the API docs private, and pass `manage.py check --deploy`. Plus a Render Blueprint (`render.yaml`) and the build and pre-deploy scripts it calls, and a CI step that runs the deploy check. The actual Render deploy and real domains are 03-go-live.

## What the user can do afterwards

- Run the app with production settings locally and get the same behaviour Render will:
  ```
  npm run build && DJANGO_SETTINGS_MODULE=project.settings_production SECRET_KEY=local-prod-check ALLOWED_HOSTS=localhost uv run manage.py collectstatic --noinput
  DJANGO_SETTINGS_MODULE=project.settings_production SECRET_KEY=local-prod-check ALLOWED_HOSTS=localhost uv run gunicorn project.wsgi -b 127.0.0.1:$DJANGO_PORT
  curl -i http://localhost:$DJANGO_PORT/health/                                   # 200, no redirect
  curl -i -H 'X-Forwarded-Proto: https' http://localhost:$DJANGO_PORT/            # 200 landing page
  curl -i http://localhost:$DJANGO_PORT/                                          # 301 to https
  ```
- Create a Render Blueprint from the repo and get web, worker, Key Value and Postgres services with the right commands, once 03-go-live adds secrets and domains.
- See CI fail if a production setting regresses (`check --deploy`).

## Anti-goals

- No real deploy, no domains, no DNS, no live Postmark/Sentry/R2 credentials (03-go-live).
- No multi-site settings (02-sites). One `ALLOWED_HOSTS` env list for now.
- No Dockerfile, Fly or Kamal config.
- No change to the development settings' behaviour: `make dev` and `make test` work exactly as before.
- No new task queue or cache library: keep Pegasus's built-in Redis cache and Celery.

## Files and interfaces

Production behaviour goes in `project/settings_production.py` (Pegasus's production module, already selected by `DJANGO_SETTINGS_MODULE`), so `project/settings.py` changes as little as possible. Copy the blocks from cookiecutter-django (BSD-3, keep a one-line source comment) and adapt them to django-environ, which Pegasus already uses:
https://github.com/cookiecutter/cookiecutter-django/blob/master/%7B%7Bcookiecutter.project_slug%7D%7D/config/settings/production.py

- **Secret key**: `SECRET_KEY = env("SECRET_KEY")` with no default, so a missing key raises at import.
- **Sender addresses**: `DEFAULT_FROM_EMAIL` and `SERVER_EMAIL` are required in production with no localhost defaults, matching how 00-saas-layer made `ADMINS` required (fail-loud rule in `CLAUDE.md`).
- **Hosts**: append `RENDER_EXTERNAL_HOSTNAME` to `ALLOWED_HOSTS` when that env var is set (Render's Django guide). `CONN_MAX_AGE = env.int("CONN_MAX_AGE", default=60)`.
- **Security**:
  - Keep Pegasus's SSL redirect, secure cookies and proxy header.
  - Turn on HSTS with `SECURE_HSTS_SECONDS` from env, default 60, to be raised after go-live.
  - Leave `SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD` off, because many unrelated domains share this deployment and preload is a permanent commitment. Silence their two `check --deploy` warnings with that reason in a comment.
  - `SECURE_REDIRECT_EXEMPT` covers the health check path, so Render's plain-HTTP health check gets a real 200 instead of a redirect, which Render also counts as healthy.
- **Static files**: add `whitenoise.middleware.WhiteNoiseMiddleware` right after `SecurityMiddleware`, and use `whitenoise.storage.CompressedStaticFilesStorage` for the `staticfiles` storage. Use the plain variant, not Manifest: Pegasus warns that manifest storage can break CSS image references, and Vite already hashes its chunks.
- **Media**: when `AWS_STORAGE_BUCKET_NAME` is set, the `default` storage is django-storages' S3 backend configured for R2 (`AWS_S3_ENDPOINT_URL`, `AWS_S3_CUSTOM_DOMAIN`, credentials from env). Otherwise it stays on the file system.
- **Email**: `anymail.backends.postmark.EmailBackend` with `ANYMAIL = {"POSTMARK_SERVER_TOKEN": env(...)}`. Switch the `django-anymail` extra in `pyproject.toml` from mailgun to postmark if one exists. Postmark needs no extra package; then drop the extra.
- **Sentry**: `sentry_sdk.init(...)` with Django and Celery integrations when `SENTRY_DSN` is set, with `environment` from env and `send_default_pii=False`. New dependency `sentry-sdk`.
- **Dependencies**: add `whitenoise`, `django-storages[s3]` and `sentry-sdk` with `uv add`, which updates `uv.lock`.
- **Health check** (`/health/`): a tiny view in `apps/web`. It runs `SELECT 1` on the default database and returns `{"status": "ok"}` with 200, or 503 with the failing check named. No login, no template, no Vite.
- **API docs**: in `project/urls.py`, pass `permission_classes=[IsAdminUser]` to the three drf-spectacular views, as Pegasus's comment there suggests.
- **`render.yaml`** (Render Blueprint spec: https://render.com/docs/blueprint-spec):
  - An env var group with `DJANGO_SETTINGS_MODULE=project.settings_production` and `SECRET_KEY` (`generateValue: true`).
  - **Web service**:
    - native `python` runtime on a paid plan, because `preDeployCommand` is paid-only;
    - `buildCommand: ./deploy/build.sh`, `preDeployCommand: ./deploy/pre_deploy.sh`;
    - `startCommand` running gunicorn on `project.wsgi`;
    - `healthCheckPath: /health/`, `autoDeployTrigger: checksPass`;
    - env vars: `DATABASE_URL` from the database, `REDIS_URL` from Key Value, `ALLOWED_HOSTS`, and `sync: false` placeholders for `SENTRY_DSN`, `POSTMARK_SERVER_TOKEN` and the `AWS_*` R2 keys.
  - **Worker**: `buildCommand: uv sync --frozen --no-dev` and `startCommand: celery -A project worker -l info --beat`, with the same env as the web service minus `ALLOWED_HOSTS`. Add a `shortcut:` comment: beat runs inside the single worker, so move it to its own worker before scaling the worker past one instance.
  - **Key Value**: `type: keyvalue` (`redis` is a deprecated alias), `plan: 256mb` (the smallest plan with persistence), `maxmemoryPolicy: noeviction`.
  - **Database**: a paid Postgres plan.
  - One region for all services, with a comment saying where to change it.
- **`deploy/build.sh`**: `set -o errexit`; `uv sync --frozen --no-dev`; `npm ci`; `npm run build`; `collectstatic --noinput`. No database access, because the build runs while the old release still serves.
- **`deploy/pre_deploy.sh`**: `set -o errexit`; `migrate --noinput`; `bootstrap_celery_tasks`.
- **Running commands on Render**: if it is unclear whether `uv` is on Render's PATH at start time, call the venv binaries (`.venv/bin/gunicorn`, `.venv/bin/celery`, `.venv/bin/python`). Note the choice in the implementation notes.
- **CI** (`.github/workflows/tests.yml`): one step in the `tests` job that runs `manage.py check --deploy --fail-level WARNING` with `DJANGO_SETTINGS_MODULE=project.settings_production` and dummy values for every required production key (`SECRET_KEY`, `ALLOWED_HOSTS`, `ADMINS`, `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL`).
- **`.env.example`**: document the production keys (`SECRET_KEY`, `ALLOWED_HOSTS`, `SENTRY_DSN`, `POSTMARK_SERVER_TOKEN`, `AWS_*`, `SECURE_HSTS_SECONDS`) as commented placeholders.
- **Tests**:
  - `/health/` returns 200 and the JSON body;
  - with the database unreachable it returns 503 (mock the cursor);
  - the API schema URLs return 403 for an anonymous user;
  - importing production settings without `SECRET_KEY` raises `ImproperlyConfigured`. Run it in a subprocess so the test settings stay untouched.

## End-to-end verification

1. `make test` passes (baseline count plus the new tests); pre-commit and `make type-check` are clean.
2. `npm run build`, then `collectstatic` with production settings, then gunicorn with production settings on `$DJANGO_PORT`. Capture:
   - `curl -i http://localhost:$DJANGO_PORT/health/`: 200 with `{"status": "ok"}`, no redirect.
   - `curl -i http://localhost:$DJANGO_PORT/`: 301 to `https://`.
   - `curl -i -H 'X-Forwarded-Proto: https' http://localhost:$DJANGO_PORT/`: 200, with a `Strict-Transport-Security` header.
   - Fetch one CSS file linked from that page with `X-Forwarded-Proto: https`: 200 from whitenoise. A `curl -I --compressed` should show gzip or brotli if available.
   - `curl -i -H 'X-Forwarded-Proto: https' http://localhost:$DJANGO_PORT/api/schema/`: 403.
3. `DJANGO_SETTINGS_MODULE=project.settings_production uv run manage.py check --deploy --fail-level WARNING` with `SECRET_KEY` unset fails loudly. With it set, it reports no issues.
4. Start `celery -A project worker -l info --beat` with production settings for about 20 seconds. The log shows the worker ready and `beat: Starting...`, then stop it.
5. `render.yaml` parses as YAML. If network access allows, also validate it against Render's published Blueprint JSON schema; otherwise list it under Not verified.
