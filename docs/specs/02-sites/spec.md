# 02-sites: two sites from one deployment

Product spec: `docs/specs/00-product/spec.md`. Context map: `docs/specs/00-saas-layer/spec.md` ("Single-site assumptions" row lists what this spec changes).

## Goal

One running Django process serves two placeholder sites, a business directory and a productivity app, on their own domains. A small middleware looks up the `Site` record for the request's domain. It sets `request.site`, a site key and that site's URL map, and redirects unknown domains to the main site. Each site has its own landing page, page metadata (title, description, Open Graph), analytics ID, robots.txt, sitemap, email sender and subject prefix. Accounts stay global; we record which site a person signed up on. The pattern is envergo's (MIT, a live French government service running two products from one deployment): https://github.com/MTES-MCT/envergo/blob/main/envergo/contrib/middleware.py

## What the user can do afterwards

With the dev server on `$DJANGO_PORT`:

```
curl -s -H "Host: directory.localhost:$DJANGO_PORT" http://127.0.0.1:$DJANGO_PORT/ | grep -o '<title>[^<]*</title>'      # directory title
curl -s -H "Host: productivity.localhost:$DJANGO_PORT" http://127.0.0.1:$DJANGO_PORT/ | grep -o '<title>[^<]*</title>'   # productivity title
curl -si -H "Host: unknown.localhost:$DJANGO_PORT" http://127.0.0.1:$DJANGO_PORT/some/path | grep -i '^location'         # main site, same path
curl -s -H "Host: directory.localhost:$DJANGO_PORT" http://127.0.0.1:$DJANGO_PORT/robots.txt                             # Sitemap line with the directory host
```

In a browser, `http://directory.localhost:$DJANGO_PORT` and `http://productivity.localhost:$DJANGO_PORT` show different landing pages. Signing up on one and logging in on the other works with the same email and password; the login is separate per domain.

## Anti-goals

- No teams, billing or site-specific data models (later specs).
- No real domains or deploy (03-go-live). Dev domains are `*.localhost`.
- No cross-domain single sign-on and no shared session cookie domain.
- No per-site database, schema or tenant library.
- No editing of Site records through an admin UI as the source of truth. Settings are the source of truth, and the database mirrors them.
- No per-site layout for the shared account pages beyond name and metadata. Login, signup and profile keep Pegasus's templates.

## Files and interfaces

New code goes in a new app, `apps/multisite`. Its label must not clash with `django.contrib.sites`, whose label is `sites`. Two new site apps hold each site's pages:

- **Settings** (`project/settings.py`):
  - Remove `SITE_ID`.
  - Add `SITES`, a dict keyed by site key (`"directory"`, `"productivity"`). Each entry holds:
    - `domain`: from env (`DIRECTORY_DOMAIN`, `PRODUCTIVITY_DOMAIN`), defaulting to `directory.localhost` and `productivity.localhost`;
    - `name`, `description`, `keywords`;
    - `urlconf`: `apps.directory.urls` or `apps.productivity.urls`;
    - `from_email`: from env, with a neutral default;
    - `google_analytics_id`: from env, default empty.
    - `image`: the social-preview image, default empty, so `og:image` and `twitter:image` are left out until a site has one.
  - Also set `PROJECT_METADATA["IMAGE"]` to empty: it still points at Pegasus's logo.
  - Add `MAIN_SITE = "productivity"`, where unknown domains are redirected.
  - Set `ACCOUNT_EMAIL_SUBJECT_PREFIX = None`, so allauth prefixes subjects with the current Site's name (allauth `format_email_subject`).
  - Add the middleware right after `SecurityMiddleware` and whitenoise. It must run before `CommonMiddleware`, whose slash redirect resolves URLs.
- **`apps/multisite/management/commands/sync_sites.py`**: idempotent `update_or_create` of a `Site` row for each `SITES` entry (domain and name). Run it from `scripts/setup-worktree.sh` after `migrate` and from `deploy/pre_deploy.sh` after `migrate`. This replaces envergo's data migrations, because our domains differ per environment.
- **`apps/multisite/middleware.py`** (envergo's shape):
  - Look up `Site.objects.get_current(request)`. Django matches the host with its port, then without it.
  - On `Site.DoesNotExist`, log a warning with the host and path, then redirect (302) to the main site's domain with the same path, keeping the request's scheme and port.
  - Otherwise set `request.site`, `request.site_key` (the `SITES` key whose domain equals `site.domain`) and `request.urlconf`.
  - The health check path (`/health/`, from 01-production) bypasses all of this and is served by `ROOT_URLCONF`.
- **`apps/multisite/context_processors.py`**: replaces Pegasus's `project_meta` in `TEMPLATES`, or wraps it.
  - It returns the same keys, with `NAME`, `DESCRIPTION`, `KEYWORDS` and `URL` taken from the current site.
  - `server_url` and `page_url` come from the request (`request.build_absolute_uri`).
  - It also gives the current site's `GOOGLE_ANALYTICS_ID`.
  - Keep Pegasus's `apps/web/context_processors.py` and `templates/web/base.html` unchanged where possible.
- **`apps/web/meta.py`**: `get_server_root()` and `absolute_url()` take an optional request and use it when given, instead of `Site.objects.get_current()` without a request (which fails once `SITE_ID` is gone). Callers that have a request pass it: the context processor and the `absolute_url` template tag (via `takes_context`). Keep the signatures backward compatible for upstream merges.
- **`apps/users/adapter.py`**: `EmailAsUsernameAdapter.get_from_email()` returns the current site's `from_email`. It reads the request from `allauth.core.context.request`, because `get_from_email` takes no request argument, and falls back to `DEFAULT_FROM_EMAIL` with no request.
- **Signup site** (Open edX's `UserSignupSource` idea, as a side table so Pegasus's user model and migrations stay untouched):
  - `apps/multisite/models.py` gets `SignupSite(user=OneToOne(AUTH_USER_MODEL), site=FK(Site, null=True, on_delete=SET_NULL))` extending `BaseModel`.
  - Fill it from allauth's `user_signed_up` signal, using `request.site`.
- **Site apps**: `apps/directory` and `apps/productivity`. Each has:
  - `urls.py`:
    - the site's `home` view at `""`: anonymous visitors get the site's landing template, logged-in users get Pegasus's dashboard (`web/app_home.html`), as `apps.web.views.home` does;
    - `robots.txt` with a `Sitemap: <scheme>://<host>/sitemap.xml` line;
    - `sitemap.xml` listing that site's public pages. Django's sitemap view takes the domain from `get_current_site(request)`.
    - Then append the shared routes: `project.urls.urlpatterns`, so admin, `accounts/`, `users/`, API, celery-progress and Pegasus's web routes keep working on every domain.
  - The site's own `templates/<site>/landing.html`, extending `web/base.html`, with distinct headline text so the two sites are visibly different.
- **CLAUDE.md**: a "Multi-site" section with these rules:
  - a new site is an app, a `SITES` entry and `sync_sites`;
  - site pages live in the site app's `urls.py` and `templates/<site>/`;
  - code that needs the site reads `request.site` or `request.site_key`;
  - Celery tasks take a `site_id` argument and never guess the site;
  - tests set the host header;
  - `SITE_ID` must not come back.
  - migrations must work with the previous release's code, because Render deploys the web service and the worker separately (product spec decision).
- **Tests** (`apps/multisite/tests/`):
  - each host gets its own landing page and title;
  - an unknown host gets a 302 to the main site with the path kept;
  - robots.txt and sitemap.xml contain the requesting host;
  - `/health/` answers 200 on an unknown host;
  - `og:site_name` differs per host;
  - a password-reset email sent from each host has that site's From address and a subject prefixed with the site name;
  - signing up on the directory host creates a `SignupSite` pointing at the directory site;
  - `sync_sites` run twice leaves exactly one row per site;
  - Pegasus's existing tests still pass. Set a host where they need one; don't weaken them.

## End-to-end verification

1. `make test`, pre-commit and `make type-check` are clean.
2. Run `sync_sites`, then start the dev server. Capture the four curl commands above: two different titles, a redirect to `productivity.localhost` keeping `/some/path`, and a robots.txt with the directory sitemap URL.
3. Open `http://directory.localhost:$DJANGO_PORT/accounts/signup/` with the Playwright MCP, sign up with a fresh email, and check in the database (Postgres MCP or `manage.py shell`) that a `SignupSite` row points at the directory site.
4. Log in with that email on `http://productivity.localhost:$DJANGO_PORT/accounts/login/` and confirm the session there is separate: logging out on one domain leaves the other logged in.
5. Trigger a password reset from the productivity host. In the console email backend output, the From address and the subject prefix are the productivity site's.
