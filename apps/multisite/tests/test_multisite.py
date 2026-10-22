from io import StringIO

from django.conf import settings
from django.contrib.sites import models as sites_models
from django.contrib.sites.models import Site
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import Client, TestCase

from apps.multisite.models import SignupSite
from apps.users.models import CustomUser

from .base import SiteTestCase, site_client

SITE_KEYS = ["directory", "productivity"]


class TestSiteRouting(SiteTestCase):
    def test_each_host_gets_its_own_landing_page(self):
        for key in SITE_KEYS:
            with self.subTest(site=key):
                response = site_client(key).get("/")
                self.assertTemplateUsed(response, f"{key}/landing.html")
                site = settings.SITES[key]
                self.assertContains(response, f"<title>{site['name']} | {site['description']}</title>", html=True)
                self.assertContains(response, f'<meta property="og:site_name" content="{site["name"]}" />', html=True)
                self.assertNotContains(response, "og:image")

    def test_host_case_is_normalised_before_the_site_lookup(self):
        response = Client(HTTP_HOST=settings.SITES["directory"]["domain"].upper()).get("/")
        self.assertTemplateUsed(response, "directory/landing.html")
        # read through the module: Site.objects.clear_cache() rebinds SITE_CACHE to a new dict
        cached_hosts = [host for host in sites_models.SITE_CACHE if isinstance(host, str)]
        self.assertEqual([host for host in cached_hosts if host != host.lower()], [])

    def test_logged_in_home_is_the_dashboard(self):
        client = site_client("directory")
        client.force_login(CustomUser.objects.create_user(username="someone@example.com"))
        self.assertTemplateUsed(client.get("/"), "web/app_home.html")

    def test_unknown_host_redirects_to_main_site_keeping_path(self):
        with self.assertLogs("apps.multisite.middleware", level="WARNING"):
            response = Client(HTTP_HOST="unknown.localhost:8123").get("/some/path?page=2")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "http://productivity.localhost:8123/some/path?page=2")

    def test_site_row_missing_from_settings_redirects(self):
        Site.objects.create(domain="old.example.com", name="Old")
        with self.assertLogs("apps.multisite.middleware", level="WARNING"):
            response = Client(HTTP_HOST="old.example.com").get("/")
        self.assertRedirects(response, "http://productivity.localhost/", fetch_redirect_response=False)

    def test_configured_site_without_site_row_fails_loudly(self):
        for key in SITE_KEYS:
            with self.subTest(site=key):
                Site.objects.filter(domain=settings.SITES[key]["domain"]).delete()
                with (
                    self.assertRaisesMessage(ImproperlyConfigured, "sync_sites"),
                    self.assertLogs("django.request", "ERROR"),
                ):
                    site_client(key).get("/")

    def test_robots_and_sitemap_name_the_requesting_host(self):
        for key in SITE_KEYS:
            domain = settings.SITES[key]["domain"]
            with self.subTest(site=key):
                robots = site_client(key).get("/robots.txt")
                self.assertEqual(robots["Content-Type"], "text/plain")
                self.assertIn(f"Sitemap: http://{domain}/sitemap.xml", robots.content.decode())
                sitemap = site_client(key).get("/sitemap.xml")
                self.assertContains(sitemap, f"<loc>http://{domain}/</loc>")

    def test_health_answers_on_unknown_host(self):
        response = Client(HTTP_HOST="unknown.localhost").get("/health/")
        self.assertEqual(response.status_code, 200)


class TestSiteEmailAndSignup(SiteTestCase):
    def test_password_reset_email_is_branded_per_site(self):
        for key in SITE_KEYS:
            with self.subTest(site=key):
                mail.outbox.clear()
                email = f"reset-{key}@example.com"
                CustomUser.objects.create_user(username=email, email=email, password="a-long-password-1")
                site_client(key).post("/accounts/password/reset/", {"email": email})
                self.assertEqual(len(mail.outbox), 1)
                self.assertEqual(mail.outbox[0].from_email, settings.SITES[key]["from_email"])
                self.assertTrue(mail.outbox[0].subject.startswith(f"[{settings.SITES[key]['name']}] "))

    def test_signup_records_the_signup_site(self):
        response = site_client("directory").post(
            "/accounts/signup/",
            {"email": "new@example.com", "password1": "a-long-password-1", "terms_agreement": "on"},
        )
        self.assertEqual(response.status_code, 302)
        signup_site = SignupSite.objects.get(user__email="new@example.com")
        self.assertEqual(signup_site.site.domain, settings.SITES["directory"]["domain"])


class TestSyncSites(TestCase):
    def test_running_twice_leaves_one_row_per_site(self):
        call_command("sync_sites", stdout=StringIO())
        call_command("sync_sites", stdout=StringIO())
        for site in settings.SITES.values():
            self.assertEqual(Site.objects.filter(domain=site["domain"]).count(), 1)
            self.assertEqual(Site.objects.get(domain=site["domain"]).name, site["name"])

    def test_matches_an_existing_row_whatever_its_case(self):
        domain = settings.SITES["directory"]["domain"]
        Site.objects.create(domain=domain.upper(), name="Old name")
        call_command("sync_sites", stdout=StringIO())
        self.assertEqual(Site.objects.filter(domain__iexact=domain).get().domain, domain)
