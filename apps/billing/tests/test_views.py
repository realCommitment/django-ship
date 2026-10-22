from copy import deepcopy
from unittest import mock

import stripe
from django.conf import settings
from django.db import transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.multisite.tests.base import SiteTestCase, site_client
from apps.teams.models import Membership, Role
from apps.teams.tests.helpers import make_team, make_user

from .helpers import (
    SECRET_KEY,
    make_customer,
    make_feature,
    make_price,
    make_stripe_account,
    make_subscription,
    set_value,
)

# Stripe is mocked in the module that calls it, as in School Desk's stripe_gateway tests (MIT, Matt Layman)


def sites_with_portals(**ids: str) -> dict:
    """settings.SITES with these portal configuration ids, e.g. directory="bpc_1"."""
    sites = deepcopy(settings.SITES)
    for key, configuration in ids.items():
        sites[key]["stripe_portal_configuration"] = configuration
    return sites


class BillingViewsTest(SiteTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user("admin@example.com")
        self.member = make_user("member@example.com")
        self.team = make_team("productivity", self.admin)
        Membership.objects.create(team=self.team, user=self.member, role=Role.MEMBER)
        self.pro = make_price(name="Pro")
        self.client = site_client("productivity")
        self.client.force_login(self.admin)
        self.billing_url = reverse("billing:billing", args=[self.team.slug])
        self.checkout_url = reverse("billing:checkout", args=[self.team.slug])
        self.portal_url = reverse("billing:portal", args=[self.team.slug])

    def directory_business(self):
        """A business on the directory with the same admin, a client for it there, and a directory plan."""
        business = make_team("directory", self.admin, slug="biz")
        client = site_client("directory")
        client.force_login(self.admin)
        return business, client, make_price(site_key="directory", name="Listing")

    def test_only_a_team_admin_gets_the_billing_urls(self):
        clients = {"anonymous": site_client("productivity")}
        for name, user in [("outsider", make_user("outsider@example.com")), ("member", self.member)]:
            clients[name] = site_client("productivity")
            clients[name].force_login(user)
        other_site = site_client("directory")
        other_site.force_login(self.admin)
        clients["admin, other site"] = other_site
        for url, method in [(self.billing_url, "get"), (self.checkout_url, "post"), (self.portal_url, "post")]:
            for who, status in [("anonymous", 302), ("outsider", 404), ("member", 403), ("admin, other site", 404)]:
                with self.subTest(url=url, who=who), mock.patch("apps.billing.views.stripe") as mock_stripe:
                    with transaction.atomic():
                        response = getattr(clients[who], method)(url, {"price": self.pro.id})
                        transaction.set_rollback(True)
                    self.assertEqual(response.status_code, status)
                    mock_stripe.checkout.Session.create.assert_not_called()
                    mock_stripe.billing_portal.Session.create.assert_not_called()

    def test_billing_page_lists_this_sites_plans(self):
        make_price(site_key="directory", name="Listing")
        response = self.client.get(self.billing_url)
        self.assertContains(response, "Free plan")
        self.assertContains(response, "Pro")
        self.assertContains(response, "$10.00 USD/month")
        self.assertNotContains(response, "Listing")
        self.assertNotContains(response, "Manage billing")

    def test_a_directory_business_sees_only_directory_plans(self):
        business, client, listing = self.directory_business()
        response = client.get(reverse("billing:billing", args=[business.slug]))
        self.assertContains(response, f'value="{listing.id}"')
        self.assertNotContains(response, self.pro.id)

    def test_billing_page_shows_the_plan_and_trial_end(self):
        subscription = make_subscription(make_customer(self.team), "trialing", [(self.pro, 1)])
        subscription.stripe_data["trial_end"] = 1767225600 + 14 * 86400  # 2026-01-15
        subscription.save()
        self.team.stripe_subscription = subscription
        self.team.save()
        response = self.client.get(self.billing_url)
        self.assertContains(response, "<dd>Pro</dd>", html=True)
        self.assertContains(response, "<dd>trialing</dd>", html=True)
        self.assertContains(response, "Jan. 15, 2026")
        self.assertContains(response, "Manage billing")
        self.assertNotContains(response, "Choose")

    def test_return_from_checkout_shows_processing_until_the_webhook(self):
        response = self.client.get(self.billing_url + "?checkout=success")
        self.assertContains(response, "Stripe is processing your payment")
        self.assertNotContains(response, "Choose")  # no second Checkout while the first one is on its way
        self.team.stripe_subscription = make_subscription(make_customer(self.team), "active", [(self.pro, 1)])
        self.team.save()
        response = self.client.get(self.billing_url + "?checkout=success")
        self.assertNotContains(response, "Stripe is processing your payment")

    def post_checkout(self, mock_stripe, stripe_statuses=(), price=None):
        """Choose a plan while Stripe reports the customer's subscriptions with these statuses."""
        mock_stripe.Subscription.list.return_value.data = [mock.Mock(status=status) for status in stripe_statuses]
        mock_stripe.checkout.Session.create.return_value = mock.Mock(url="https://checkout.stripe.com/c/pay/cs_1")
        return self.client.post(self.checkout_url, {"price": (price or self.pro).id}, follow=True)

    @mock.patch("apps.billing.views.stripe")
    def test_checkout_uses_the_request_host_and_tags_the_team(self, mock_stripe):
        customer = make_customer(self.team)
        self.pro.product.metadata["trial_period_days"] = "14"
        self.pro.product.save()
        mock_stripe.Subscription.list.return_value.data = []
        mock_stripe.checkout.Session.create.return_value = mock.Mock(url="https://checkout.stripe.com/c/pay/cs_1")

        response = self.client.post(self.checkout_url, {"price": self.pro.id})

        self.assertRedirects(response, "https://checkout.stripe.com/c/pay/cs_1", fetch_redirect_response=False)
        self.assertEqual(mock_stripe.Subscription.list.call_args.kwargs["customer"], customer.id)
        kwargs = mock_stripe.checkout.Session.create.call_args.kwargs
        host = "http://productivity.localhost"
        metadata = {"site": "productivity", "team_id": str(self.team.pk)}
        self.assertEqual(kwargs["customer"], customer.id)
        self.assertEqual(kwargs["mode"], "subscription")
        self.assertEqual(kwargs["line_items"], [{"price": self.pro.id, "quantity": 1}])
        self.assertEqual(kwargs["client_reference_id"], f"productivity:{self.team.pk}")
        self.assertEqual(kwargs["metadata"], metadata)
        self.assertEqual(kwargs["subscription_data"], {"metadata": metadata, "trial_period_days": 14})
        self.assertEqual(kwargs["success_url"], f"{host}{self.billing_url}?checkout=success")
        self.assertEqual(kwargs["cancel_url"], f"{host}{self.billing_url}")

    @mock.patch("apps.billing.views.stripe")
    def test_checkout_refuses_another_sites_price_and_a_second_plan(self, mock_stripe):
        make_customer(self.team)
        listing = make_price(site_key="directory", name="Listing")
        self.assertEqual(self.post_checkout(mock_stripe, price=listing).status_code, 404)
        # paid a moment ago: Stripe has the subscription, its webhook hasn't arrived
        self.assertContains(self.post_checkout(mock_stripe, ["trialing"]), "already has a plan")
        self.assertContains(self.post_checkout(mock_stripe, ["canceled", "past_due"]), "already has a plan")
        mock_stripe.checkout.Session.create.assert_not_called()

    @mock.patch("apps.billing.views.stripe")
    def test_directory_checkout_refuses_a_productivity_price_and_returns_to_the_directory(self, mock_stripe):
        business, client, listing = self.directory_business()
        make_customer(business, "cus_dir")
        url = reverse("billing:checkout", args=[business.slug])
        mock_stripe.Subscription.list.return_value.data = []
        mock_stripe.checkout.Session.create.return_value = mock.Mock(url="https://checkout.stripe.com/c/pay/cs_1")
        self.assertEqual(client.post(url, {"price": self.pro.id}).status_code, 404)
        mock_stripe.checkout.Session.create.assert_not_called()

        client.post(url, {"price": listing.id})
        kwargs = mock_stripe.checkout.Session.create.call_args.kwargs
        billing_url = "http://directory.localhost" + reverse("billing:billing", args=[business.slug])
        self.assertEqual(kwargs["customer"], "cus_dir")
        self.assertEqual(kwargs["line_items"], [{"price": listing.id, "quantity": 1}])
        self.assertEqual(kwargs["metadata"], {"site": "directory", "team_id": str(business.pk)})
        self.assertEqual(kwargs["success_url"], billing_url + "?checkout=success")
        self.assertEqual(kwargs["cancel_url"], billing_url)

    @mock.patch("apps.billing.views.stripe")
    def test_trial_once_per_team_and_a_price_can_turn_it_off(self, mock_stripe):
        make_customer(self.team)
        self.pro.product.metadata["trial_period_days"] = "14"
        self.pro.product.save()
        self.post_checkout(mock_stripe, ["canceled"])
        self.assertNotIn("trial_period_days", mock_stripe.checkout.Session.create.call_args.kwargs["subscription_data"])
        self.pro.metadata = {"trial_period_days": "0"}
        self.pro.save()
        self.post_checkout(mock_stripe)
        self.assertNotIn("trial_period_days", mock_stripe.checkout.Session.create.call_args.kwargs["subscription_data"])

    @override_settings(STRIPE_TEST_SECRET_KEY=SECRET_KEY)
    @mock.patch("apps.billing.views.stripe")
    def test_checkout_creates_the_teams_customer_once(self, mock_stripe):
        make_stripe_account()
        created = stripe.convert_to_stripe_object(
            {"id": "cus_new", "object": "customer", "email": "admin@example.com", "livemode": False, "created": 1}
        )
        with mock.patch("stripe.Customer.create", return_value=created) as create:
            self.post_checkout(mock_stripe)
            self.post_checkout(mock_stripe)
        create.assert_called_once_with(
            api_key=SECRET_KEY,
            email="admin@example.com",
            name=self.team.name,
            metadata={"site": "productivity", "team_id": str(self.team.pk)},
        )
        self.team.refresh_from_db()
        self.assertEqual(self.team.stripe_customer.id, "cus_new")
        self.assertEqual(mock_stripe.checkout.Session.create.call_args.kwargs["customer"], "cus_new")

    @override_settings(STRIPE_TEST_SECRET_KEY=SECRET_KEY)
    @mock.patch("apps.billing.views.stripe")
    def test_a_customer_deleted_in_stripe_is_replaced(self, mock_stripe):
        make_stripe_account()
        make_customer(self.team, "cus_deleted")
        self.team.stripe_customer.date_purged = timezone.now()  # what dj-stripe does on customer.deleted
        self.team.stripe_customer.save()
        created = stripe.convert_to_stripe_object(
            {"id": "cus_new", "object": "customer", "livemode": False, "created": 1}
        )
        with mock.patch("stripe.Customer.create", return_value=created):
            self.post_checkout(mock_stripe)
        self.team.refresh_from_db()
        self.assertEqual(self.team.stripe_customer.id, "cus_new")

    @override_settings(SITES=sites_with_portals(productivity=""))
    @mock.patch("apps.billing.views.stripe")
    def test_portal_returns_to_the_request_host(self, mock_stripe):
        customer = make_customer(self.team)
        mock_stripe.billing_portal.Session.create.return_value = mock.Mock(url="https://billing.stripe.com/p/s_1")

        response = self.client.post(self.portal_url)

        self.assertRedirects(response, "https://billing.stripe.com/p/s_1", fetch_redirect_response=False)
        mock_stripe.billing_portal.Session.create.assert_called_once_with(
            api_key=mock.ANY,
            customer=customer.id,
            return_url=f"http://productivity.localhost{self.billing_url}",
            configuration=None,
        )

    @override_settings(SITES=sites_with_portals(directory="bpc_directory", productivity="bpc_productivity"))
    @mock.patch("apps.billing.views.stripe")
    def test_portal_session_gets_the_sites_configuration(self, mock_stripe):
        make_customer(self.team)
        business, client, _ = self.directory_business()
        make_customer(business, "cus_dir")
        mock_stripe.billing_portal.Session.create.return_value = mock.Mock(url="https://billing.stripe.com/p/s_1")

        client.post(reverse("billing:portal", args=[business.slug]))
        self.client.post(self.portal_url)

        calls = [call.kwargs for call in mock_stripe.billing_portal.Session.create.call_args_list]
        self.assertEqual(
            [(call["customer"], call["configuration"], call["return_url"].split("/a/")[0]) for call in calls],
            [
                ("cus_dir", "bpc_directory", "http://directory.localhost"),
                ("cus_1", "bpc_productivity", "http://productivity.localhost"),
            ],
        )

    def test_portal_without_a_customer_is_not_found(self):
        self.assertEqual(self.client.post(self.portal_url).status_code, 404)


class FeatureGateTest(SiteTestCase):
    def setUp(self):
        super().setUp()
        self.admin = make_user("admin@example.com")
        self.member = make_user("member@example.com")
        self.team = make_team("productivity", self.admin)
        Membership.objects.create(team=self.team, user=self.member, role=Role.MEMBER)
        self.pro = make_price()
        set_value(make_feature(self.team, "productivity.export"), self.pro, 1)
        self.url = reverse("export", urlconf="apps.productivity.urls", args=[self.team.slug])

    def client_for(self, user):
        client = site_client("productivity")
        client.force_login(user)
        return client

    def test_free_team_is_sent_to_billing(self):
        response = self.client_for(self.admin).get(self.url, follow=True)
        self.assertRedirects(response, reverse("billing:billing", args=[self.team.slug]))
        self.assertContains(response, "Your plan doesn&#x27;t include this")
        # members can't open Billing, so they go to the team's home page
        response = self.client_for(self.member).get(self.url, follow=True)
        self.assertRedirects(response, reverse("teams:home", args=[self.team.slug]))
        self.assertContains(response, "Ask an admin to upgrade")

    def test_paid_team_gets_in(self):
        self.team.stripe_subscription = make_subscription(make_customer(self.team), "active", [(self.pro, 1)])
        self.team.save()
        for user in [self.admin, self.member]:
            response = self.client_for(user).get(self.url)
            self.assertContains(response, "Your plan includes export.")


class DirectoryFeatureGateTest(SiteTestCase):
    def test_featured_listing_needs_a_directory_plan(self):
        admin = make_user("admin@example.com")
        business = make_team("directory", admin)
        listing = make_price(site_key="directory", name="Listing")
        set_value(make_feature(business, "directory.featured_listing"), listing, 1)
        url = reverse("featured", urlconf="apps.directory.urls", args=[business.slug])
        client = site_client("directory")
        client.force_login(admin)
        self.assertRedirects(client.get(url), reverse("billing:billing", args=[business.slug]))
        business.stripe_subscription = make_subscription(make_customer(business), "active", [(listing, 1)])
        business.save()
        self.assertContains(client.get(url), "Your plan includes a featured listing.")
