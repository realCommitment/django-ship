# 08-railway: implementation notes

Spec: `docs/specs/08-railway/spec.md`. Implemented 2026-10-19 in the same session that wrote the spec (owner's request, no approval round).

## Decisions not in the spec

- **`collectstatic` runs with `DEBUG=False` in the Dockerfile.** With the development module and `DEBUG` unset, `settings.py` adds `django_browser_reload`, a dev-only package that `uv sync --no-dev` leaves out, and the build failed. `DEBUG=False` keeps the settings importable; nothing in collectstatic connects to Redis or Postgres.
- **No brotli copies.** `python -m whitenoise.compress` wrote 205 `.gz` files and 0 `.br`, because the `brotli` package is not installed. Gzip is enough; add `brotli` to the dependencies if the saving ever matters.
- **`scripts/railway-check.mjs` is plain JavaScript.** Node 24 strips the types from `.railway/railway.ts` when importing it, and `tsc` already type-checks the config because `tsconfig.json` has no `include` list. A `.ts` check script tripped `tsc` (import with a `.ts` extension, top-level await), so the script stays `.mjs`. It runs in the front-end workflow after `type-check`.
- **`railway` is a dev dependency** (3.16). The CLI is not a project dependency; the owner installs it where `config apply` runs.
- **The deploy check cannot be proven on this machine outside Docker.** `mise` exports this checkout's `.env` into every `uv run`, so the dummy `SECRET_KEY` was replaced by the dev key and `check --deploy` warned. Inside the image, which has no `.env`, the check passes with no issues. CI has no `.env` either.
- **Postgres and Redis regions are left to the account default** in `railway.ts`. `postgres()` and `redis()` accept a `region`, but the type says nothing about the volume behind them, so the owner sets the account's preferred region to Virginia before applying (03-go-live step 2).
- **Only the web service has a pre-deploy command.** Three services running `migrate` at once would race; the CLAUDE.md rule that migrations work with the previous release covers worker and beat starting first.

## Verified locally

- `docker build -t django-ship .`: 224 static files collected, image runs as `app`, no `node_modules`, no `.env`.
- In the image against the compose databases: `check --deploy --fail-level WARNING` clean; `deploy/pre_deploy.sh` ran migrate, `sync_sites` (created both sites) and `bootstrap_celery_tasks`; gunicorn answered `/health/` 200 with `Host: healthcheck.railway.app`, 301 to https without `X-Forwarded-Proto`, 200 with HSTS and both sites' titles with it, and one CSS file gzip-encoded from whitenoise; `celery worker` logged `ready`, `celery beat` logged the DatabaseScheduler starting.
- `make test` (138 tests), `make type-check`, ruff, `npm run railway-check` (prints the six resources).

## Not verified

- `railway config plan` or `apply` against a real project (needs the owner's account; 03-go-live).
- That `preserve()` is accepted for variables that do not exist yet, and that `checkSuites: true` maps to the dashboard's "Wait for CI".
- The bucket's addressing style on a real bucket.
