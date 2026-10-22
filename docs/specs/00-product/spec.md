# 00-product: one Django foundation for a portfolio of sites

Agreed 2026-10-17 (planning conversation, draft 3 of `PLAN.md`). Changed only through an interview or by hand; implementation sessions only tick boxes in `## Specs`.

## Goal

One Django codebase and one deployment that serves many sites on their own domains (first a business directory and a productivity app). It gives every site accounts, teams, Stripe billing and 2FA, and deploys to Railway on every green push. It stays MIT, so the code can be published or sold. Everything is built from patterns that already run in production elsewhere; each spec names its source.

## Users and what they can do

- **The owner (solo developer).** Adds a new site by creating a Django app, a `Site` record, its plans and a domain on Railway. Accounts, teams and billing need no changes. Builds with Claude Code; merges Pegasus releases from `upstream`.
- **A visitor.** Sees one brand per domain, server-rendered and indexable, and never notices the shared backend.
- **A person with an account.** Signs up once; the same account works on every site. Logs in separately on each domain, because cookies are per domain. Can turn on 2FA.
- **A team admin.** Creates a team on a site (on the directory it is labelled a "business" and owns listings), invites people by email, manages roles, subscribes on Stripe Checkout and manages billing in the Customer Portal.
- **A team member.** Uses the team's paid features on that site only.

## Anti-goals

- No cross-domain single sign-on. One login per domain.
- No separate accounts per site. allauth's global unique email stays.
- No schema-per-tenant (django-tenants) and no per-site database.
- No SPA. React can be added later for single screens, mounted inside Django pages.
- No per-seat or usage-based pricing, no card-less trials, no Stripe Entitlements, no Paddle, for now.
- No API keys, impersonation, translations or CMS.
- No deploy targets other than Railway for now (Render was planned, never deployed; replaced by 08-railway on 2026-10-19).
- No changes to Pegasus's own files beyond what a spec needs. New code goes in new apps, so `git merge upstream/main` stays easy.
- No account deletion or data export yet (needed before an EU launch).

## Architecture decisions

- **Base: SaaS Pegasus open-source edition (MIT), full history, `upstream` remote.** Best code quality of the free options, HTMX + Tailwind + Vite front end, good `CLAUDE.md`, monthly releases that land as merges into upstream `main`.
- **Sites: one `django.contrib.sites` record per domain, `SITE_ID` removed.** allauth, sitemaps and email links already read the current site from the request.
- **Routing: middleware looks up `Site.objects.get_current(request)` and sets `request.site`, `request.urlconf` and a base template per site; unknown domains redirect to the main site.** Our sites are different products. Pattern from envergo (MIT, a live French government service running two products from one deployment): https://github.com/MTES-MCT/envergo/blob/main/envergo/contrib/middleware.py
- **Per-site settings in one settings dict keyed by site** (name, sender address, analytics ID, Stripe portal configuration). Site records are created in data migrations. envergo uses `FROM_EMAIL[site]` and site migrations.
- **Background tasks receive a site id** and render per-site email templates. envergo `users/tasks.py`.
- **Accounts: one global user, plus a record of the site a person signed up on.** Takahē, Plane, DareFail (global user); Open edX `UserSignupSource` (signup site).
- **Teams belong to one site; the payer is always a team; a directory "business" is a team on the directory site.** One payer type and one set of invite and billing code for every site.
- **Teams code: Keel's model shape (MIT), Read the Docs' invite flow (MIT), PostHog's invite checks and row locking (MIT outside `ee/`).** django-organizations was rejected: its invites create inactive users and bypass allauth.
- **Two roles, admin and member; the last admin cannot be removed or demoted.** Pegasus uses two roles; Read the Docs has the last-owner guard.
- **Billing: dj-stripe 2.11 with Stripe Checkout and Customer Portal; each team links to its dj-stripe customer and subscription, re-picked after every webhook.** Read the Docs' design (MIT); duplicate and out-of-order events do no harm. dj-stripe declares Django 6.0 and 6.1.
- **One Stripe account; a separate Stripe customer per team, tagged with its site; one portal configuration per site; one webhook endpoint.** Keeps each site's portal showing only its own plans.
- **Flat prices per plan, trials run by Stripe (`trial_period_days`, card required).** No trial code of our own.
- **Entitlements: admin-editable tables in the style of Chargebee's features (on/off or quantity), a value per Stripe product, free-plan defaults when there is no subscription; lookup logic from Read the Docs' `get_feature`.** Limits change without a deploy.
- **Hosting: Railway, declared in `.railway/railway.ts` and built from a Dockerfile** (08-railway, replacing the Render Blueprint). One web service listing every domain, a worker, a Beat service with one replica, Railway Postgres, Redis and a private storage bucket. The web service's pre-deploy command runs migrations; deploys wait for green GitHub checks. Managed services, automatic HTTPS per domain.
- **Production settings from cookiecutter-django (BSD-3):** required secret key, security and HSTS block, whitenoise, django-storages (Railway bucket, S3 API), Anymail (Postmark), Sentry with Celery.
- **2FA: `allauth.mfa` (TOTP and recovery codes), passkeys off.** Same library as login.
- **Explicit team filters in queries, with isolation tests.** Less magic than an auto-scoping manager.
- **Migrations must work with the previous release's code.** Railway deploys the web, worker and beat services separately, and only the web service runs the pre-deploy migrations.

Licenses: MIT, BSD and Apache code may be copied with its notice kept. AGPL code and paid templates (Pegasus Pro, pretix) are used for ideas only.

## Specs

- [x] 00-saas-layer: the fork is documented and green. A Context map of where things live, Pegasus's names and emails replaced, the Pegasus-account skills removed, upstream-merge and fail-loud rules in `CLAUDE.md`. `make test`, pre-commit and mypy pass.
- [x] 01-production: production settings and the Render Blueprint (the Blueprint was replaced by 08-railway). Locally the production settings run under gunicorn, serve static files through whitenoise, answer `/health/` with 200 and pass `manage.py check --deploy`.
- [x] 02-sites: two sites from one deployment. `directory.localhost` and `productivity.localhost` each show their own landing page, robots.txt, sitemap and email branding. An unknown host redirects to the main site, and the signup site is recorded.
- [ ] 03-go-live: deployed on Railway with two real domains over HTTPS, Postmark sending from each domain, Sentry receiving errors, uploads in the Railway bucket. Needs the owner's accounts and DNS. Do 08-railway first.
- [x] 04-account-security: 2FA with an authenticator app and recovery codes, and mandatory email verification. A user who turns 2FA on must enter a code to log in.
- [x] 05-teams: teams per site with email invitations, admin and member roles, and a last-admin guard. Two people work in one team, and that team returns "not found" from the other site.
- [ ] 06-billing: team billing and entitlements. In Stripe test mode a team admin subscribes through Checkout, the team gets the plan's features, loses them after cancelling, and an admin edit to a feature value takes effect without a deploy.
- [ ] 07-site-billing: billing per site. A directory business and a productivity team are billed separately from one Stripe account, each sees only its own site's plans in the portal, and both return to the domain they paid on.
- [x] 08-railway: the Railway deployment, declared in `.railway/railway.ts` and built from a Dockerfile. The image builds, serves `/health/`, runs the pre-deploy step, the worker and beat locally; Render is removed.
