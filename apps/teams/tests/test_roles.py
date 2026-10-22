from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from apps.multisite.tests.base import SiteTestCase, site_client
from apps.teams.models import Membership, Role, validate_role_change

from .helpers import make_team, make_user


class LastAdminTest(SiteTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user("admin@example.com")
        self.team = make_team("directory", self.admin)
        self.admin_membership = Membership.objects.get(team=self.team, user=self.admin)
        self.client = site_client("directory")
        self.client.force_login(self.admin)
        self.slug = self.team.slug

    def assert_still_sole_admin(self, response):
        self.assertContains(response, "Every team needs an admin")
        self.assertEqual(list(self.team.memberships.admins()), [self.admin_membership])

    def test_last_admin_cannot_leave(self):
        self.assert_still_sole_admin(self.client.post(reverse("teams:leave", args=[self.slug]), follow=True))

    def test_last_admin_cannot_be_removed(self):
        url = reverse("teams:remove_member", args=[self.slug, self.admin_membership.pk])
        self.assert_still_sole_admin(self.client.post(url, follow=True))

    def test_last_admin_cannot_be_demoted(self):
        url = reverse("teams:change_role", args=[self.slug, self.admin_membership.pk])
        self.assert_still_sole_admin(self.client.post(url, {"role": Role.MEMBER}, follow=True))

    def test_promote_another_admin_then_leave(self):
        member = Membership.objects.create(team=self.team, user=make_user("b@example.com"))
        self.client.post(reverse("teams:change_role", args=[self.slug, member.pk]), {"role": Role.ADMIN})
        member.refresh_from_db()
        self.assertEqual(member.role, Role.ADMIN)
        response = self.client.post(reverse("teams:leave", args=[self.slug]))
        self.assertRedirects(response, reverse("web:home"))
        self.assertFalse(self.team.memberships.filter(user=self.admin).exists())

    def test_admin_removes_a_member_and_a_member_leaves(self):
        removed = Membership.objects.create(team=self.team, user=make_user("b@example.com"))
        self.client.post(reverse("teams:remove_member", args=[self.slug, removed.pk]))
        self.assertFalse(Membership.objects.filter(pk=removed.pk).exists())
        leaver = make_user("c@example.com")
        Membership.objects.create(team=self.team, user=leaver)
        self.client.force_login(leaver)
        self.client.post(reverse("teams:leave", args=[self.slug]))
        self.assertFalse(self.team.memberships.filter(user=leaver).exists())

    def test_non_admins_cannot_change_roles_or_remove_others(self):
        member = Membership.objects.create(team=self.team, user=make_user("b@example.com"))
        with transaction.atomic():
            for target, new_role in [
                (member, Role.ADMIN),
                (self.admin_membership, Role.MEMBER),
                (self.admin_membership, None),
            ]:
                with self.subTest(target=target, new_role=new_role), self.assertRaises(ValidationError) as raised:
                    validate_role_change(member, target, new_role)
                self.assertEqual(raised.exception.code, "not_admin")
            validate_role_change(member, member, None)  # leaving is allowed

    def test_decisions_use_the_rows_as_they_are_under_the_lock(self):
        member = Membership.objects.create(team=self.team, user=make_user("b@example.com"))
        stale_admin = Membership.objects.get(pk=member.pk)
        stale_admin.role = Role.ADMIN  # promoted in memory, still a member in the database
        with transaction.atomic(), self.assertRaises(ValidationError) as raised:
            validate_role_change(stale_admin, self.admin_membership, None)
        self.assertEqual(raised.exception.code, "not_admin")
        member.delete()
        with transaction.atomic(), self.assertRaises(ValidationError) as raised:
            validate_role_change(self.admin_membership, stale_admin, None)
        self.assertEqual(raised.exception.code, "not_member")
