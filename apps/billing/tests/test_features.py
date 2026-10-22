from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from djstripe.models import SubscriptionItem

from apps.billing.features import get_feature, has_feature
from apps.billing.models import Feature
from apps.multisite.tests.base import SiteTestCase
from apps.teams.tests.helpers import make_team, make_user

from .helpers import make_customer, make_feature, make_price, make_subscription, set_value


class GetFeatureTest(SiteTestCase):
    def setUp(self):
        super().setUp()
        self.team = make_team("productivity", make_user("admin@example.com"))
        self.pro = make_price(name="Pro")
        self.export = make_feature(self.team, "productivity.export")
        self.projects = make_feature(self.team, "productivity.projects", Feature.Kind.QUANTITY, free_value=3)
        set_value(self.export, self.pro, 1)
        set_value(self.projects, self.pro, 10)
        self.customer = make_customer(self.team)

    def subscribe(self, status, items=None):
        self.team.stripe_subscription = make_subscription(self.customer, status, items or [(self.pro, 1)])
        self.team.save()

    def test_free_team_gets_the_free_value(self):
        self.assertEqual(get_feature(self.team, "productivity.export"), 0)
        self.assertEqual(get_feature(self.team, "productivity.projects"), 3)
        self.assertFalse(has_feature(self.team, "productivity.export"))

    def test_entitled_statuses_get_the_product_value(self):
        for status in ["active", "trialing", "past_due"]:
            with self.subTest(status=status):
                self.team.stripe_subscription and self.team.stripe_subscription.delete()
                self.subscribe(status)
                self.assertEqual(get_feature(self.team, "productivity.export"), 1)
                self.assertEqual(get_feature(self.team, "productivity.projects"), 10)
                self.assertTrue(has_feature(self.team, "productivity.export"))

    def test_canceled_gets_the_free_value(self):
        for status in ["canceled", "incomplete", "unpaid"]:
            with self.subTest(status=status):
                self.team.stripe_subscription and self.team.stripe_subscription.delete()
                self.subscribe(status)
                self.assertEqual(get_feature(self.team, "productivity.export"), 0)
                self.assertEqual(get_feature(self.team, "productivity.projects"), 3)

    def test_quantity_sums_across_items(self):
        extra = make_price(name="Extra", amount=200)
        set_value(self.projects, extra, 5)
        self.subscribe("active", [(self.pro, 2), (extra, 3)])
        self.assertEqual(get_feature(self.team, "productivity.projects"), 2 * 10 + 3 * 5)
        # on/off stays 1 however many units have it
        self.assertEqual(get_feature(self.team, "productivity.export"), 1)

    def test_items_removed_in_stripe_no_longer_count(self):
        basic = make_price(name="Basic")
        set_value(self.projects, basic, 4)
        self.subscribe("active", [(basic, 1)])
        # the Pro item Stripe removed when the plan changed: dj-stripe leaves its row
        SubscriptionItem.objects.create(
            id="si_removed", subscription=self.team.stripe_subscription, price=self.pro, stripe_data={"quantity": 1}
        )
        self.assertEqual(get_feature(self.team, "productivity.projects"), 4)
        self.assertEqual(get_feature(self.team, "productivity.export"), 0)

    def test_plan_without_the_feature_gets_the_free_value(self):
        self.subscribe("active", [(make_price(name="Basic"), 1)])
        self.assertEqual(get_feature(self.team, "productivity.projects"), 3)

    def test_wrong_site_prefix_raises(self):
        with self.assertRaisesMessage(ValueError, "'directory.listings' is not a feature of site 'productivity'"):
            get_feature(self.team, "directory.listings")

    def test_unknown_key_raises(self):
        with self.assertRaisesMessage(Feature.DoesNotExist, "No feature 'productivity.nope'"):
            get_feature(self.team, "productivity.nope")

    def test_value_edit_applies_on_the_next_call(self):
        self.subscribe("active")
        self.assertEqual(get_feature(self.team, "productivity.projects"), 10)
        self.projects.product_values.filter(product=self.pro.product).update(value=25)
        self.assertEqual(get_feature(self.team, "productivity.projects"), 25)

    def test_key_must_start_with_the_site_key(self):
        feature = Feature(key="directory.export", site=self.team.site, kind=Feature.Kind.ON_OFF, free_value=0)
        with self.assertRaisesMessage(ValidationError, "The key must start with productivity."):
            feature.full_clean()
        feature.key, feature.free_value = "productivity.other", 2
        with self.assertRaisesMessage(ValidationError, "free value is 0 or 1"):
            feature.full_clean()
        # Django's example.com row is in the Site list but not in SITES
        feature.site, feature.free_value = Site.objects.get_or_create(domain="example.com")[0], 0
        with self.assertRaisesMessage(ValidationError, "This site is not in settings.SITES."):
            feature.full_clean()


class GetStripeSubscriptionTest(SiteTestCase):
    def setUp(self):
        super().setUp()
        self.team = make_team("productivity", make_user("admin@example.com"))
        self.price = make_price()

    def test_no_customer_has_no_subscription(self):
        self.assertIsNone(self.team.get_stripe_subscription())

    def test_follows_the_status_priority_then_the_latest(self):
        customer = make_customer(self.team)
        # added from the lowest priority up; each new one must win over all before it
        order = ["canceled", "incomplete", "trialing", "past_due", "active"]
        for n, status in enumerate(order):
            subscription = make_subscription(customer, status, [(self.price, 1)], stripe_id=f"sub_{status}", days=-n)
            with self.subTest(status=status):
                self.assertEqual(self.team.get_stripe_subscription(), subscription)

    def test_falls_back_to_the_latest(self):
        customer = make_customer(self.team)
        make_subscription(customer, "canceled", [], stripe_id="sub_old", days=1)
        latest = make_subscription(customer, "canceled", [], stripe_id="sub_new", days=2)
        make_subscription(customer, "incomplete_expired", [], stripe_id="sub_older", days=0)
        self.assertEqual(self.team.get_stripe_subscription(), latest)

    def test_latest_of_the_same_status_wins(self):
        customer = make_customer(self.team)
        make_subscription(customer, "active", [], stripe_id="sub_a", days=1)
        newer = make_subscription(customer, "active", [], stripe_id="sub_b", days=2)
        with self.assertLogs("apps.teams.models", "ERROR"):
            self.assertEqual(self.team.get_stripe_subscription(), newer)
