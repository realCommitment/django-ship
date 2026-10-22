import re
from datetime import timedelta
from unittest import mock

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core import mail
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.multisite.tests.base import SiteTestCase, site_client
from apps.teams.adapter import INVITATION_SESSION_KEY
from apps.teams.models import Invitation, Membership, Role
from apps.teams.tasks import send_invitation_email

from .helpers import PASSWORD, make_team, make_user


class InvitationTestBase(SiteTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user("admin@example.com")
        self.team = make_team("directory", self.admin)
        self.invitation = Invitation.objects.create(team=self.team, email="B@Example.com", invited_by=self.admin)
        self.url = self.invitation.get_absolute_url()
        self.client = site_client("directory")

    def login(self, user):
        self.client.force_login(user)

    def is_member(self, email="b@example.com"):
        return Membership.objects.filter(team=self.team, user__email__iexact=email).exists()


class InviteViewTest(InvitationTestBase):
    def setUp(self):
        super().setUp()
        self.login(self.admin)
        self.invite_url = reverse("teams:invite", args=[self.team.slug])

    def invite(self, email, role=Role.MEMBER):
        with mock.patch.object(send_invitation_email, "delay") as delay, self.captureOnCommitCallbacks(execute=True):
            self.client.post(self.invite_url, {"email": email, "role": role})
        return delay

    def test_invite_stores_lowercased_email_and_sends_after_commit(self):
        delay = self.invite("New@Example.com", Role.ADMIN)
        invitation = Invitation.objects.get(email="new@example.com")
        self.assertEqual((invitation.role, invitation.invited_by), (Role.ADMIN, self.admin))
        delay.assert_called_once_with(invitation.pk)

    def test_repeating_an_invite_sends_no_duplicate(self):
        delay = self.invite("b@EXAMPLE.com")
        self.assertEqual(Invitation.objects.filter(team=self.team).count(), 1)
        delay.assert_not_called()

    def test_inviting_again_after_expiry_resends_with_a_new_expiry(self):
        Invitation.objects.filter(pk=self.invitation.pk).update(sent_at=timezone.now() - timedelta(days=15))
        self.assertTrue(Invitation.objects.expired().filter(pk=self.invitation.pk).exists())
        other_admin = make_user("admin2@example.com")
        Membership.objects.create(team=self.team, user=other_admin, role=Role.ADMIN)
        self.login(other_admin)
        delay = self.invite("b@example.com", Role.ADMIN)
        self.invitation.refresh_from_db()
        self.assertFalse(self.invitation.is_expired)
        self.assertEqual((self.invitation.role, self.invitation.invited_by), (Role.ADMIN, other_admin))
        delay.assert_called_once_with(self.invitation.pk)


class InvitationEmailTest(InvitationTestBase):
    def test_email_links_to_the_teams_site_from_its_sender(self):
        other = make_team("productivity", self.admin, slug="prod")
        cases = [("directory", self.invitation), ("productivity", other.invitations.create(email="c@example.com"))]
        for key, invitation in cases:
            with self.subTest(site=key):
                mail.outbox.clear()
                send_invitation_email(invitation.pk)
                message = mail.outbox[0]
                site = settings.SITES[key]
                self.assertEqual(message.from_email, site["from_email"])
                self.assertEqual(message.to, [invitation.email])
                self.assertTrue(message.subject.startswith(f"[{site['name']}] "))
                self.assertIn(f"http://{site['domain']}/invitations/{invitation.token}/", message.body)

    def test_revoked_invitation_sends_nothing(self):
        invitation_id = self.invitation.pk
        self.invitation.delete()
        with self.assertLogs("apps.teams.tasks", "INFO"):
            send_invitation_email(invitation_id)
        self.assertEqual(mail.outbox, [])

    def test_subject_stays_on_one_line(self):
        self.team.name = "Acme\nCorp"
        self.team.save()
        send_invitation_email(self.invitation.pk)
        self.assertIn("Acme Corp", mail.outbox[0].subject)


class InvitationViewTest(InvitationTestBase):
    """The shape of Read the Docs' invitation view tests: expired, another user, anonymous, logged in, revoke."""

    def test_logged_in_get_shows_the_invitation_and_post_accepts(self):
        user = make_user("b@example.com")
        self.login(user)
        response = self.client.get(self.url)
        self.assertContains(response, "Accept invitation")
        self.assertFalse(self.is_member())
        response = self.client.post(self.url)
        self.assertRedirects(response, self.team.get_absolute_url())
        self.assertEqual(Membership.objects.get(team=self.team, user=user).role, Role.MEMBER)
        self.invitation.refresh_from_db()
        self.assertIsNotNone(self.invitation.accepted_at)

    def test_email_match_is_case_insensitive(self):
        user = make_user("b.upper@example.com")
        EmailAddress.objects.create(user=user, email="B@EXAMPLE.COM", verified=True)
        self.login(user)
        self.client.post(self.url)
        self.assertTrue(Membership.objects.filter(team=self.team, user=user).exists())

    def test_expired(self):
        Invitation.objects.filter(pk=self.invitation.pk).update(sent_at=timezone.now() - timedelta(days=15))
        self.login(make_user("b@example.com"))
        self.assertContains(self.client.post(self.url), "expired")
        self.assertFalse(self.is_member())

    def test_expired_for_anonymous_does_not_go_to_signup(self):
        Invitation.objects.filter(pk=self.invitation.pk).update(sent_at=timezone.now() - timedelta(days=15))
        self.assertContains(self.client.get(self.url), "expired")
        self.assertNotIn(INVITATION_SESSION_KEY, self.client.session)

    def test_another_user(self):
        self.login(make_user("c@example.com"))
        self.assertContains(self.client.post(self.url), "This invitation was sent to b@example.com")
        self.assertFalse(Membership.objects.filter(team=self.team, user__email="c@example.com").exists())

    def test_unverified_matching_email_is_rejected(self):
        self.login(make_user("b@example.com", verified=False))
        self.assertContains(self.client.post(self.url), "This invitation was sent to b@example.com")
        self.assertFalse(self.is_member())

    def test_already_a_member(self):
        user = make_user("b@example.com")
        Membership.objects.create(team=self.team, user=user)
        self.login(user)
        self.assertContains(self.client.post(self.url), "already a member")

    def test_wrong_site_is_not_found(self):
        self.client = site_client("productivity")
        self.login(make_user("b@example.com"))
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.assertFalse(self.is_member())

    def test_anonymous_with_an_account_goes_to_login_and_back(self):
        make_user("b@example.com")
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('account_login')}?next={self.url}", fetch_redirect_response=False)

    def test_anonymous_without_an_account_signs_up_verifies_and_lands_in_the_team(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("account_signup"), fetch_redirect_response=False)
        self.client.post(
            reverse("account_signup"), {"email": "b@example.com", "password1": PASSWORD, "terms_agreement": "on"}
        )
        self.assertFalse(self.is_member())  # not before the email is verified
        response = self.confirm_email()
        self.assertRedirects(response, self.team.get_absolute_url(), fetch_redirect_response=False)
        self.assertTrue(self.is_member())

    def test_signup_with_another_email_does_not_redeem(self):
        self.client.get(self.url)
        self.client.post(
            reverse("account_signup"), {"email": "c@example.com", "password1": PASSWORD, "terms_agreement": "on"}
        )
        response = self.confirm_email()
        self.assertRedirects(response, settings.LOGIN_REDIRECT_URL, fetch_redirect_response=False)
        self.assertFalse(self.is_member("c@example.com"))
        self.assertIsNone(Invitation.objects.get(pk=self.invitation.pk).accepted_at)

    def confirm_email(self):
        key = re.search(r"/accounts/confirm-email/([^/]+)/", mail.outbox[-1].body).group(1)
        return self.client.post(reverse("account_confirm_email", args=[key]))

    def test_double_post_creates_one_membership(self):
        self.login(make_user("b@example.com"))
        self.client.post(self.url)
        self.assertEqual(self.client.post(self.url).status_code, 404)  # accepted invitations are not open
        self.assertEqual(Membership.objects.filter(team=self.team).count(), 2)

    def test_a_used_invitation_cannot_be_accepted_again_from_a_stale_copy(self):
        user = make_user("b@example.com")
        stale = Invitation.objects.get(pk=self.invitation.pk)
        self.invitation.accept(user)
        # after leaving, only the re-read under the row lock stops the old invitation from being used again
        Membership.objects.filter(team=self.team, user=user).delete()
        with self.assertRaises(ValidationError) as raised:
            stale.accept(user)
        self.assertEqual(raised.exception.code, "expired")
        self.assertFalse(self.is_member())

    def test_revoke(self):
        member = make_user("member@example.com")
        Membership.objects.create(team=self.team, user=member)
        revoke_url = reverse("teams:revoke", args=[self.team.slug, self.invitation.pk])
        self.login(member)
        self.assertEqual(self.client.post(revoke_url).status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.client.get(revoke_url).status_code, 405)
        self.assertRedirects(self.client.post(revoke_url), reverse("teams:members", args=[self.team.slug]))
        self.assertFalse(Invitation.objects.filter(pk=self.invitation.pk).exists())
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_reinvite_after_leaving(self):
        user = make_user("b@example.com")
        self.invitation.accept(user)
        self.login(user)
        self.client.post(reverse("teams:leave", args=[self.team.slug]))
        self.assertFalse(self.is_member())
        self.login(self.admin)
        with mock.patch.object(send_invitation_email, "delay"), self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("teams:invite", args=[self.team.slug]), {"email": "b@example.com", "role": 1})
        again = Invitation.objects.open().get(team=self.team, email="b@example.com")
        self.login(user)
        self.client.post(again.get_absolute_url())
        self.assertTrue(self.is_member())
