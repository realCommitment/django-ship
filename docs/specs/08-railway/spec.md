# 08-railway: run django-ship on Railway

Product spec: `docs/specs/00-product/spec.md`. Replaces the Render Blueprint from 01-production. Decided 2026-10-19 by the owner (seed plan) and the implementing session (the rest); the owner asked for no approval round.

## Goal

django-ship runs on Railway from one Docker image: a web service, a Celery worker, a Celery Beat service, Railway Postgres, Railway Redis and one private storage bucket for uploads, all declared in `.railway/railway.ts` and applied with `railway config apply`. Railway deploys from GitHub on every push to `main` once that commit's GitHub Actions runs pass. Everything Render-specific is removed. The real accounts, domains, secrets and the first deploy are the owner's steps, listed in the rewritten `03-go-live`.

## What the owner can do afterwards

- Build and run the production image locally, which is the same image Railway builds:
  ```
  docker build -t django-ship .
  docker run --rm --network host -e PORT=8010 -e DATABASE_URL=... -e REDIS_URL=... <the production env> django-ship
  curl -i http://localhost:8010/health/      # 200 {"status": "ok"}
  ```
- Run the pre-deploy step and the worker and beat commands in that image.
- From a machine with the Railway CLI: `railway login && railway link`, then `DIRECTORY_DOMAIN=... PRODUCTIVITY_DOMAIN=... railway config plan`, then `apply`. It creates the six resources, wires `DATABASE_URL`, `REDIS_URL` and the bucket credentials, and keeps every secret as `preserve()` so none lives in the repo.
- Type-check and compile the Railway config locally without an account: `npm run railway-check`.

## Decisions

- **Infrastructure as Code, not the dashboard.** `.railway/railway.ts`, applied with the Railway CLI. Config as Code (`railway.toml`) is deprecated and stops being read on 2026-12-01.
- **A Dockerfile, not Railpack.** This reverses 01-production's "No Dockerfile" anti-goal. One image for web, worker and beat; each service sets its own start command. Multi-stage: a `node:24` stage runs `npm ci && npm run build`, a `python:3.14-slim` stage with `uv` runs `uv sync --frozen --no-dev`, copies the built `static/` and runs `collectstatic`.
- **`collectstatic` runs with the development settings module plus `python -m whitenoise.compress`.** Production settings refuse to import without the secret key, Stripe keys, portal ids, domains and sender addresses, and a Docker build must not need secrets. The development module produces the same files; whitenoise's compress command adds the gzip and brotli copies that `CompressedStaticFilesStorage` would have made. `deploy/build.sh` is deleted: the Dockerfile is the build.
- **Pre-deploy** stays `deploy/pre_deploy.sh` (`migrate`, `sync_sites`, `bootstrap_celery_tasks`), set on the web service only. Railway runs it in its own container from the same image; a failure stops the deploy. Worker and beat have no pre-deploy, so they may run new code before the web's migrations finish; the existing rule that migrations work with the previous release's code covers it.
- **Beat is its own service** with one replica (`django_celery_beat` DatabaseScheduler; two replicas would schedule every task twice). The worker runs without `--beat`.
- **Hosts.** `healthcheck.railway.app` is always in `ALLOWED_HOSTS` in production, and `RAILWAY_PUBLIC_DOMAIN` is appended when set, replacing `RENDER_EXTERNAL_HOSTNAME`. The health path keeps its SSL-redirect exemption.
- **The media bucket is required in production.** `AWS_STORAGE_BUCKET_NAME` has no default any more; before, a missing bucket silently stored uploads on the container disk, lost at the next deploy. The bucket is private, so file URLs are presigned by django-storages (no custom domain, `AWS_QUERYSTRING_AUTH` left on). `AWS_S3_REGION_NAME` comes from the bucket's `REGION` and `AWS_S3_ADDRESSING_STYLE = "virtual"`, which is what Railway buckets use. `AWS_S3_CUSTOM_DOMAIN` is dropped.
- **Domains come from the owner's shell at apply time** (`DIRECTORY_DOMAIN`, `PRODUCTIVITY_DOMAIN`), because `domains:` needs literal strings and the repo must not hard-code the owner's domains. `railway.ts` throws when they are unset. The same values become the services' `DIRECTORY_DOMAIN`, `PRODUCTIVITY_DOMAIN` and `ALLOWED_HOSTS` variables.
- **Every other owner value is `preserve()`:** `SECRET_KEY`, `ADMINS`, sender addresses, Stripe keys and portal ids, Postmark, Sentry. The owner sets them in the dashboard before the first successful deploy. The first deploy after `apply` fails loudly on the missing values; the next push or a redeploy picks them up.
- **"Wait for CI"** is `checkSuites: true` on the GitHub source of the three services. A commit deploys only when every GitHub Actions run on it passes.
- **CI builds the image** in a new `docker` job, so a broken Dockerfile fails the checks and never deploys.
- **Region:** services in `us-east4-eqdc4a` (Virginia), the bucket in `iad`. Postgres and Redis take Railway's default region, which the owner sets to Virginia in account settings before applying (the IaC helpers accept a region, but the volume behind a database is created where the account default says).
- **Plan: Pro** from the start (custom domains beyond two, 50 GB volumes). **Hard spending limit and alerts** are dashboard settings.
- **Render is removed in this spec:** `render.yaml`, `deploy/build.sh`, the `RENDER_EXTERNAL_HOSTNAME` lines, the Render comments in `deploy/pre_deploy.sh`, the test and `.env.example`, and the Render sentence in `CLAUDE.md`.
- **Backups:** volume backups are switched on at go-live in the dashboard (daily kept 6 days, weekly 1 month, monthly 3 months). The nightly off-site `pg_dump` to another provider is a follow-up spec (`09-offsite-backup`), as is point-in-time recovery.

## Anti-goals

- No real deploy, account, DNS or secrets in this spec (03-go-live, owner).
- No staging or PR environments.
- No off-site backup cron service, no pgBackRest.
- No change to development: `make dev`, `make test`, docker compose for the databases all work as before.
- No Railway CLI as a project dependency; only the `railway` npm package, for type-checking the config.

## Files and interfaces

- **`Dockerfile`** (new) and **`.dockerignore`** (new: `.git`, `.venv`, `node_modules`, `static_root`, `media`, `.env*`, `docs`).
  - Stage `frontend`: `node:24-slim`, `npm ci`, `npm run build`. Output is `static/` (vite's `outDir`).
  - Stage `app`: `python:3.14-slim`, `uv` copied from `ghcr.io/astral-sh/uv`, `UV_COMPILE_BYTECODE=1`, `uv sync --frozen --no-dev`, copy the source and the built `static/`, `DJANGO_SETTINGS_MODULE=project.settings python manage.py collectstatic --noinput`, `python -m whitenoise.compress static_root`. `ENV PATH=/app/.venv/bin:$PATH`, `ENV DJANGO_SETTINGS_MODULE=project.settings_production`. `CMD gunicorn project.wsgi --bind 0.0.0.0:$PORT`. Runs as a non-root user.
- **`.railway/railway.ts`** (new): `web`, `worker`, `beat` services from `github("alpha-bravo-lima/django-ship", { branch: "main", checkSuites: true })`, `build: { builder: "DOCKERFILE" }`, start commands per service, `preDeployCommand: ["./deploy/pre_deploy.sh"]` and `healthcheckPath: "/health/"` on web, `numReplicas: 1` on beat, `region` on all three; `postgres("postgres")`, `redis("redis")`, `bucket("media", { region: "iad" })`; one shared `env` map spread into the three services. The web service lists both domains.
- **`package.json`**: `railway` as a dev dependency and a `railway-check` script that type-checks `.railway/railway.ts` and evaluates it with placeholder domains to prove it compiles.
- **`project/settings_production.py`**: `ALLOWED_HOSTS` gets `healthcheck.railway.app` and `RAILWAY_PUBLIC_DOMAIN`; the bucket block becomes unconditional with `AWS_S3_REGION_NAME`, `AWS_S3_ADDRESSING_STYLE` and no custom domain; comments say Railway.
- **`deploy/pre_deploy.sh`**: comment and paths (`python` is on `PATH` in the image). **`deploy/build.sh`** and **`render.yaml`**: deleted.
- **`.github/workflows/tests.yml`**: the production check gets the four `AWS_*` dummy values; a `docker` job runs `docker build .`.
- **`.env.example`**, **`CLAUDE.md`**, **`apps/web/tests/test_production_settings.py`**: Render wording replaced.
- **Specs**: `00-product` (goal, anti-goal, hosting decision, the 03 line), `01-production` (note that the Blueprint and the Dockerfile anti-goal are superseded), `03-go-live` rewritten for Railway.

## End-to-end verification

1. `make test`, pre-commit and `make type-check` pass; `npm run railway-check` passes.
2. `docker build -t django-ship .` succeeds; the image contains `static_root/` with `.gz` files and no `node_modules`.
3. With the local docker compose databases: `docker run --rm --network host` with `PORT=8010`, `DATABASE_URL`, `REDIS_URL` and the CI's dummy production values:
   - `./deploy/pre_deploy.sh` finishes (migrate, sync_sites, bootstrap_celery_tasks);
   - the default command serves `curl -i http://localhost:8010/health/` with 200 and `{"status": "ok"}`, and `curl -i -H 'Host: healthcheck.railway.app' http://localhost:8010/health/` also 200;
   - `curl -i -H 'X-Forwarded-Proto: https' -H 'Host: directory.example.com' http://localhost:8010/` is 200 with HSTS, and one CSS file comes back from whitenoise;
   - `celery -A project worker -l info` logs "ready", and `celery -A project beat -l info` logs the DatabaseScheduler starting.
4. `railway config plan` against a real project is the owner's step (03-go-live); listed under Not verified.
