# 00-saas-layer: implementation notes

## Decisions not in the spec

- **`PROJECT_URL` is the env key for `PROJECT_METADATA["URL"]`.** The spec says "URL from env" without a name. `PROJECT_URL` matches the dict it feeds and the existing `PROJECT_LOG_LEVEL` naming. Documented in `.env.example` next to the four keys the spec lists.
- **Defaults:** `CONTACT_EMAIL` and `DEFAULT_FROM_EMAIL` default to `hello@localhost`, `ADMINS` to `["admin@localhost"]`, `SERVER_EMAIL` to `noreply@localhost`. Pegasus's `SERVER_EMAIL` default was `noreply@localhost:8000`, which is not a valid address (it has a port), so it changed with the rest.
- **`ADMINS` is a list of plain addresses** (`env.list`, comma-separated in `.env`), the format Django 6.0 expects and the one Pegasus already used.
- **`settings_production.py` reads `ADMINS` with no default: `ADMINS = env.list("ADMINS")`.** It is the same env key as `settings.py`, but in production a missing value raises `ImproperlyConfigured` instead of mailing 500 errors to `admin@localhost`. That follows the fail-loud rule this spec adds. `env` comes in through the existing `from .settings import *`. Nothing loads the production settings yet (no deploy until 01-production), so this breaks nothing today.
- **The localhost defaults in `settings.py` go against the new fail-loud rule.** The spec asks for them, and they keep local dev and CI working with no extra `.env` keys. Making `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL`, `CONTACT_EMAIL` and `PROJECT_URL` required in production is for 01-production, which brings in cookiecutter-django's required-env pattern.
- **`PROJECT_URL` only seeds the Site record.** `PROJECT_METADATA["URL"]` is read only by `apps/web/migrations/0001_initial.py`, on the first migrate. Absolute URLs come from `Site.objects.get_current().domain`. `.env.example` says this, and gives the expected format (no trailing slash: the migration strips only the scheme).
- **Description** (title tag, OpenAPI): "One Django foundation for a portfolio of sites.", taken from the product spec's title.
- **`KEYWORDS` left as `"SaaS, django"`.** It holds no Pegasus name, so changing it was churn.
- **Footer credit removed.** The "🦄 Built with SaaS Pegasus" link (to saaspegasus.com) was the only visitor-facing Pegasus address in the templates. The spec's own check needs `grep -c saaspegasus` to be 0, and the product spec says visitors should never notice the shared backend, so the line is gone rather than reworded. MIT asks for the notice in copies of the code (`LICENSE`), not in the UI.
- **`.env.example` keys are commented placeholders** (`example.com`), like the email lines already there. A fresh `cp .env.example .env` (what `scripts/setup-worktree.sh` does) keeps the settings defaults.
- **`CLAUDE.md` upstream section** adds one sentence: the `resolve-pegasus-conflicts` skill's steps for finding a `pegasus-YYYY.MM` branch do not apply, because we merge `upstream/main` directly. Without it an agent following the skill goes looking for a branch that does not exist. The skill itself is unchanged.
- **`pegasus startapp` works without a Pegasus account,** so its line in `CLAUDE.md` stays. Checked with `pegasus startapp demo Widget` in a scratch copy of `manage.py`, `pegasus-config.yaml` and `project/`, with no `PEGASUS_API_KEY` and no `~/.pegasus/credentials`: exit 0, `apps/demo` and `templates/demo` generated, the app added to `INSTALLED_APPS`. `startapp` renders bundled cookiecutter templates and never imports the API client. Only `pegasus auth` and `pegasus projects` need an account.

## Left as is, on purpose

- **`PROJECT_METADATA["IMAGE"]` still points at the Wikimedia Pegasus logo** (`PEO-pegasus_black.svg`), shown in `og:image` and `twitter:image`. It is neither a name nor an email and the spec does not list it. There is no django-ship image to swap in yet. **Your call:** give me an image, or leave it for 02-sites' per-site settings.
- **Not visitor-facing, unchanged:** "Django Boilerplate" in the docstrings of `project/settings.py`, `project/urls.py`, `project/wsgi.py`, in the generated `api-client/runtime.ts` header (it follows the OpenAPI title the next time the client is regenerated), and in `pegasus-config.yaml` (`project_name`, `email: hello@saaspegasus.com`, input for Pegasus's project generator). `README.md` and the Pegasus guidelines are excluded by the spec.
- The Site record in an existing database keeps whatever name it was created with. `apps/web/migrations/0001_initial.py` reads `PROJECT_METADATA` only when it first runs, so fresh and test databases get "django-ship". The page title and `og:site_name` come from settings, not the Site record.

## Environment

- **`make` is not installed on this machine** (no `/usr/bin/make`). I ran the Makefile's recipes directly: `make test` is `uv run manage.py test`, `make type-check` is `uv run mypy .`, `make dev` runs `scripts/dev.sh`, so the app ran as `uv run manage.py runserver $DJANGO_PORT`. All through `~/.local/bin/mise exec --` so `.env` and the pinned Python load.

## Code review

`/code-review medium`. The first run reviewed the wrong repository: the forked skill started in the session's working directory, another repository. Its findings were about that repository's `PLAN.md` and were discarded. The second run named the django-ship repository and the range `b8fd99f..HEAD` plus the working tree.

Fixed:

- Production `ADMINS` silently fell back to `admin@localhost`, and the line duplicated the one in `settings.py`. It is now required in production (see above).
- The `SERVER_EMAIL` default `noreply@localhost:8000` was a malformed address. It is now `noreply@localhost`.
- `.env.example` presented `PROJECT_URL` as a live setting, but it only seeds the Site record on the first migrate, and a trailing slash would end up in `Site.domain`. The comment now says both.

Skipped:

- "The localhost defaults contradict the fail-loud rule." The spec asks for them; production enforcement is for 01-production (see above).
- "The `resolve-pegasus-conflicts` skill still tells the agent to find a `pegasus-YYYY.MM` branch and merge main into it." The spec says keep the skill, and changes to Pegasus content are limited to names, emails and the skill list. The `CLAUDE.md` Upstream merges section overrides those steps in one sentence. **Your call** whether to edit the skill's "Running the merge" steps instead.
- "The migration's URL parsing keeps a trailing slash or path." `apps/web/migrations/0001_initial.py` is Pegasus's code and runs once. It is documented in `.env.example` instead of patched, to keep upstream merges clean.
- "The spec is ticked before the evidence exists; the WIP commit has no evidence." That is a process point about an intermediate commit. The squashed final commit carries the evidence and the tick together.
