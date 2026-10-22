from io import StringIO

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.test import Client, TestCase


def site_client(site_key: str) -> Client:
    """A test client whose requests carry that site's host header."""
    return Client(HTTP_HOST=settings.SITES[site_key]["domain"])


class SiteTestCase(TestCase):
    """The Site rows a deployed database gets from sync_sites, and self.client on the main site's host."""

    @classmethod
    def setUpTestData(cls):
        call_command("sync_sites", stdout=StringIO())
        # Django caches Site objects per process; drop ones whose rows an earlier test class rolled back
        Site.objects.clear_cache()
        cls.addClassCleanup(Site.objects.clear_cache)

    def setUp(self):
        super().setUp()
        self.client = site_client(settings.MAIN_SITE)
