# 05-teams: teams per site with email invitations

Product spec: `docs/specs/00-product/spec.md`. Builds on 02-sites (`request.site`, `request.site_key`) and 04-account-security (verified emails).

## Goal

People work together in teams. A team belongs to one site; on the directory it is labelled a "business", the same code under another label. A team has admins and members. Admins invite people by email, and an invite can be accepted only by someone whose verified email matches it. Team pages live under `/a/<team_slug>/` and show "not found" to anyone who isn't a member or who is on another site. The last admin can't be removed, demoted or leave. This team is what 06-billing charges.

Sources (MIT; keep a one-line source comment where code is adapted):
- **Model shape and permission mixins**: Keel. https://github.com/CuriousLearner/django-keel/tree/main/template/apps/%7B%25%20if%20use_teams%20%25%7Dteams%7B%25%20endif%20%25%7D
- **Invite flow**: Read the Docs.
  - https://github.com/readthedocs/readthedocs.org/blob/main/readthedocs/invitations/models.py
  - https://github.com/readthedocs/readthedocs.org/blob/main/readthedocs/invitations/views.py
  - https://github.com/readthedocs/readthedocs.org/blob/main/readthedocs/core/adapters.py
- **Invite validation and row locking**: PostHog. https://github.com/PostHog/posthog/blob/master/posthog/models/organization_invite.py
- **Last-owner guard and queryset helpers**: Read the Docs. https://github.com/readthedocs/readthedocs.org/blob/main/readthedocs/organizations/querysets.py

## What the user can do afterwards

- Create a team on a site, which makes them its admin, and see it at `/a/<slug>/` on that site.
- Invite someone by email as admin or member. The invite email links to the same site's domain.
- As the invitee:
  - logged out with an account: open the link, log in, then accept;
  - logged out without an account: open the link, sign up with the invited email, verify it, and land in the team;
  - logged in: accept with one click (a POST).
- Switch between their teams on a site.
- As an admin: change roles, remove members and revoke pending invites.
- As any member: leave. The last admin can't leave or be removed or demoted.
- Find the team invisible from the other site: `/a/<slug>/` on the other domain returns 404.

## Anti-goals

- No billing (06-billing) and no per-seat logic.
- No teams that span sites, and no team transfer between sites.
- No owner role. Two roles only: admin and member.
- No automatic team-scoping manager or ContextVar. Use explicit `.filter(team=...)` and tests.
- No API endpoints for teams. Server-rendered views with HTMX where it helps.
- No django-organizations: its invites create inactive users and bypass allauth.

## Files and interfaces

New app `apps/teams`.

- **Models**, all extending `BaseModel`:
  - **`Team`**: `site` (FK to `Site`), `name`, `slug`, with `UniqueConstraint(fields=["site", "slug"])`. There is no owner field; the admin role is the owner.
  - **`Membership`**: `team`, `user`, `role`, where `role` is an `IntegerChoices` with `MEMBER = 1` and `ADMIN = 8` (PostHog's levels, leaving room between them). `UniqueConstraint(team, user)`.
  - **`Invitation`**:
    - fields: `team`, `email` (stored lowercased), `role`, `token` (`secrets.token_urlsafe(32)`, unique), `invited_by`, `sent_at`, `accepted_at` (null);
    - a partial `UniqueConstraint(fields=["team", "email"], condition=Q(accepted_at__isnull=True))`, so there is only one open invite per address and someone can be re-invited after leaving;
    - expiry is `sent_at + TEAM_INVITATION_EXPIRY_DAYS` (setting, default 14), and resending bumps `sent_at`;
    - queryset helpers `open()` and `expired()`.
- **Querysets**:
  - `TeamQuerySet.for_user(user)`, a membership join;
  - a `Membership` helper to count admins for the last-admin guard.
- **Team lookup**:
  - `get_object_or_404(Team.objects.for_user(request.user).filter(site=request.site), slug=team_slug)`.
  - Two decorators, `team_member_required` and `team_admin_required`, that perform it and set `request.team` and `request.membership`.
- **Invite flow**:
  - Creating an invite uses `get_or_create` on the open invite, so repeating it sends no duplicate.
  - The email is sent by a Celery task that receives the invitation id. It builds the absolute URL from `invitation.team.site.domain` and uses that site's `from_email`, following the 02-sites rule that tasks never guess the site.
  - `GET /invitations/<token>/` shows the invite. Accepting is a `POST`, so email link scanners can't accept it.
  - Validation with error codes, in PostHog's style:
    - **expired**: rejected;
    - **wrong site**: the token is used on a domain other than the team's site; rejected with 404;
    - **already a member**: rejected;
    - **email mismatch**: the user has no verified allauth `EmailAddress` equal (case-insensitive) to the invite email; rejected.
  - A logged-out visitor with an account goes to login with `next` set to the invite page.
  - A logged-out visitor without an account: store the invitation id in the session and go to signup. After the email is verified, the allauth adapter redeems the invite, but only if the user's verified email matches it. Read the Docs skips that check.
  - `accept()` runs in `transaction.atomic()` with `select_for_update()` on the invitation, then creates the membership and sets `accepted_at`. A double POST creates one membership.
  - Revoking is a POST-only, admin-only delete.
- **Roles**:
  - A `validate_role_change()` that blocks removing, demoting or self-removing the last admin, and blocks non-admins from changing roles.
  - Any member may leave unless they are the last admin.
- **Views and templates**:
  - `templates/teams/` extending `web/app/app_base.html`, using DaisyUI components.
  - Create team, team home, members list with role controls, pending invites, invite form, team switcher in the app nav. Keep Pegasus nav changes to one include.
- **URLs**: add the teams routes to the shared routes so every site gets them: `a/<slug:team_slug>/...` and `invitations/<token>/`.
- **Site key helper**: 02-sites has no helper that maps a `Site` row to its `SITES` key; the middleware builds the mapping inline. Add `site_key_for(site) -> str` in `apps/multisite`, make the middleware use it, and use it wherever a task or model needs the key (the invite email task, `Team.site_key` property).
- **Labels**: a per-site team label in `SITES` (`"team_label": "Business"` for the directory, `"Team"` for productivity), used in templates.
- **Admin**: register `Team`, `Membership` and `Invitation` for the owner's use.
- **Tests**:
  - Copy the shape of Read the Docs' invitation view tests: expired, another user, anonymous, logged in, decline/revoke.
  - Case-insensitive email match.
  - An unverified matching email is rejected.
  - Re-invite after leaving works.
  - A double POST accept creates one membership.
  - The last admin can't leave or be removed or demoted.
  - A team created on the directory returns 404 at the same URL on the productivity host.
  - A non-member gets 404.
  - Every team URL, checked with anonymous, member and admin, returns the expected status (Read the Docs' URL access matrix idea).

## End-to-end verification

1. `make test`, pre-commit and `make type-check` are clean.
2. Start the dev server and a Celery worker (or `CELERY_TASK_ALWAYS_EAGER=True` for this run, noted in the evidence). With the Playwright MCP:
   - user A signs up on `directory.localhost`, verifies, and creates a business;
   - A invites `b@example.com` as a member;
   - from the console email output, open the invite link logged out, sign up as B with that email, verify, and land in the business;
   - capture A's members page showing B.
3. As B, try `/a/<slug>/` on `productivity.localhost` and capture the 404.
4. As A, try to leave or demote yourself while you are the only admin and capture the refusal. Then promote B, leave, and capture success.
