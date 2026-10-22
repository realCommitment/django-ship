from datetime import UTC, datetime, timedelta

from djstripe.enums import APIKeyType
from djstripe.models import Account, APIKey, Customer, Price, Product, Subscription, SubscriptionItem

from apps.billing.models import Feature, ProductFeature
from apps.teams.models import Team

# dj-stripe rows built directly in the database, as a webhook sync would leave them; Stripe is never called.

START = datetime(2026, 1, 1, tzinfo=UTC)
SECRET_KEY = "sk_test_" + "x" * 24  # use with override_settings(STRIPE_TEST_SECRET_KEY=SECRET_KEY)


def make_stripe_account() -> None:
    """The key's account, as after a first sync, so syncing objects doesn't ask Stripe for it."""
    account = Account.objects.create(id="acct_1", livemode=False)
    APIKey.objects.create(secret=SECRET_KEY, type=APIKeyType.secret, livemode=False, djstripe_owner_account=account)


def make_customer(team: Team, stripe_id: str = "cus_1") -> Customer:
    customer = Customer.objects.create(id=stripe_id, livemode=False)
    team.stripe_customer = customer
    team.save()
    return customer


def make_price(site_key: str = "productivity", name: str = "Pro", amount: int = 1000) -> Price:
    product = Product.objects.create(
        id=f"prod_{name.lower()}", name=name, active=True, livemode=False, metadata={"site": site_key}
    )
    return Price.objects.create(
        id=f"price_{name.lower()}",
        product=product,
        active=True,
        currency="usd",
        livemode=False,
        stripe_data={
            "type": "recurring",
            "billing_scheme": "per_unit",
            "unit_amount": amount,
            "recurring": {"interval": "month", "interval_count": 1},
        },
    )


def make_subscription(
    customer: Customer, status: str, items: list[tuple[Price, int]], stripe_id: str = "sub_1", days: int = 0
) -> Subscription:
    """A subscription created `days` after START, with (price, quantity) items."""
    item_ids = [f"si_{stripe_id}_{n}" for n in range(len(items))]
    subscription = Subscription.objects.create(
        id=stripe_id,
        customer=customer,
        livemode=False,
        created=START + timedelta(days=days),
        stripe_data={
            "id": stripe_id,
            "status": status,
            "trial_end": None,
            "items": {"object": "list", "data": [{"id": item_id} for item_id in item_ids]},
        },
    )
    for item_id, (price, quantity) in zip(item_ids, items, strict=True):
        SubscriptionItem.objects.create(
            id=item_id, subscription=subscription, price=price, stripe_data={"quantity": quantity}
        )
    return subscription


def make_feature(team: Team, key: str, kind: str = Feature.Kind.ON_OFF, free_value: int = 0) -> Feature:
    return Feature.objects.create(key=key, site=team.site, kind=kind, free_value=free_value)


def set_value(feature: Feature, price: Price, value: int) -> ProductFeature:
    return ProductFeature.objects.create(feature=feature, product=price.product, value=value)
