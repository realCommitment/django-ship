# 07-site-billing: billing per site

Product spec: `docs/specs/00-product/spec.md`. Builds on 06-billing.

## Goal

The directory gets its own products, features and Customer Portal configuration, billed from the same Stripe account as productivity. A directory business (a team on the directory site) and a productivity team each see only their own site's plans, in our Billing page and in Stripe's portal, and both return to the domain they paid on. One webhook endpoint keeps serving every site.

## What the user can do afterwards

- On `directory.localhost`, a business admin sees the directory plans only, subscribes through Checkout, returns to `directory.localhost`, and gets directory features (demo gate `directory.featured_listing`).
- In the portal opened from the directory, they see directory plans only and can switch between them. The same holds for productivity.
- The owner adds a third site's billing by tagging its Stripe products with `metadata.site`, creating its portal configuration, and adding its id to `SITES`. No code changes.

## Anti-goals

- No second Stripe account and no Stripe Connect.
- No cross-site bundles (one subscription covering two sites).
- No new payer type: a directory business is a `Team`.
- No custom portal UI.

## Files and interfaces

- **`SITES[*]["stripe_portal_configuration"]`**: from env per site (`DIRECTORY_STRIPE_PORTAL_CONFIGURATION`, `PRODUCTIVITY_STRIPE_PORTAL_CONFIGURATION`), default empty. 06's portal view already reads the key with `.get()`, but `SITES` doesn't define it yet. Add it to both entries, `.env.example` and the `render.yaml` placeholders. When it's empty, Stripe's default portal applies, which is fine for development but not for production; decide whether production requires it and record the decision.
- **Management command `create_portal_configurations`**: idempotent.
  - For each site with products tagged `metadata.site=<key>`, create or update a `billing_portal.Configuration`:
    - `business_profile.headline` is the site name;
    - `features.subscription_update` lists only that site's products and prices;
    - payment method update, invoice history and cancellation are on;
    - `default_return_url` is `https://<site domain>/`.
  - Print the ids to put in env.
  - Stripe API reference: https://docs.stripe.com/api/customer_portal/configurations/create
- **Billing page**: already filters prices by `metadata.site == request.site_key` (06). Add a test that a directory business never sees productivity prices.
- **Checkout**: 06-billing already refuses another site's price (`test_checkout_refuses_another_sites_price_and_a_second_plan`). Keep that test, and add a directory-host variant if it only covers productivity.
- **Webhook routing**: unchanged. Each team is its own customer. Add a test that events for a directory team's subscription update only that team.
- **Demo gate**: `/a/<slug>/featured/` on the directory, gated by `directory.featured_listing`.
- **Tests**:
  - price filtering per site;
  - cross-site price rejected at Checkout;
  - the portal session gets the site's configuration id;
  - `create_portal_configurations` run twice updates rather than duplicates (mock Stripe);
  - a directory team's subscription doesn't touch a productivity team.

## What I need from the owner

- In Stripe test mode, one or two directory products with monthly prices tagged `metadata.site = directory`, then `djstripe_sync_models Product Price`.

## End-to-end verification

1. Tests, pre-commit and mypy are clean.
2. Run `create_portal_configurations` against Stripe test mode, capture the two ids, and put them in `.env`.
3. On `directory.localhost`, a business subscribes with the test card. Capture the return to the directory domain, the Billing page and the demo gate open.
4. Open the portal from the directory and capture that only directory plans appear. Do the same from a productivity team.
5. POST a productivity price id to the directory Checkout view and capture the 400.
6. Without Stripe test keys, stop after step 1, say so under Not verified, and leave the checkbox unticked.
