from django.http import HttpResponse
from django.shortcuts import render

from apps.billing.features import feature_required
from apps.teams.decorators import team_member_required
from apps.web import views as web_views


def home(request) -> HttpResponse:
    if request.user.is_authenticated:
        return web_views.home(request)  # Pegasus's dashboard
    return render(request, "productivity/landing.html")


@team_member_required
@feature_required("productivity.export")
def export(request, team_slug) -> HttpResponse:
    """The demo of a paid feature: a plain page behind the productivity.export gate."""
    return render(request, "productivity/export.html")
