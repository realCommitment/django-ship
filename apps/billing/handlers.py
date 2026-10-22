import logging

from djstripe.event_handlers import djstripe_receiver
from djstripe.models import Customer

from apps.teams.models import Team

logger = logging.getLogger(__name__)

# Shape from Read the Docs' subscriptions/event_handlers.py (MIT). dj-stripe has already stored the event (a duplicate
# is never handled twice) and synced the object; the team's subscription is then re-picked from what is stored, so an
# older event arriving late cannot win.


@djstripe_receiver(
    [
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "checkout.session.completed",
    ]
)
def update_team_subscription(sender, event, **kwargs) -> None:
    obj = event.data["object"]
    if not obj.get("customer"):
        return  # a Checkout without a customer (a payment link, say) is none of ours: teams always have one
    customer = Customer.objects.filter(id=obj["customer"]).first()
    # the team row lock orders concurrent webhooks for one team, so a slower one can't save an older pick
    teams = Team.objects.select_for_update()
    # Teams are found only through their linked customer, never through event metadata: with one Stripe test account
    # shared by several checkouts, metadata from another environment could otherwise attach a foreign subscription.
    team = teams.filter(stripe_customer=customer).first() if customer else None
    if team is None:
        logger.error("Stripe event %s (%s): no team for customer %s", event.id, event.type, obj["customer"])
        return
    team.stripe_subscription = team.get_stripe_subscription()
    team.save(update_fields=["stripe_customer", "stripe_subscription", "updated_at"])
