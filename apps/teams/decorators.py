from collections.abc import Callable
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404

from .models import Team

# Adapted from Keel's TeamMemberRequiredMixin and TeamAdminRequiredMixin (MIT): apps/teams/permissions.py


def team_member_required(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """Set request.team and request.membership from the URL's team_slug; 404 unless a member on this site."""

    @wraps(view)
    @login_required
    def wrapper(request: HttpRequest, team_slug: str, *args, **kwargs) -> HttpResponse:
        team = get_object_or_404(Team.objects.for_user(request.user).filter(site=request.site), slug=team_slug)
        request.team = team  # type: ignore[attr-defined]
        request.membership = team.memberships.get(user=request.user)  # type: ignore[attr-defined]
        return view(request, team_slug, *args, **kwargs)

    return wrapper


def team_admin_required(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """As team_member_required, then 403 unless the member is an admin."""

    @wraps(view)
    @team_member_required
    def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not request.membership.is_admin:  # type: ignore[attr-defined]
            raise PermissionDenied("Only team admins can do this.")
        return view(request, *args, **kwargs)

    return wrapper
