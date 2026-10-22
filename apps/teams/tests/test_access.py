from django.db import transaction
from django.urls import reverse

from apps.multisite.tests.base import SiteTestCase, site_client
from apps.teams.models import Invitation, Membership, Role, Team

from .helpers import make_team, make_user


class TeamUrlAccessTest(SiteTestCase):
    """Every team URL with each kind of visitor (Read the Docs' URL access matrix idea)."""

    def setUp(self):
        super().setUp()
        self.admin = make_user("admin@example.com")
        self.member = make_user("member@example.com")
        self.outsider = make_user("outsider@example.com")
        self.team = make_team("directory", self.admin)
        self.membership = Membership.objects.create(team=self.team, user=self.member, role=Role.MEMBER)
        self.invitation = Invitation.objects.create(team=self.team, email="new@example.com", invited_by=self.admin)
        self.clients = {"anonymous": site_client("directory")}
        for name in ["outsider", "member", "admin"]:
            self.clients[name] = site_client("directory")
            self.clients[name].force_login(getattr(self, name))

    def test_url_access_matrix(self):
        slug = self.team.slug
        # url, method, data, expected status for anonymous, outsider, member, admin
        matrix = [
            (reverse("teams:create"), "get", {}, (302, 200, 200, 200)),
            (reverse("teams:home", args=[slug]), "get", {}, (302, 404, 200, 200)),
            (reverse("teams:members", args=[slug]), "get", {}, (302, 404, 200, 200)),
            (reverse("teams:invite", args=[slug]), "get", {}, (302, 404, 403, 200)),
            (reverse("teams:invite", args=[slug]), "post", {"email": "x@example.com", "role": 1}, (302, 404, 403, 302)),
            (reverse("teams:change_role", args=[slug, self.membership.pk]), "post", {"role": 8}, (302, 404, 403, 302)),
            (reverse("teams:remove_member", args=[slug, self.membership.pk]), "post", {}, (302, 404, 403, 302)),
            (reverse("teams:revoke", args=[slug, self.invitation.pk]), "post", {}, (302, 404, 403, 302)),
            (reverse("teams:leave", args=[slug]), "post", {}, (302, 404, 302, 302)),
            # the POST-only URLs refuse GET from those allowed to POST
            (reverse("teams:revoke", args=[slug, self.invitation.pk]), "get", {}, (302, 404, 403, 405)),
            (reverse("teams:leave", args=[slug]), "get", {}, (302, 404, 405, 405)),
        ]
        for url, method, data, expected in matrix:
            for who, status in zip(["anonymous", "outsider", "member", "admin"], expected, strict=True):
                with self.subTest(url=url, method=method, who=who):
                    # each request in a rolled-back savepoint, so one visitor's change doesn't affect the next
                    with transaction.atomic():
                        response = getattr(self.clients[who], method)(url, data)
                        transaction.set_rollback(True)
                    self.assertEqual(response.status_code, status)
                    if who == "anonymous":
                        self.assertTrue(response["Location"].startswith(reverse("account_login")))

    def test_team_on_the_directory_is_not_found_on_productivity(self):
        client = site_client("productivity")
        client.force_login(self.member)
        self.assertEqual(client.get(reverse("teams:home", args=[self.team.slug])).status_code, 404)
        self.assertEqual(self.clients["member"].get(reverse("teams:home", args=[self.team.slug])).status_code, 200)

    def test_non_member_gets_404(self):
        response = self.clients["outsider"].get(reverse("teams:home", args=[self.team.slug]))
        self.assertEqual(response.status_code, 404)


class CreateTeamTest(SiteTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user("founder@example.com")
        self.client = site_client("directory")
        self.client.force_login(self.user)

    def test_creator_becomes_admin_of_a_team_on_this_site(self):
        response = self.client.post(reverse("teams:create"), {"name": "Acme Plumbing"})
        team = Team.objects.get(slug="acme-plumbing")
        self.assertRedirects(response, "/a/acme-plumbing/")
        self.assertEqual(team.site_key, "directory")
        self.assertEqual(Membership.objects.get(team=team, user=self.user).role, Role.ADMIN)

    def test_slugs_are_unique_per_site(self):
        self.client.post(reverse("teams:create"), {"name": "Acme"})
        self.client.post(reverse("teams:create"), {"name": "Acme"})
        other = site_client("productivity")
        other.force_login(self.user)
        other.post(reverse("teams:create"), {"name": "Acme"})
        slugs = sorted((team.site_key, team.slug) for team in Team.objects.select_related("site"))
        self.assertEqual(slugs, [("directory", "acme"), ("directory", "acme-2"), ("productivity", "acme")])

    def test_switcher_lists_this_sites_teams_under_its_label(self):
        make_team("directory", self.user, slug="dirteam")
        make_team("productivity", self.user, slug="prodteam")
        page = self.client.get("/").content.decode()
        self.assertIn("Business", page)
        self.assertIn("/a/dirteam/", page)
        self.assertNotIn("/a/prodteam/", page)
        other = site_client("productivity")
        other.force_login(self.user)
        page = other.get("/").content.decode()
        self.assertIn("New team", page)
        self.assertIn("/a/prodteam/", page)
        self.assertNotIn("/a/dirteam/", page)
