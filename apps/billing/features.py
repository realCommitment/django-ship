from collections.abc import Callable
from functools import wraps

from django.contrib import messages
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from djstripe.models import Subscription, SubscriptionItem

from apps.teams.models import Team

from .models import Feature

# Subscription statuses that get the plan's features; any other status gets the free values.
ENTITLED_STATUSES = {"active", "trialing", "past_due"}


def get_feature(team: Team, key: str) -> int:
    """
    The team's value for a feature: its plan's value times the quantity, summed over the subscription's items,
    or the free value. Raises for an unknown key or another site's key.
    Lookup logic from Read the Docs' get_feature (MIT): readthedocs/subscriptions/products.py
    """
    if not key.startswith(f"{team.site_key}."):
        raise ValueError(f"Feature {key!r} is not a feature of site {team.site_key!r} (team {team.pk})")
    # shortcut: up to four queries per call, no cache; add PostHog's JSON cache of the team's values when profiling
    # shows feature lookups on hot pages
    try:
        feature = Feature.objects.get(key=key)
    except Feature.DoesNotExist:
        raise Feature.DoesNotExist(f"No feature {key!r}: add it in the admin") from None
    subscription = team.stripe_subscription
    if subscription is None or subscription.status not in ENTITLED_STATUSES:
        return feature.free_value
    values = dict(feature.product_values.values_list("product_id", "value"))
    items = current_items(subscription).filter(price__product__pk__in=values).select_related("price__product")
    if not items:
        return feature.free_value
    total = sum(values[item.price.product.pk] * item.quantity for item in items)
    if feature.kind == Feature.Kind.ON_OFF:
        return int(total > 0)
    return total


def current_items(subscription: Subscription) -> QuerySet[SubscriptionItem]:
    """The subscription's items as Stripe last reported them; dj-stripe keeps items removed upstream in its table."""
    # shortcut: reads the page of items Stripe embeds in the subscription and ignores has_more; flat plans have one
    # item. List the items from Stripe if a subscription ever carries more than that page.
    ids = [item["id"] for item in subscription.stripe_data.get("items", {}).get("data", [])]
    return SubscriptionItem.objects.filter(subscription=subscription, id__in=ids)


def has_feature(team: Team, key: str) -> bool:
    return get_feature(team, key) > 0


def feature_required(key: str) -> Callable[[Callable[..., HttpResponse]], Callable[..., HttpResponse]]:
    """For team views, under team_member_required: without the feature, admins go to Billing, members to the team."""

    def decorator(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(view)
        def wrapper(request: HttpRequest, team_slug: str, *args, **kwargs) -> HttpResponse:
            if has_feature(request.team, key):  # type: ignore[attr-defined]
                return view(request, team_slug, *args, **kwargs)
            if request.membership.is_admin:  # type: ignore[attr-defined]
                messages.info(request, _("Your plan doesn't include this. Choose a plan to use it."))
                return redirect("billing:billing", team_slug)
            messages.info(request, _("Your team's plan doesn't include this. Ask an admin to upgrade."))
            return redirect("teams:home", team_slug)

        return wrapper

    return decorator
