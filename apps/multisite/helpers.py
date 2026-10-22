from django.conf import settings
from django.contrib.sites.models import Site


def site_key_for(site: Site) -> str:
    """The settings.SITES key of a Site row. Raises KeyError if no SITES entry has its domain."""
    return {entry["domain"]: key for key, entry in settings.SITES.items()}[site.domain]
