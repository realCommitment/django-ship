from functools import partial

from allauth.account.utils import filter_users_by_email
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .adapter import INVITATION_SESSION_KEY
from .decorators import team_admin_required, team_member_required
from .forms import InvitationForm, RoleForm, TeamForm
from .models import Invitation, Membership, Role, Team, validate_role_change
from .tasks import send_invitation_email


@login_required
def create_team(request) -> HttpResponse:
    form = TeamForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        base = slugify(form.cleaned_data["name"])[:90] or "team"
        slug, n = base, 1
        # shortcut: two teams named alike created at the same moment can race to one slug (IntegrityError, 500)
        while Team.objects.filter(site=request.site, slug=slug).exists():
            n += 1
            slug = f"{base}-{n}"
        with transaction.atomic():
            team = Team.objects.create(site=request.site, name=form.cleaned_data["name"], slug=slug)
            Membership.objects.create(team=team, user=request.user, role=Role.ADMIN)
        return redirect(team)
    return render(request, "teams/create_team.html", {"form": form, "active_tab": "create_team"})


@team_member_required
def team_home(request, team_slug) -> HttpResponse:
    return render(request, "teams/team_home.html", {"active_tab": "team_home"})


@team_member_required
def members(request, team_slug) -> HttpResponse:
    context = {
        "memberships": request.team.memberships.select_related("user").order_by("user__email"),
        "invitations": request.team.invitations.open().order_by("email"),
        "roles": Role.choices,
        "active_tab": "team_members",
    }
    return render(request, "teams/members.html", context)


@team_admin_required
def invite(request, team_slug) -> HttpResponse:
    form = InvitationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email, role = form.cleaned_data["email"].lower(), form.cleaned_data["role"]
        # get_or_create on the open invitation (Read the Docs' InvitationQueryset.invite): repeating sends no duplicate
        invitation, created = Invitation.objects.open().get_or_create(
            team=request.team, email=email, defaults={"role": role, "invited_by": request.user}
        )
        if not created and not invitation.is_expired:
            messages.info(request, _("%(email)s already has a pending invitation.") % {"email": email})
            return redirect("teams:members", team_slug)
        if not created:  # resend an expired invitation, from this admin, with a fresh expiry and the role just chosen
            invitation.role, invitation.invited_by, invitation.sent_at = role, request.user, timezone.now()
            invitation.save(update_fields=["role", "invited_by", "sent_at", "updated_at"])
        # the worker must see the committed row
        transaction.on_commit(partial(send_invitation_email.delay, invitation.pk))
        messages.success(request, _("Invitation sent to %(email)s.") % {"email": email})
        return redirect("teams:members", team_slug)
    return render(request, "teams/invite.html", {"form": form, "active_tab": "team_members"})


@team_admin_required
@require_POST
def revoke_invitation(request, team_slug, invitation_id) -> HttpResponse:
    with transaction.atomic():
        # waits for an accept in progress, then finds the row no longer open
        invitation = get_object_or_404(
            Invitation.objects.open().select_for_update(), pk=invitation_id, team=request.team
        )
        invitation.delete()
    messages.success(request, _("Invitation to %(email)s revoked.") % {"email": invitation.email})
    return redirect("teams:members", team_slug)


@team_admin_required
@require_POST
def change_role(request, team_slug, membership_id) -> HttpResponse:
    target = get_object_or_404(Membership, pk=membership_id, team=request.team)
    form = RoleForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Choose a valid role."))
        return redirect("teams:members", team_slug)
    try:
        with transaction.atomic():
            validate_role_change(request.membership, target, form.cleaned_data["role"])
            target.role = form.cleaned_data["role"]
            target.save(update_fields=["role", "updated_at"])
    except ValidationError as e:
        messages.error(request, e.messages[0])
    else:
        messages.success(
            request,
            _("%(user)s now has the role %(role)s.")
            % {"user": target.user.get_display_name(), "role": target.get_role_display()},
        )
    return redirect("teams:members", team_slug)


def _remove(request, target: Membership, success_message: str) -> HttpResponse:
    try:
        with transaction.atomic():
            validate_role_change(request.membership, target, None)
            target.delete()
    except ValidationError as e:
        messages.error(request, e.messages[0])
        return redirect("teams:members", request.team.slug)
    messages.success(request, success_message)
    if target.user_id == request.user.pk:
        return redirect("web:home")
    return redirect("teams:members", request.team.slug)


@team_admin_required
@require_POST
def remove_member(request, team_slug, membership_id) -> HttpResponse:
    target = get_object_or_404(Membership.objects.select_related("user"), pk=membership_id, team=request.team)
    return _remove(
        request,
        target,
        _("%(user)s was removed from %(team)s.") % {"user": target.user.get_display_name(), "team": request.team},
    )


@team_member_required
@require_POST
def leave(request, team_slug) -> HttpResponse:
    return _remove(request, request.membership, _("You left %(team)s.") % {"team": request.team})


def invitation(request, token) -> HttpResponse:
    """Show an invitation; accepting is a POST, so email link scanners can't accept it. Shape from Read the Docs."""
    # another site's token is not found here
    invitation = get_object_or_404(
        Invitation.objects.open().select_related("team"), token=token, team__site=request.site
    )
    user = request.user if request.user.is_authenticated else None
    try:
        invitation.validate(user)
        if user is None:
            if filter_users_by_email(invitation.email):
                return redirect_to_login(request.get_full_path())
            # redeemed by the account adapter once the new account's email is verified
            request.session[INVITATION_SESSION_KEY] = invitation.pk
            return redirect("account_signup")
        if request.method == "POST":
            invitation.accept(user)
            messages.success(request, _("You joined %(team)s.") % {"team": invitation.team})
            return redirect(invitation.team)
        error = None
    except ValidationError as e:
        error = e.messages[0]
    return render(request, "teams/invitation.html", {"invitation": invitation, "error": error})
