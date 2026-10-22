from io import StringIO
from unittest import mock

import stripe
from django.core.management import CommandError, call_command

from apps.multisite.tests.base import SiteTestCase

from .helpers import make_price


@mock.patch("apps.billing.management.commands.create_portal_configurations.stripe")
class CreatePortalConfigurationsTest(SiteTestCase):
    def fake_portal(self, mock_stripe):
        """Stripe's portal configurations, starting with its default one: create adds to them, list returns them."""
        portal = mock_stripe.billing_portal.Configuration
        configs = [self.configuration("bpc_default", None), self.configuration("bpc_other", {"team": "x"})]
        portal.list.return_value.auto_paging_iter.side_effect = lambda: iter(configs)

        def create(**params):
            configs.append(self.configuration(f"bpc_{params['metadata']['site']}", params["metadata"]))
            return configs[-1]

        portal.create.side_effect = create
        portal.modify.side_effect = lambda id, **params: self.configuration(id, params["metadata"])
        return portal

    @staticmethod
    def configuration(id, metadata):
        return stripe.convert_to_stripe_object(
            {"id": id, "object": "billing_portal.configuration", "metadata": metadata}
        )

    def run_command(self) -> str:
        out = StringIO()
        call_command("create_portal_configurations", stdout=out)
        return out.getvalue()

    def test_run_twice_updates_instead_of_duplicating(self, mock_stripe):
        make_price(site_key="directory", name="Listing")
        make_price(site_key="directory", name="Spotlight", amount=3000)
        make_price(name="Pro")
        portal = self.fake_portal(mock_stripe)

        first = self.run_command()
        second = self.run_command()

        self.assertEqual(portal.create.call_count, 2)
        self.assertEqual([call.args[0] for call in portal.modify.call_args_list], ["bpc_directory", "bpc_productivity"])
        self.assertIn("Created directory: DIRECTORY_STRIPE_PORTAL_CONFIGURATION=bpc_directory", first)
        self.assertIn("Created productivity: PRODUCTIVITY_STRIPE_PORTAL_CONFIGURATION=bpc_productivity", first)
        self.assertIn("Updated directory: DIRECTORY_STRIPE_PORTAL_CONFIGURATION=bpc_directory", second)
        self.assertIn("Updated productivity: PRODUCTIVITY_STRIPE_PORTAL_CONFIGURATION=bpc_productivity", second)
        directory, productivity = (call.kwargs for call in portal.create.call_args_list)
        self.assertEqual(directory["business_profile"], {"headline": "Business Directory"})
        self.assertEqual(directory["default_return_url"], "https://directory.localhost/")
        self.assertEqual(directory["metadata"], {"site": "directory"})
        self.assertEqual(
            directory["features"],
            {
                "subscription_update": {
                    "enabled": True,
                    "default_allowed_updates": ["price"],
                    "products": [
                        {"product": "prod_listing", "prices": ["price_listing"]},
                        {"product": "prod_spotlight", "prices": ["price_spotlight"]},
                    ],
                },
                "payment_method_update": {"enabled": True},
                "invoice_history": {"enabled": True},
                "subscription_cancel": {"enabled": True},
            },
        )
        self.assertEqual(
            productivity["features"]["subscription_update"]["products"],
            [{"product": "prod_pro", "prices": ["price_pro"]}],
        )
        self.assertEqual(portal.modify.call_args_list[0].kwargs, directory)  # the second run sends the same

    def test_a_site_without_plans_gets_a_portal_without_plan_changes(self, mock_stripe):
        make_price(name="Pro")
        portal = self.fake_portal(mock_stripe)
        self.assertIn("Created directory: DIRECTORY_STRIPE_PORTAL_CONFIGURATION=bpc_directory", self.run_command())
        directory = portal.create.call_args_list[0].kwargs
        self.assertEqual(directory["metadata"], {"site": "directory"})
        self.assertEqual(directory["features"]["subscription_update"], {"enabled": False})

    def test_two_configurations_for_one_site_stop_the_command(self, mock_stripe):
        portal = self.fake_portal(mock_stripe)
        portal.create(metadata={"site": "directory"})
        portal.create(metadata={"site": "directory"})
        portal.create.reset_mock()
        with self.assertRaisesMessage(CommandError, "both have metadata.site=directory"):
            self.run_command()
        portal.create.assert_not_called()
        portal.modify.assert_not_called()
