import stripe
from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from djstripe.models import Customer, Price
from djstripe.settings import djstripe_settings

from apps.teams.models import Team


def site_prices(site_key: str) -> QuerySet[Price]:
    """The site's active recurring prices, from dj-stripe's synced tables: products tagged metadata.site."""
    return Price.objects.filter(
        active=True,
        livemode=settings.STRIPE_LIVE_MODE,
        stripe_data__type="recurring",
        product__active=True,
        product__metadata__site=site_key,
    ).select_related("product")


def get_or_create_stripe_customer(team: Team, email: str) -> Customer:
    """
    The team's Stripe customer, created with `email` (the paying admin's) if it has none yet.
    Adapted from Read the Docs' subscriptions/utils.py (MIT).
    """
    with transaction.atomic():
        # two admins starting Checkout at once must not create two customers
        team = Team.objects.select_for_update().get(pk=team.pk)
        # a customer deleted in Stripe stays here, purged (dj-stripe keeps the row); the team gets a new one
        if team.stripe_customer is None or team.stripe_customer.date_purged:
            api_key = djstripe_settings.STRIPE_SECRET_KEY
            data = stripe.Customer.create(
                api_key=api_key,
                email=email,
                name=team.name,
                metadata={"site": team.site_key, "team_id": str(team.pk)},
            )
            # dj-stripe needs the key passed in (as Read the Docs notes, dj-stripe issues 2037 and 2055)
            team.stripe_customer = Customer.sync_from_stripe_data(data, api_key=api_key)
            team.save(update_fields=["stripe_customer", "updated_at"])
    return team.stripe_customer
