from typing import Any

import stripe
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from djstripe.settings import djstripe_settings

from apps.billing.utils import site_prices


class Command(BaseCommand):
    help = (
        "Create or update one Stripe Customer Portal configuration per site, offering only that site's plans "
        "(the synced prices of products tagged metadata.site). Safe to run again."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        api_key = djstripe_settings.STRIPE_SECRET_KEY
        # a configuration is found again by its metadata.site, so a second run updates it instead of adding another
        existing: dict[str, str] = {}
        configs = stripe.billing_portal.Configuration.list(api_key=api_key, active=True, limit=100)
        for config in configs.auto_paging_iter():
            if config.metadata and "site" in config.metadata:  # a StripeObject, not a dict: no .get()
                tagged = config.metadata["site"]
                if tagged in existing:
                    raise CommandError(
                        f"Portal configurations {existing[tagged]} and {config.id} both have metadata.site={tagged}: "
                        "deactivate the one that is not in <SITE>_STRIPE_PORTAL_CONFIGURATION, then run this again"
                    )
                existing[tagged] = config.id
        for key, site in settings.SITES.items():
            products: dict[str, list[str]] = {}
            for price in site_prices(key).order_by("product__name", "id"):
                products.setdefault(price.product.id, []).append(price.id)
            # a site without plans still gets one, with plan changes off: production requires an id for every site
            subscription_update: dict[str, Any] = {"enabled": False}
            if products:
                subscription_update = {
                    "enabled": True,
                    "default_allowed_updates": ["price"],
                    "products": [{"product": product, "prices": prices} for product, prices in products.items()],
                }
            params: dict[str, Any] = {
                "business_profile": {"headline": site["name"]},
                "default_return_url": f"https://{site['domain']}/",
                "features": {
                    "subscription_update": subscription_update,
                    "payment_method_update": {"enabled": True},
                    "invoice_history": {"enabled": True},
                    "subscription_cancel": {"enabled": True},
                },
                "metadata": {"site": key},
            }
            if key in existing:
                config = stripe.billing_portal.Configuration.modify(existing[key], api_key=api_key, **params)
            else:
                config = stripe.billing_portal.Configuration.create(api_key=api_key, **params)
            action = "Updated" if key in existing else "Created"
            self.stdout.write(f"{action} {key}: {key.upper()}_STRIPE_PORTAL_CONFIGURATION={config.id}")
