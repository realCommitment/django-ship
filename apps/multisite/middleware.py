import logging
from collections.abc import Callable

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.http.request import split_domain_port

from .helpers import site_key_for

logger = logging.getLogger(__name__)


class MultisiteMiddleware:
    """
    Serves each site in settings.SITES from its own urlconf, picked by the request's domain.
    Sets request.site, request.site_key and request.urlconf; unknown domains redirect to settings.MAIN_SITE.
    Shape from envergo's SetUrlConfBasedOnSite (MIT, Copyright (c) 2021, MTES):
    https://github.com/MTES-MCT/envergo/blob/main/envergo/contrib/middleware.py
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Hosts are case-insensitive, and Django caches one Site per distinct Host string, so normalise
        # before anything looks the site up; otherwise case variants of a real domain grow that cache.
        if "HTTP_HOST" in request.META:
            request.META["HTTP_HOST"] = request.META["HTTP_HOST"].lower()
        # The health check answers on any host, from ROOT_URLCONF.
        if request.path_info == "/health/":
            return self.get_response(request)
        try:
            # matches the host with its port, then without it
            site = Site.objects.get_current(request)
            site_key = site_key_for(site)
        except Site.DoesNotExist, KeyError:  # KeyError: a Site row that is not in settings.SITES
            return self.redirect_to_main_site(request)
        request.site = site
        request.site_key = site_key  # type: ignore[attr-defined]
        request.urlconf = settings.SITES[site_key]["urlconf"]
        return self.get_response(request)

    def redirect_to_main_site(self, request: HttpRequest) -> HttpResponse:
        domain, port = split_domain_port(request.get_host())  # domain comes back lowercased
        if domain in {site["domain"].lower() for site in settings.SITES.values()}:
            # a configured site without its row; for the main site, redirecting would also loop
            raise ImproperlyConfigured(f"No Site row for the configured domain {domain}. Run manage.py sync_sites.")
        main_domain = settings.SITES[settings.MAIN_SITE]["domain"]
        url = f"{request.scheme}://{main_domain}{f':{port}' if port else ''}{request.get_full_path()}"
        logger.warning("Unknown site host %s for path %s, redirecting to %s", request.get_host(), request.path, url)
        return HttpResponseRedirect(url)
