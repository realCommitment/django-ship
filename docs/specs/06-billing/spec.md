# 06-billing: team billing and entitlements

Product spec: `docs/specs/00-product/spec.md`. Builds on 02-sites (`request.site`, `request.site_key`, `SITES`) and 05-teams (`Team`, `team_admin_required`, `/a/<slug>/` URLs).

## Goal

A team admin subscribes their team to a plan on Stripe's hosted Checkout page and manages billing in Stripe's Customer Portal. Prices are flat per plan, and trials are run by Stripe with a card. dj-stripe 2.11 receives Stripe's webhooks, stores and deduplicates the events, and keeps a synced copy of customers, products, prices and subscriptions. Each team points at its dj-stripe customer and current subscription, which is re-picked after every webhook, so duplicate or out-of-order events do no harm.

Features work like Chargebee's. Each site defines features that are either on/off or a quantity, and each Stripe product gives a value per feature, edited in Django admin. Teams without a subscription get the free-plan value. Views and templates check features by name, e.g. `productivity.export`. This spec covers the productivity site end to end; 07-site-billing adds the directory's own products and portal configuration.

Sources (MIT; keep a one-line source comment where code is adapted):
- **Team fields, `get_stripe_subscription()` and customer creation**: Read the Docs.
  - https://github.com/readthedocs/readthedocs.org/blob/main/readthedocs/organizations/models.py
  - https://github.com/readthedocs/readthedocs.org/blob/main/readthedocs/subscriptions/utils.py
- **Webhook handlers**: Read the Docs. https://github.com/readthedocs/readthedocs.org/blob/main/readthedocs/subscriptions/event_handlers.py
- **Checkout and portal views**: Read the Docs. https://github.com/readthedocs/readthedocs.org/blob/main/readthedocs/subscriptions/views.py
- **Feature lookup**: Read the Docs' `get_feature`. https://github.com/readthedocs/readthedocs.org/blob/main/readthedocs/subscriptions/products.py
- **Checkout wrapper and its tests**: Matt Layman's School Desk. https://github.com/mblayman/homeschool/blob/main/homeschool/accounts/stripe_gateway.py
- dj-stripe docs for 2.11: webhooks via the `WebhookEndpoint` model, `djstripe_receiver`, `djstripe_sync_models`.

## What the user can do afterwards

- On `productivity.localhost`, a team admin opens the team's Billing page, sees the productivity plans, and clicks one.
- Stripe Checkout opens: trial, card. After paying, they return to the team's Billing page on the same domain, which shows the plan, the status and the trial end date.
- Team pages gated by a feature (one demo gate, `productivity.export`) work for the paid team and redirect free teams to the Billing page.
- "Manage billing" opens Stripe's Customer Portal and returns to the same domain.
- Cancelling in the portal (at period end, or immediately in test mode) removes the paid features once Stripe reports the subscription as canceled.
- The owner changes a feature's value for a product in Django admin, and the change applies on the next request with no deploy.

## Anti-goals

- No directory billing, no per-site portal configurations beyond productivity's, no second payer type (07-site-billing).
- No per-seat or usage pricing, no card-less trials, no coupons UI (the portal and Checkout can take promotion codes if switched on in Stripe), no Stripe Entitlements, no invoices UI (the portal has them).
- No custom webhook signature or event-storage code: dj-stripe does it.
- No billing for individual users: the payer is always a team.
- No caching of feature values yet. Measure first. The shortcut comment says when to add PostHog's JSON cache.

## Files and interfaces

New app `apps/billing`.

- **Dependencies and settings**:
  - `dj-stripe` 2.11.x and `stripe` via `uv add`. Add `djstripe` to the installed apps.
  - From env: `STRIPE_LIVE_MODE` (default False), `STRIPE_TEST_SECRET_KEY`, `STRIPE_LIVE_SECRET_KEY`, `STRIPE_TEST_PUBLIC_KEY`, `STRIPE_LIVE_PUBLIC_KEY`.
  - The dj-stripe settings its 2.11 docs require, for example `DJSTRIPE_FOREIGN_KEY_TO_FIELD = "id"`. Read the installed package's docs and checks.
  - Add the keys to `.env.example`, and as `sync: false` placeholders to both services in `render.yaml`.
- **Team fields**: add to `Team` (05-teams):
  - `stripe_customer = OneToOneField("djstripe.Customer", null=True, blank=True, on_delete=SET_NULL, related_name="team")`;
  - `stripe_subscription = OneToOneField("djstripe.Subscription", null=True, blank=True, on_delete=SET_NULL, related_name="team")`.
  - `get_stripe_subscription()`, following Read the Docs: pick the customer's subscription by status priority (active, past_due, trialing, then incomplete and others), falling back to the latest.
  - `get_or_create_stripe_customer(team)` (Read the Docs' `utils.py`): creates the Stripe customer with the admin's email, the team name and `metadata={"site": team.site_key, "team_id": team.id}` (`Team.site_key` comes from 05-teams, via `apps.multisite.site_key_for`), and links it through dj-stripe's sync.
- **Feature tables**, extending `BaseModel`, registered in admin with inlines:
  - **`Feature`**: `key`, unique, which must start with `<site_key>.` (validated); `site` FK; `kind` (`on_off` or `quantity`); `free_value` (int; 0/1 for on_off).
  - **`ProductFeature`**: `product` (FK `djstripe.Product`), `feature`, `value`, with a unique `(product, feature)` constraint.
- **`apps/billing/features.py`**:
  - **`get_feature(team, key) -> int`**:
    - Assert the key's site prefix matches `team.site`'s key.
    - If the team's subscription status is entitled (`active`, `trialing`, `past_due`), sum `ProductFeature.value × item quantity` over the subscription items whose product has that feature. For on_off, treat any value above 0 as on.
    - Otherwise, or with no matching rows, return `free_value`.
    - Unknown keys raise. Fail loud.
  - **`has_feature(team, key) -> bool`**.
  - A **`feature_required(key)`** decorator for team views. It is stacked under `team_member_required` and redirects to the team's Billing page with a message.
- **Views** (team admin only, under `/a/<slug>/billing/`):
  - **Billing page**: the current plan and status. The available prices are this site's products, those with Stripe product `metadata.site == request.site_key`, and their active recurring prices from dj-stripe's synced tables.
  - **Checkout (POST)**: `stripe.checkout.Session.create(customer=..., mode="subscription", line_items=[{price, quantity: 1}], client_reference_id=f"{site_key}:{team.id}", subscription_data={"metadata": {...}, "trial_period_days": N if the price or product metadata says so}, success_url=request.build_absolute_uri(...), cancel_url=request.build_absolute_uri(...))`. Then redirect to `session.url`.
  - **Portal (POST)**: `stripe.billing_portal.Session.create(customer=..., return_url=request.build_absolute_uri(...), configuration=SITES[site_key].get("stripe_portal_configuration"))`, then redirect. When no configuration is set, Stripe's default portal applies.
  - **Success page**: the Billing page shows "processing" until the webhook arrives. It doesn't trust the redirect.
- **Webhooks**:
  - One dj-stripe `WebhookEndpoint` (created in admin or with a management command) at its UUID URL.
  - **`apps/billing/handlers.py`**: `@djstripe_receiver` for `customer.subscription.created/updated/deleted` and `checkout.session.completed`. Find the team through `customer.team`, falling back to the `team_id` metadata, then `team.stripe_subscription = team.get_stripe_subscription(); team.save()`.
  - Handlers are synchronous (a few queries), as Read the Docs does it.
- **Demo gate**: one feature-gated page under the productivity team, e.g. `/a/<slug>/export/`. It returns a plain page so the gate can be shown end to end.
- **Dev helper**: a management command that prints the `stripe listen --forward-to http://localhost:$DJANGO_PORT/<dj-stripe webhook URL>` line for this checkout. Seeding Stripe test products is the owner's step (see What I need).
- **Tests**. Mock the Stripe API; never call Stripe in tests.
  - `get_feature`:
    - free team gets the free value;
    - active, trialing and past_due subscriptions get the product value;
    - canceled gets the free value;
    - quantity sums across items;
    - a wrong site prefix raises;
    - an unknown key raises.
  - `get_stripe_subscription` follows the priority order.
  - Webhook handlers update `team.stripe_subscription`. Build dj-stripe objects in the DB as its own tests do; a duplicate event and an out-of-order (older) event leave the right state.
  - Checkout view: only a team admin; builds success and cancel URLs from the request host; passes `client_reference_id` and metadata.
  - Portal view uses the request host for `return_url`.
  - The gate redirects a free team and allows a paid one.
  - An admin edit to `ProductFeature.value` changes `get_feature` on the next call.

## What I need from the owner before the end-to-end step

- `STRIPE_TEST_SECRET_KEY` and `STRIPE_TEST_PUBLIC_KEY` in this checkout's `.env`, and the Stripe CLI logged in (`stripe login`).
- In Stripe test mode, two productivity products with monthly prices, each with `metadata.site = productivity`, then `djstripe_sync_models Product Price` run locally.

## End-to-end verification

1. `make test` (or its recipe), pre-commit and mypy are clean.
2. With test keys, the dev server, `stripe listen` forwarding to the dj-stripe endpoint, and a productivity team:
   - open the Billing page and start Checkout;
   - pay with `4242 4242 4242 4242`;
   - capture the return to `productivity.localhost`, the webhook lines in `stripe listen`, and the Billing page showing trialing or active;
   - capture the demo gate allowing access.
3. Change the plan's `ProductFeature.value` in admin and capture the gate's behaviour change without a restart.
4. Open the portal, cancel immediately, and capture the webhook, then the gate redirecting to Billing.
5. If no Stripe test keys are available, stop after step 1. Say so under Not verified and leave the checkbox unticked.
