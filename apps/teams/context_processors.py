from typing import Any

from django.conf import settings
from django.http import HttpRequest

from .models import Team


def teams(request: HttpRequest) -> dict[str, Any]:
    """The site's name for a team, and the user's teams on this site for the team switcher."""
    context: dict[str, Any] = {"team_label": settings.SITES[request.site_key]["team_label"]}  # type: ignore[attr-defined]
    if request.user.is_authenticated:
        # a lazy queryset: only pages that show the switcher run the query
        context["user_teams"] = Team.objects.for_user(request.user).filter(site=request.site).order_by("name")
    return context
