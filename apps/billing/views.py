from typing import cast

import stripe
from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from djstripe.settings import djstripe_settings
from stripe.params.checkout import SessionCreateParamsSubscriptionData

from apps.teams.decorators import team_admin_required

from .features import ENTITLED_STATUSES, current_items
from .utils import get_or_create_stripe_customer, site_prices

# Checkout and portal views adapted from Read the Docs' subscriptions/views.py (MIT)

# a team whose subscription is in one of these can start a new one
ENDED_STATUSES = {"canceled", "incomplete_expired"}


def _billing_url(request: HttpRequest) -> str:
    return request.build_absolute_uri(reverse("billing:billing", args=[request.team.slug]))  # type: ignore[attr-defined]


@team_admin_required
def billing(request, team_slug) -> HttpResponse:
    subscription = request.team.stripe_subscription
    item = current_items(subscription).select_related("price__product").first() if subscription else None
    # the return from Checkout proves nothing: the plan shows once the webhook has arrived
    processing = request.GET.get("checkout") == "success" and not (
        subscription and subscription.status in ENTITLED_STATUSES
    )
    can_subscribe = not processing and (subscription is None or subscription.status in ENDED_STATUSES)
    context = {
        "subscription": subscription,
        "plan": item.price.product if item else None,
        "prices": site_prices(request.site_key).order_by("product__name") if can_subscribe else [],
        "processing": processing,
        "active_tab": "team_billing",
    }
    return render(request, "billing/billing.html", context)


@team_admin_required
@require_POST
def checkout(request, team_slug) -> HttpResponse:
    team = request.team
    price = get_object_or_404(site_prices(request.site_key), id=request.POST.get("price"))
    customer = get_or_create_stripe_customer(team, request.user.email)
    # asked of Stripe, which has a paid Checkout's subscription at once; its webhook may still be on the way here
    earlier = stripe.Subscription.list(
        api_key=djstripe_settings.STRIPE_SECRET_KEY, customer=customer.id, status="all", limit=100
    ).data
    if any(subscription.status not in ENDED_STATUSES for subscription in earlier):
        messages.info(request, _("%(team)s already has a plan. Change it in Manage billing.") % {"team": team})
        return redirect("billing:billing", team_slug)
    metadata = {"site": request.site_key, "team_id": str(team.pk)}
    subscription_data: SessionCreateParamsSubscriptionData = {"metadata": metadata}
    # Stripe runs the trial (card required), once per team; the price's metadata wins over the product's, "0" is none
    meta = price.metadata or {}
    trial_days = int(meta.get("trial_period_days") or price.product.metadata.get("trial_period_days") or 0)
    if trial_days and not earlier:
        subscription_data["trial_period_days"] = trial_days
    session = stripe.checkout.Session.create(
        api_key=djstripe_settings.STRIPE_SECRET_KEY,
        customer=customer.id,
        mode="subscription",
        line_items=[{"price": price.id, "quantity": 1}],
        client_reference_id=f"{request.site_key}:{team.pk}",
        metadata=metadata,
        subscription_data=subscription_data,
        success_url=_billing_url(request) + "?checkout=success",
        cancel_url=_billing_url(request),
    )
    if not session.url:
        raise ValueError(f"Stripe returned Checkout session {session.id} without a URL")
    return redirect(session.url)


@team_admin_required
@require_POST
def portal(request, team_slug) -> HttpResponse:
    if request.team.stripe_customer is None:
        raise Http404("This team has no Stripe customer yet.")
    session = stripe.billing_portal.Session.create(
        api_key=djstripe_settings.STRIPE_SECRET_KEY,
        customer=request.team.stripe_customer.id,
        return_url=_billing_url(request),
        # empty becomes None, which stripe leaves out, and Stripe's default portal applies
        configuration=cast(str, settings.SITES[request.site_key]["stripe_portal_configuration"] or None),
    )
    return redirect(session.url)
