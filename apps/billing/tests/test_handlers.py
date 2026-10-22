from copy import deepcopy
from unittest import mock

import stripe
from django.test import override_settings
from djstripe.models import Event, Subscription

from apps.multisite.tests.base import SiteTestCase
from apps.teams.models import Team
from apps.teams.tests.helpers import make_team, make_user

from .helpers import SECRET_KEY, START, make_customer, make_price, make_stripe_account


@override_settings(STRIPE_TEST_SECRET_KEY=SECRET_KEY)
class SubscriptionWebhookTest(SiteTestCase):
    """Events go through dj-stripe's Event.process, as from its webhook view; Stripe's retrieve calls are mocked."""

    def setUp(self):
        super().setUp()
        self.team = make_team("productivity", make_user("admin@example.com"))
        self.customer = make_customer(self.team)
        self.price = make_price()
        make_stripe_account()
        self.stripe = {}  # Stripe's current state, by subscription id
        patcher = mock.patch(
            "stripe.Subscription.retrieve",
            side_effect=lambda id, **kw: stripe.convert_to_stripe_object(deepcopy(self.stripe[id])),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def set_stripe(self, sub_id, status, days=0, metadata=None, customer="cus_1", price=None):
        self.stripe[sub_id] = {
            "id": sub_id,
            "object": "subscription",
            "customer": customer,
            "status": status,
            "created": int(START.timestamp()) + days * 86400,
            "metadata": metadata or {},
            "livemode": False,
            "items": {
                "object": "list",
                "has_more": False,
                "url": f"/v1/subscription_items?subscription={sub_id}",
                "data": [
                    {
                        "id": f"si_{sub_id}",
                        "object": "subscription_item",
                        "price": (price or self.price).id,
                        "quantity": 1,
                        "subscription": sub_id,
                        "created": int(START.timestamp()),
                    }
                ],
            },
        }

    def send(self, event_id, event_type, payload):
        """Deliver an event whose payload is `payload` (a snapshot, perhaps older than Stripe's state)."""
        Event.process(
            {
                "id": event_id,
                "object": "event",
                "type": event_type,
                "api_version": "2026-05-27.dahlia",
                "created": payload["created"],
                "livemode": False,
                "data": {"object": payload},
                "request": {"id": None, "idempotency_key": None},
            },
            api_key=SECRET_KEY,
        )
        self.team.refresh_from_db()

    def test_created_and_deleted_update_the_team(self):
        self.set_stripe("sub_1", "trialing")
        self.send("evt_1", "customer.subscription.created", self.stripe["sub_1"])
        self.assertEqual(self.team.stripe_subscription.id, "sub_1")
        self.assertEqual(self.team.stripe_subscription.status, "trialing")

        self.set_stripe("sub_1", "canceled")
        self.send("evt_2", "customer.subscription.deleted", self.stripe["sub_1"])
        self.assertEqual(self.team.stripe_subscription.status, "canceled")

    def test_duplicate_event_is_handled_once(self):
        self.set_stripe("sub_1", "active")
        created = deepcopy(self.stripe["sub_1"])
        self.send("evt_1", "customer.subscription.created", created)
        self.set_stripe("sub_1", "canceled")
        self.send("evt_2", "customer.subscription.deleted", self.stripe["sub_1"])
        with mock.patch("apps.billing.handlers.Team.get_stripe_subscription") as repick:
            self.send("evt_1", "customer.subscription.created", created)
        repick.assert_not_called()
        self.assertEqual(Event.objects.filter(id="evt_1").count(), 1)
        self.assertEqual(self.team.stripe_subscription.status, "canceled")

    def test_older_event_arriving_late_does_not_win(self):
        # the team cancelled sub_old and then subscribed again with sub_new
        self.set_stripe("sub_old", "active", days=0)
        old_snapshot = deepcopy(self.stripe["sub_old"])
        self.set_stripe("sub_old", "canceled", days=0)
        self.set_stripe("sub_new", "active", days=30)
        self.send("evt_new", "customer.subscription.created", self.stripe["sub_new"])
        self.assertEqual(self.team.stripe_subscription.id, "sub_new")
        # sub_old's "updated" from when it was still active arrives last
        self.send("evt_old", "customer.subscription.updated", old_snapshot)
        self.assertEqual(self.team.stripe_subscription.id, "sub_new")
        self.assertEqual(Subscription.objects.get(id="sub_old").status, "canceled")

    def test_a_directory_teams_event_updates_only_that_team(self):
        business = make_team("directory", make_user("owner@example.com"), slug="biz")
        make_customer(business, "cus_dir")
        listing = make_price(site_key="directory", name="Listing")
        self.set_stripe("sub_1", "active")
        self.send("evt_1", "customer.subscription.created", self.stripe["sub_1"])

        self.set_stripe("sub_dir", "trialing", customer="cus_dir", price=listing)
        self.send("evt_2", "customer.subscription.created", self.stripe["sub_dir"])
        self.set_stripe("sub_dir", "canceled", customer="cus_dir", price=listing)
        self.send("evt_3", "customer.subscription.deleted", self.stripe["sub_dir"])

        business.refresh_from_db()
        self.assertEqual(
            (business.stripe_subscription.id, business.stripe_subscription.status), ("sub_dir", "canceled")
        )
        self.assertEqual((self.team.stripe_subscription.id, self.team.stripe_subscription.status), ("sub_1", "active"))

    def test_team_id_metadata_never_links_an_unlinked_customer(self):
        self.team.stripe_customer = None
        self.team.save()
        self.set_stripe("sub_1", "active", metadata={"site": "productivity", "team_id": str(self.team.pk)})
        with self.assertLogs("apps.billing.handlers", "ERROR"):
            self.send("evt_1", "customer.subscription.created", self.stripe["sub_1"])
        self.team.refresh_from_db()
        self.assertIsNone(self.team.stripe_customer)
        self.assertIsNone(self.team.stripe_subscription)

    def test_customer_without_a_team_is_logged(self):
        Team.objects.update(stripe_customer=None)
        self.set_stripe("sub_1", "active")
        with self.assertLogs("apps.billing.handlers", "ERROR") as logs:
            self.send("evt_1", "customer.subscription.created", self.stripe["sub_1"])
        self.assertIn("no team for customer cus_1", logs.output[0])
        self.assertIsNone(self.team.stripe_subscription)
