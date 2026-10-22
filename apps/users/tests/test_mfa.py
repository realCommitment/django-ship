from unittest import mock

from allauth.account.models import EmailAddress
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal.auth import TOTP, format_hotp_value, generate_totp_secret, hotp_value
from django.conf import settings
from django.urls import reverse

from apps.multisite.tests.base import SiteTestCase, site_client
from apps.users.models import CustomUser

EMAIL = "mfa@example.com"
PASSWORD = "a-long-password-1"
# Codes are computed for a frozen clock, as allauth's own TOTP tests do (tests/apps/mfa/totp/test_unit.py).
NOW = 1731948631


def frozen_clock():
    return mock.patch("time.time", mock.MagicMock(return_value=NOW))


class MfaLoginTest(SiteTestCase):
    def setUp(self):
        super().setUp()
        self.user = CustomUser.objects.create_user(username=EMAIL, email=EMAIL, password=PASSWORD)
        EmailAddress.objects.create(user=self.user, email=EMAIL, verified=True, primary=True)
        self.secret = generate_totp_secret()
        TOTP.activate(self.user, self.secret)

    def _login_with_password(self):
        return self.client.post(reverse("account_login"), {"login": EMAIL, "password": PASSWORD})

    def _enter_code(self, code):
        return self.client.post(reverse("mfa_authenticate"), {"code": code})

    def _logged_in(self):
        return "_auth_user_id" in self.client.session

    def test_password_alone_leads_to_the_2fa_step_on_every_site(self):
        for key in settings.SITES:
            with self.subTest(site=key):
                self.client = site_client(key)
                response = self._login_with_password()
                self.assertRedirects(response, reverse("mfa_authenticate"), fetch_redirect_response=False)
                self.assertFalse(self._logged_in())

    def test_valid_totp_code_completes_the_login(self):
        with frozen_clock():
            self._login_with_password()
            response = self._enter_code(format_hotp_value(hotp_value(self.secret, NOW // 30)))
        self.assertRedirects(response, settings.LOGIN_REDIRECT_URL, fetch_redirect_response=False)
        self.assertTrue(self._logged_in())

    def test_wrong_totp_code_does_not_log_in(self):
        with frozen_clock():
            self._login_with_password()
            # the code of the previous 30-second step is outside allauth's default tolerance of 0
            response = self._enter_code(format_hotp_value(hotp_value(self.secret, NOW // 30 - 1)))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(self._logged_in())

    def test_recovery_code_works_once(self):
        code = RecoveryCodes.activate(self.user).get_unused_codes()[0]
        self._login_with_password()
        response = self._enter_code(code)
        self.assertRedirects(response, settings.LOGIN_REDIRECT_URL, fetch_redirect_response=False)
        self.assertTrue(self._logged_in())

        self.client.post(reverse("account_logout"))
        self._login_with_password()
        response = self._enter_code(code)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(self._logged_in())

    def test_2fa_page_is_linked_from_the_profile_on_every_site(self):
        for key in settings.SITES:
            with self.subTest(site=key):
                client = site_client(key)
                client.force_login(self.user)
                self.assertContains(client.get(reverse("users:user_profile")), f'href="{reverse("mfa_index")}"')
                self.assertContains(client.get(reverse("mfa_index")), "Authenticator App")


class MandatoryEmailVerificationTest(SiteTestCase):
    def setUp(self):
        super().setUp()
        self.user = CustomUser.objects.create_user(username=EMAIL, email=EMAIL, password=PASSWORD)

    def _login(self):
        return self.client.post(reverse("account_login"), {"login": EMAIL, "password": PASSWORD})

    def test_unverified_user_cannot_log_in(self):
        EmailAddress.objects.create(user=self.user, email=EMAIL, verified=False, primary=True)
        response = self._login()
        self.assertRedirects(response, reverse("account_email_verification_sent"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_verified_user_can_log_in(self):
        EmailAddress.objects.create(user=self.user, email=EMAIL, verified=True, primary=True)
        response = self._login()
        self.assertRedirects(response, settings.LOGIN_REDIRECT_URL, fetch_redirect_response=False)
        self.assertIn("_auth_user_id", self.client.session)
