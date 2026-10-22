import logging

from django.contrib.auth.decorators import user_passes_test
from django.db import Error, connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


def home(request) -> HttpResponse:
    if request.user.is_authenticated:
        return render(
            request,
            "web/app_home.html",
            context={
                "active_tab": "dashboard",
                "page_title": _("Dashboard"),
            },
        )
    else:
        return render(request, "web/landing_page.html")


@user_passes_test(lambda u: u.is_superuser)
def simulate_error(request) -> HttpResponse:
    raise RuntimeError("This is a simulated error.")


def health(request) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Error:
        logger.exception("Health check: SELECT 1 on the default database failed")
        return JsonResponse({"status": "error", "failed_check": "database"}, status=503)
    return JsonResponse({"status": "ok"})
