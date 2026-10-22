from django.conf import settings
from django.contrib.sites.models import Site
from django.http import HttpRequest


def get_protocol(is_secure: bool = settings.USE_HTTPS_IN_ABSOLUTE_URLS) -> str:
    """
    Returns the default protocol for the server ("http" or "https").
    """
    return f"http{'s' if is_secure else ''}"


def get_server_root(is_secure: bool = settings.USE_HTTPS_IN_ABSOLUTE_URLS, request: HttpRequest | None = None) -> str:
    """
    Returns the default server root, with protocol. E.g. https://www.example.com
    With a request, its scheme and host. Without one there is no current site (no SITE_ID), so this raises.
    """
    if request is not None:
        return request.build_absolute_uri("/").removesuffix("/")
    return f"{get_protocol(is_secure)}://{Site.objects.get_current().domain}"


def absolute_url(
    relative_url: str, is_secure: bool = settings.USE_HTTPS_IN_ABSOLUTE_URLS, request: HttpRequest | None = None
) -> str:
    """
    Returns the complete absolute url for a given path - for use in emails or API integrations.
    """
    return f"{get_server_root(is_secure, request)}{relative_url}"
