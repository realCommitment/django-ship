# 03-go-live: deployed on Railway with two real domains

Product spec: `docs/specs/00-product/spec.md`. Builds on 08-railway (`Dockerfile`, `.railway/railway.ts`, `deploy/pre_deploy.sh`, production settings) and 02-sites (`SITES`, `sync_sites`). Rewritten for Railway on 2026-10-19; the Render version is in git history.

## Goal

The app runs on Railway from `.railway/railway.ts`, serving the directory and productivity sites on two real domains over HTTPS. Postmark sends each site's mail from its own verified domain, Sentry receives errors from web, worker and beat, uploads land in the Railway bucket, and beat runs scheduled tasks. Most steps are the owner's, done in dashboards and DNS from the owner's machine (no production actions run from the agent's machine). The agent prepares config changes, verifies from outside, and records the evidence.

## Owner steps (in order)

1. **Push the repo to GitHub.** Private `alpha-bravo-lima/django-ship`, `main` pushed. Railway deploys from it.
2. **Railway account.** Pro plan. In account settings set the preferred region to US East (Virginia) before creating anything: Postgres and Redis volumes are created in the preferred region and cannot move. Connect the GitHub app to the repo and accept its updated permissions (needed for "Wait for CI", which `checkSuites: true` switches on).
3. **Spending.** Set the hard spending limit and the usage alerts (https://docs.railway.com/pricing/cost-control). At the hard limit every workload in the workspace goes offline.
4. **Apply the config** from a checkout with the Railway CLI and `npm ci` done:
   ```
   railway login && railway init   # or railway link to an existing empty project
   DIRECTORY_DOMAIN=<directory domain> PRODUCTIVITY_DOMAIN=<productivity domain> railway config plan
   DIRECTORY_DOMAIN=... PRODUCTIVITY_DOMAIN=... railway config apply
   ```
   It creates `postgres`, `redis`, the `media` bucket and the `web`, `worker` and `beat` services. The first deploy fails on purpose: the `preserve()` variables are still empty.
5. **Secrets** in the dashboard, on each of the three services (or as shared variables referenced from all three): `SECRET_KEY`, `ADMINS`, `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL`, `DIRECTORY_FROM_EMAIL`, `PRODUCTIVITY_FROM_EMAIL`, `STRIPE_LIVE_MODE`, the Stripe secret key of that mode, the two portal ids (step 9), `POSTMARK_SERVER_TOKEN`, `SENTRY_DSN`. Optionally `TURNSTILE_KEY` and `TURNSTILE_SECRET` from a Cloudflare Turnstile widget listing both domains; unset, sign-up has no captcha. Then redeploy.
6. **Domains.** `railway.ts` already lists both custom domains on the web service. Create the CNAME records Railway shows and wait for the certificates (https://docs.railway.com/networking/domains/working-with-domains).
7. **Postmark.** A server with its token. A sender domain per site, with the DKIM and Return-Path DNS records verified.
8. **Sentry.** One project with its DSN, used by all three services.
9. **Stripe settings needed to start.** Production refuses to start without `STRIPE_LIVE_MODE`, the matching secret key and a Customer Portal configuration id per site.
   - Go live in Stripe test mode first: `STRIPE_LIVE_MODE=false` plus the test keys.
   - The portal ids must exist before the first successful deploy, and `create_portal_configurations` reads plans from dj-stripe's synced tables. Create them from a throwaway Orca worktree, which has its own database: set that mode's Stripe keys in the worktree's `.env`; run `djstripe_sync_models Product Price`, then `create_portal_configurations`; copy the printed ids into Railway; remove the worktree with `--run-hooks`.
   - Repeat with the live keys when switching to live mode. Before switching, clear any test-mode customer links (see `docs/specs/06-billing/implementation-notes.md`).
   - After the first deploy: create the dj-stripe `WebhookEndpoint` in the admin; add the features (`productivity.export`, `directory.featured_listing`) and their product values in the admin (until then those demo pages answer 500, the fail-loud behaviour for unknown features); run `djstripe_sync_models Product Price` with `railway run` or `railway ssh` on the web service.
10. **Turnstile** (if used). Add both domains to the widget's hostname list.
11. **First admin.** Email verification is mandatory (04-account-security). Sign up on a site, verify the email, then run `manage.py promote_user_to_superuser <email>` on the web service.
12. **Backups.** In the Postgres service's volume settings switch on daily, weekly and monthly backups, then follow the restore drill in https://docs.railway.com/guides/postgres-backups-restores once. The off-site dump is `09-offsite-backup`.

## Agent changes

- `.railway/railway.ts`: the region, if the owner picks another one; nothing else should need a change for go-live.
- Raise `SECURE_HSTS_SECONDS` through its env var after a week with no issues. Not in this spec's commit.

## Known risks to check first if the first deploy fails

- **The health check gets a 400.** It arrives as `healthcheck.railway.app`, which production settings always allow, and `RAILWAY_PUBLIC_DOMAIN` is appended when set. If logs show `DisallowedHost` for another host, add it.
- **The pre-deploy step fails.** It runs `migrate`, `sync_sites` and `bootstrap_celery_tasks` from the new image with the service's variables; `sync_sites` needs `DIRECTORY_DOMAIN` and `PRODUCTIVITY_DOMAIN`, which `railway.ts` sets from the shell at apply time.
- **Uploads fail.** The bucket's Credentials tab says whether it needs virtual-hosted or path-style URLs; the settings assume virtual-hosted (`AWS_S3_ADDRESSING_STYLE = "virtual"`).
- **Worker or beat run new code before the web's migrations finish.** Accepted by design; migrations must work with the previous release's code.
- **`preserve()` on a variable that was never set.** Untested whether `railway config plan` accepts it on a fresh project. If it refuses, set the secrets in the dashboard first, then apply.

## Not in this spec

The billing end-to-end runs (06, 07), beyond the Stripe settings production needs to start. Raising HSTS. The off-site backup (09). Monitoring beyond Sentry.

## End-to-end verification (agent, from this machine)

1. `curl -sI https://<directory domain>/` and `https://<productivity domain>/` return 200 with HSTS. Their `<title>` values differ, and `curl -sI http://<domain>/` redirects to https.
2. `curl -s https://<domain>/health/` returns `{"status": "ok"}`, and the Railway dashboard shows the web service healthy (owner screenshot).
3. Sign up on each domain with a real inbox the owner controls. The verification emails arrive from each site's sender, and Postmark's activity shows both.
4. A superuser opens `/simulate_error/` on one domain, and the event appears in Sentry with the production environment.
5. Upload a profile picture. Its URL is a presigned bucket URL and loads.
6. The beat log shows `beat: Starting...` and, within a day, the worker log shows the session-cleanup task running.
