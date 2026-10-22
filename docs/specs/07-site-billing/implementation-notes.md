# 07-site-billing: implementation notes

## Stopped before the Stripe steps

There are no Stripe test keys in this checkout's `.env` and the Stripe CLI is not installed, so I followed the spec's step 6. Everything is built and tested with Stripe mocked. The parts that need no Stripe were driven against the running app. Steps 2 to 4 were not run: `create_portal_configurations` against Stripe, a real Checkout, and the real portal. The `07-site-billing` box in the product spec stays unticked. Nothing in this session called the Stripe API.

## Decisions not in the spec

- **Production requires a portal configuration for every site.** `settings_production.py` raises `ImproperlyConfigured` ("No Stripe portal configuration for directory, productivity: run manage.py create_portal_configurations and set <SITE>_STRIPE_PORTAL_CONFIGURATION") when any `SITES` entry has an empty `stripe_portal_configuration`. Reason: Stripe's default portal offers whatever products the dashboard's default configuration lists. If that list includes both sites' products, a directory business could switch to a productivity plan. The check runs over `SITES`, so it catches a value that is unset or set but empty (a Render prompt left blank), and a third site added without its id. `render.yaml` prompts for both keys on both services, because the worker loads the same settings. CI's production check gets dummy `bpc_ci_only_*` values. Development keeps the empty default, which means Stripe's default portal.
- **That makes the ids a precondition of the first deploy.** The services do not start without them. Run the command where the plans are synced (locally, after `djstripe_sync_models Product Price` with the same Stripe key), then put the printed ids into the Render prompts.
- **Every site in `SITES` gets a configuration, including a site without plans.** That site's `subscription_update` is `{"enabled": False}`, and the rest is the same. The spec says "for each site with products", but production needs an id for every site, so skipping planless sites would leave production unable to start. A rerun after a site's last plan was archived also turns plan changes off, instead of leaving the old list. (Changed after code review; the first version skipped those sites.)
- **The command reads the plans from dj-stripe's synced tables, not from Stripe.** It uses the Billing page's filter: active recurring prices in the current mode on active products tagged `metadata.site`. I moved that filter from `views._site_prices(request)` to `utils.site_prices(site_key)` so both use the same one. The portal therefore offers exactly what the Billing page offers. Sync before running the command, and run it again after adding or archiving a price, because the configuration keeps the list it was given.
- **Idempotent through `metadata.site` on the configuration.** The command lists the active configurations (`Configuration.list(active=True)`, all pages), takes the one whose `metadata.site` is the site key, and modifies it. If there is none, it creates one. A configuration made by hand in the dashboard (no `metadata.site`) is never adopted, and a deactivated one is never reused. Stripe's default configuration is left alone. If two active configurations carry the same `metadata.site`, the command stops with a `CommandError` naming both ids before it writes anything. (Added after code review.)
- **Configuration contents:** `business_profile.headline` is the site name. `default_return_url` is `https://<SITES domain>/`. `subscription_update` is on, with `default_allowed_updates: ["price"]` (flat prices, no quantity) and the site's products with their prices. Payment method update, invoice history and cancellation are on. Proration, cancellation mode (at period end) and the rest stay at Stripe's defaults. Customer details update is not turned on, because the spec doesn't list it. Stripe allows up to 10 products in `subscription_update`. A site with more gets Stripe's error, uncaught.
- **Printed line:** `Created directory: DIRECTORY_STRIPE_PORTAL_CONFIGURATION=bpc_...` (or `Updated`). The env name is the site key in capitals plus `_STRIPE_PORTAL_CONFIGURATION`, as the spec names the two keys.
- **The cross-site Checkout POST answers 404, not 400.** Spec step 5 says "capture the 400", but the same spec says to keep `test_checkout_refuses_another_sites_price_and_a_second_plan`, which asserts 404. I kept 06's behaviour. Another site's price gets the same answer as any unknown price id, so the response does not reveal that the price exists elsewhere.
- **The portal turns an empty configuration into None.** stripe-python leaves out a None parameter, so Stripe's default portal applies. Passed as `""`, it would send an empty `configuration`. 06 read the key with `.get()`. Every entry now has it, so the view reads it with `[]`, and an entry without the key raises `KeyError`.
- **The demo gate** `/a/<slug>/featured/` is in the directory's URLs only (404 on productivity). It renders "Your plan includes a featured listing." like 06's export page. No data migration adds the feature (06's reason: the Site rows come from `sync_sites`, after `migrate`). The owner adds `directory.featured_listing` in the admin. Until then the page answers 500 (`Feature.DoesNotExist`).
- **stripe-python 15's `StripeObject` is not a dict.** It has no `.get()`, so the metadata lookup uses `"site" in config.metadata` and `config.metadata["site"]`. mypy caught this. My first test fakes were plain dicts and passed anyway, so the fakes are now real `StripeObject`s (`stripe.convert_to_stripe_object`).
- **Tests (8 new, 40 in `apps/billing/tests`):**
  - a directory business sees only directory plans;
  - directory Checkout refuses a productivity price, and its success and cancel URLs are on the directory host;
  - each site's portal session gets that site's configuration id and returns to that site's host;
  - the command run twice updates instead of duplicating, and sends the same contents both times;
  - a site without plans gets a configuration with plan changes off;
  - two configurations tagged with one site stop the command;
  - a directory team's events update only that team;
  - the directory gate redirects a free business and opens for a subscribed one.

  The portal tests set `SITES` with `override_settings`, so they no longer depend on the environment. Spec step 2 puts real ids into `.env`, and the 06 test that expected `configuration=None` would then have failed.

## What the owner needs before the end-to-end step

The spec's list and 06's list, plus:

- In the admin: add the feature `directory.featured_listing` (site Business Directory, on/off, free value 0) and give the paid directory products the value 1.
- Run `uv run manage.py create_portal_configurations` after `djstripe_sync_models Product Price`. Put the two printed lines into `.env` and restart `runserver`.
- For production (03-go-live): the same two keys in the Render prompts on both services, from a run against the same Stripe account and mode. Without them neither service starts.

## Things you should know

- **One configuration per site per Stripe account and mode.** Every environment on the shared test account finds the same configurations by `metadata.site`: dev worktrees and a test-mode production alike. Running the command anywhere updates them for everyone. That includes `default_return_url`, which becomes the domain of the environment that ran it last. Our portal sessions always pass the Billing page as `return_url`, so this only affects a portal opened without a session, which we don't use.
- **Pegasus files touched:** `project/settings.py` (one key in each `SITES` entry) and `project/settings_production.py` (the check). Also `.env.example`, `render.yaml` and `.github/workflows/tests.yml`. The rest is in our apps: `apps/billing`, `apps/directory`, `templates/directory`.

## Code review

`/code-review medium`, with the django-ship repository and the range `3a47937..HEAD` plus the working tree named in the arguments. All 10 findings were about django-ship files.

Fixed:

- Production required an id for every site, but the command skipped sites without plans and printed no id for them. A site added before its products (or a free site) would have kept every service from starting. Every site now gets a configuration, with plan changes off when it has no plans. Test: `test_a_site_without_plans_gets_a_portal_without_plan_changes`.
- A site whose plans were all archived was skipped, so its configuration kept offering the old plans. Same fix: the rerun turns plan changes off.
- Two active configurations with the same `metadata.site` were resolved silently: the one Stripe listed last was updated. The command now stops and names both. Test: `test_two_configurations_for_one_site_stop_the_command`.
- The production check read `site["stripe_portal_configuration"]`, so a `SITES` entry without the key raised a bare `KeyError`. It now uses `.get()` and raises its own message.

Skipped:

- "The portal view's `[...]` raises `KeyError` for an entry without the key." Every entry defines it, and a missing key in code should fail loudly. The error names the key, and production now stops at startup with a clear message first.
- "A deactivated configuration is not found, so a rerun creates a new one." That is what the owner needs: a deactivated configuration cannot open portal sessions. The command prints the new id to put in env. Silently reactivating the old one would undo the owner's choice.
- "More than 10 products, or any other Stripe error, stops the loop partway, and the traceback does not name the site." The command prints one line per finished site, so the last line shows how far it got. A rerun is safe. Stripe's error names the parameter.
- "The `directory.featured_listing` row has no migration, so the gate answers 500 until the owner adds it." This is 06's decision, for 06's reason. It is under What the owner needs.
- "Step 5 expects 400, the code answers 404." This is a conflict inside the spec, written up under Decisions. **Your call** if you want 400.
- "`sites_with_portals` deep-copies `SITES` at import, so env-set domains leak into the tests." 06's tests already hard-code `http://productivity.localhost`. Domains are set only in production, so these tests do not run with them.
- "The `Created`/`Updated` label recomputes `key in existing`." Cosmetic.

## Environment

- **`make` is not installed on this machine.** I ran the Makefile recipes directly through `~/.local/bin/mise exec --`: `make test` is `uv run manage.py test`, `make type-check` is `uv run mypy .`. The dev server ran as `uv run manage.py runserver 38697 --noreload`, without Vite, so the pages had no CSS.
- **No browser.** I drove the app with a Python `requests` script (one cookie jar per person, CSRF tokens from the forms) against `http://directory.localhost:38697` and `http://productivity.localhost:38697`. The rows that stand in for Stripe were created through `manage.py shell` against the same database: products and prices as a sync leaves them, and for the subscription a customer, a subscription and an item. Then the real `update_team_subscription` receiver ran with the event dj-stripe would pass.
- **`check --deploy` under production settings** ran in a `git archive HEAD` export with no `.env`, using the venv's Python, CI's variables and the dev database. The built Vite manifest was copied in from the checkout, as 04's notes describe.
- **Dev database:** I added demo rows and deleted them afterwards: two `site-billing-e2e-*` users with their email addresses and sessions, the teams `e2e-biz` (directory) and `e2e-team` (productivity), three products and prices, a customer, a subscription and its item, and the feature with its value. The counts again match the start of the session: 3 users, 6 sessions, no teams, dj-stripe rows or features. No migrations were added.
