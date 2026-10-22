# 04-account-security: 2FA and mandatory email verification

Product spec: `docs/specs/00-product/spec.md`. Context map: `docs/specs/00-saas-layer/spec.md`.

## Goal

A person can protect their account with an authenticator app (TOTP) and one-time recovery codes, using allauth's built-in MFA app (`allauth.mfa`), as cookiecutter-django enables it. Once 2FA is on, logging in on any site asks for a code. Email addresses must be verified before an account can log in, which later specs rely on (05-teams only accepts invites for verified matching emails). Passkeys and WebAuthn stay off.

## What the user can do afterwards

- From their profile page, open "Two-factor authentication", scan a QR code (or copy the secret), confirm a code, and download recovery codes.
- Log out and back in on either site: after the password, they are asked for a TOTP code (or a recovery code) before reaching the dashboard.
- Sign up and find that they must click the emailed verification link before they can log in. In development the link appears in the console email output.

## Anti-goals

- No passkeys, WebAuthn or SMS.
- No forcing 2FA on anyone (no per-team "2FA required" policy).
- No custom MFA views. Use allauth's views, URLs and templates, styled by Pegasus's existing `templates/allauth/` element and layout overrides.
- No change to captcha. Turnstile keys stay global; each domain is added to the widget's hostname list in Cloudflare at go-live.

## Files and interfaces

- **`pyproject.toml`**: `django-allauth[socialaccount,mfa]`, with `uv lock` updated. The mfa extra brings the QR-code dependency.
- **`project/settings.py`**:
  - Add `"allauth.mfa"` to the third-party apps.
  - Rely on allauth's defaults: TOTP and recovery codes are the default supported types, and WebAuthn is off by default. cookiecutter-django sets no `MFA_*` either. Add only what the defaults don't cover, with a comment.
  - `ACCOUNT_EMAIL_VERIFICATION` defaults to `"mandatory"` in all environments and stays overridable from env. If that forces large changes to Pegasus's existing tests, make it production-only instead (`settings_production.py`) and write down why in the notes.
- **URLs**: allauth's `accounts/` include already serves the MFA URLs once the app is installed. Confirm the `mfa_index` route resolves on both site domains.
- **Profile page**: add a link to `mfa_index` in Pegasus's profile template (`templates/account/profile.html` or its components). One small addition. Write down the exact file in the notes.
- **Templates**: allauth's MFA templates extend allauth's layouts, which Pegasus overrides. If any MFA page renders unstyled or breaks, add the smallest override under `templates/mfa/`.
- **Tests** (new `apps/users/tests/test_mfa.py` or similar):
  - a user with a TOTP authenticator who logs in with their password is sent to the 2FA step, not the dashboard;
  - a valid TOTP code completes the login and a wrong one doesn't;
  - a recovery code works once and fails the second time;
  - with mandatory verification, an unverified user can't log in and a verified one can.
  - Generate TOTP codes with the helper allauth's own tests use. Find it in the installed package rather than adding a dependency.

## End-to-end verification

1. `make test`, pre-commit and `make type-check` are clean.
2. Start the dev server and use the Playwright MCP on `http://productivity.localhost:$DJANGO_PORT`:
   - sign up with a fresh email and confirm that login is blocked until verification;
   - open the verification link from the console email output and log in;
   - open the 2FA page from the profile and activate TOTP, computing the code from the shown secret with allauth's helper in `manage.py shell` or with Python's standard library;
   - save the recovery codes, then log out.
3. Log in on `http://directory.localhost:$DJANGO_PORT` with the same account. Capture the 2FA prompt (screenshot or page text), enter a fresh code and capture the dashboard.
4. Log out, log in again using one recovery code, and capture success. Repeat with the same code and capture the rejection.
