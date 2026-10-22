from typing import Any

from django.conf import settings
from django.http import HttpRequest

from apps.web.context_processors import project_meta as pegasus_project_meta


def project_meta(request: HttpRequest) -> dict[str, Any]:
    """Pegasus's project_meta, with the name, metadata and analytics ID of the request's site."""
    context = pegasus_project_meta(request)
    site = settings.SITES[request.site_key]  # type: ignore[attr-defined]
    meta = context["project_meta"]  # a copy of PROJECT_METADATA, safe to change
    meta.update(
        NAME=site["name"],
        DESCRIPTION=site["description"],
        KEYWORDS=site["keywords"],
        IMAGE=site["image"],
        URL=context["server_url"],
    )
    meta["TITLE"] = "{} | {}".format(meta["NAME"], meta["DESCRIPTION"])
    context["GOOGLE_ANALYTICS_ID"] = site["google_analytics_id"]
    return context
