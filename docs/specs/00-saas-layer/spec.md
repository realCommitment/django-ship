# 00-saas-layer: the fork is documented and green

Product spec: `docs/specs/00-product/spec.md` (its architecture decisions and anti-goals bind this spec).

## Context

Map of the Pegasus open-source edition at upstream commit `e9d11b0` (release 2026.10), so later specs know where to cut in.

| Concern | Where it lives |
|---|---|
| License | `LICENSE`: MIT. Our code stays MIT; copied code from other MIT/BSD/Apache projects keeps its notice. |
| Settings | `project/settings.py` (django-environ reads `.env`; `DEBUG` defaults to True), `project/settings_production.py` (SSL redirect, secure cookies, proxy header; HSTS commented out). |
| Single-site assumptions | `SITE_ID = 1` in settings; `PROJECT_METADATA` dict (name, URL, description, image, keywords, contact email); `apps/web/meta.py` `get_server_root()` calls `Site.objects.get_current()` with no request; `apps/web/context_processors.py` `project_meta` calls it on every render; `GOOGLE_ANALYTICS_ID` and `DEFAULT_FROM_EMAIL` are single values. 02-sites changes these. |
| Auth | django-allauth, email login, login by code, honeypot, Turnstile captcha on signup. Settings `ACCOUNT_*` in `project/settings.py`; adapter `apps/users/adapter.py` (`EmailAsUsernameAdapter`); user model `apps/users/models.py` (`CustomUser`); forms `apps/users/forms.py` (`TermsSignupForm`); templates `templates/account/`, `templates/allauth/` (element and layout overrides). No MFA. |
| URLs | `project/urls.py` (admin, sitemap, `accounts/`, `users/`, `apps.web.urls`, celery-progress, public API schema/docs). `apps/web/urls.py` has home, terms, robots.txt and error-page test routes. |
| Database | Postgres via `DATABASE_URL`. `docker-compose.yml` runs `db` (Postgres 17) and `redis` with health checks; ports come from `.env` (`scripts/setup-worktree.sh` assigns them per checkout). Models extend `apps.utils.models.BaseModel` (`created_at`, `updated_at`). `DEFAULT_AUTO_FIELD = AutoField`. |
| Migrations | Per app under `apps/*/migrations/`. `apps/web/tests/test_missing_migrations.py` fails the suite on pending migrations, so CI already checks this. |
| Background jobs | `project/celery.py`; `CELERY_BEAT_SCHEDULER` is django-celery-beat's DatabaseScheduler; tasks are declared in `SCHEDULED_TASKS` and loaded with `manage.py bootstrap_celery_tasks`; `make celery` runs worker + beat (`--pool=solo`). |
| Cache | Dummy cache when `DEBUG`, Redis otherwise (`CACHES`). |
| Front end | `assets/` (JS, CSS), `vite.config.ts`, django-vite (`{% vite_asset %}`), Tailwind 4 + DaisyUI, HTMX + Alpine. Base template `templates/web/base.html` holds the title, Open Graph and canonical tags. |
| API | DRF with session auth, drf-spectacular, generated TS client in `api-client/`. |
| Email | Console backend by default; `django-anymail[mailgun]` installed, production config commented out. |
| Tests | Django test runner: `make test`, single test with `make test ARGS='apps.web.tests.test_basic_views'`. 40 tests at baseline. |
| CI | `.github/workflows/tests.yml` (pre-commit with ruff, mypy, tests against Postgres 17 + Redis), `build_frontend.yml`. |
| Deploy | None (`pegasus-config.yaml`: `deploy_platform: none`). `gunicorn` is in the `prod` dependency group. 01-production adds it. |
| Claude Code | `CLAUDE.md` (template sections on top, Pegasus guidelines below), `.claude/commands/` (template), `.claude/skills/` (six Pegasus skills), `.mcp.json` (Postgres MCP reading `DATABASE_URL`, Playwright MCP). |
| Upstream | Remote `upstream` = saaspegasus/django-boilerplate, push disabled. Releases land as merges into upstream `main`; there are no tags. |

## Goal

Make the fork ours without changing behaviour: replace Pegasus's names and contact addresses with django-ship values, remove the two Claude skills that only work with a paid Pegasus account, and record how to merge upstream releases and the fail-loud rules in `CLAUDE.md`. The suite, pre-commit and mypy stay green.

## What the user can do afterwards

- Open the app and see "django-ship" in the page title, Open Graph tags and footer instead of "Django Boilerplate" or Pegasus addresses. Shown by: `curl -s http://localhost:$DJANGO_PORT/ | grep -o '<title>[^<]*</title>'`.
- Merge a Pegasus release by following `CLAUDE.md`: `git fetch upstream && git merge upstream/main`, then the `resolve-pegasus-conflicts` skill for conflicts.
- Claude no longer offers the `upgrade-pegasus` or `pegasus-projects` skills.

## Anti-goals

- No multi-site work (02-sites), no production settings (01-production), no new features.
- Do not rewrite Pegasus's README or guidelines. Change only names, emails and the skill list.
- Do not rename the Python package `project` or the Docker/compose service names.

## Files and interfaces

- `project/settings.py`:
  - `PROJECT_METADATA`: NAME "django-ship", URL from env with the localhost default, a short description, KEYWORDS, CONTACT_EMAIL from env.
  - `ADMINS`, `SERVER_EMAIL`, `DEFAULT_FROM_EMAIL`: read from env, with neutral localhost defaults. No `saaspegasus.com` addresses.
  - `EMAIL_SUBJECT_PREFIX`: `"[django-ship] "`.
  - `SPECTACULAR_SETTINGS`: TITLE and DESCRIPTION.
- `project/settings_production.py`: its own `ADMINS` line uses the same env value.
- `.env.example`: document the new env keys (`ADMINS`, `CONTACT_EMAIL`, `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL`) with placeholders.
- Remove `.claude/skills/upgrade-pegasus/` and `.claude/skills/pegasus-projects/`. Keep `resolve-pegasus-conflicts`, `fix-types`, `upgrade-js-deps` and `upgrade-python-deps`.
- `CLAUDE.md`:
  - **Upstream merges**: the commands above, plus "merge on `main`, not on a feature branch". Check whether `uv run pegasus startapp` still works without a Pegasus account; keep the Pegasus line about it if it does, or delete it.
  - **Mistakes**: the fail-loud rules from `docs/skeleton-checklist.md` item 10: no fallback defaults that hide errors, no `sleep` for races, no swallowed exceptions, errors carry context.
- Grep the repo (templates, `pyproject.toml` description, `README.md` top lines excluded) for remaining "Django Boilerplate" and "saaspegasus.com" user-facing strings in templates and settings; replace those shown to visitors.

## Checklist decisions (docs/skeleton-checklist.md)

1. Compose with health checks: already in Pegasus (`db`, `redis`). Adopted as is.
2. One stack per worktree: done in `scripts/setup-worktree.sh` and `orca.yaml` (main branch). Adopted.
3. Bootstrap and smoke: bootstrap is the setup script (migrate). Smoke waits for `/health/` in 01-production. Deferred.
4. Strict types: Pegasus runs mypy non-strict with django-stubs. Kept as Pegasus has it, so upstream merges stay clean. Skipped strict.
5. Targeted tests: `make test ARGS='<dotted path>'` is the default during work. Adopted, documented by Pegasus.
6. One end-to-end path per feature: each spec's verification step drives the running app (curl or Playwright MCP). Adopted per spec.
7. Agent access: Postgres MCP (now reading `DATABASE_URL`) and Playwright MCP from Pegasus. Adopted.
8. Logging rules: Pegasus logs to console; no secrets test yet. Deferred to 01-production.
9. Gates: pre-commit (ruff) plus mypy plus tests, as in CI. Adopted as is.
10. Fail loud: into `CLAUDE.md` Mistakes in this spec. Adopted.
11. Boundary lint: skipped, too few modules.
12. Review standards file: skipped for now.

## End-to-end verification

1. `make test` passes with the same or higher count (baseline 40); `uv run pre-commit run --all-files` and `make type-check` are clean.
2. Start the app with `make dev` (or `uv run manage.py runserver $DJANGO_PORT`). `curl -s http://localhost:$DJANGO_PORT/` returns 200, its `<title>` and `og:site_name` say "django-ship", and `grep -c saaspegasus` on the response is 0.
3. `ls .claude/skills` shows exactly the four kept skills.
