import logging
import secrets
from datetime import timedelta

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.multisite.helpers import site_key_for
from apps.utils.models import BaseModel

# Model shape adapted from Keel's teams app (MIT): https://github.com/CuriousLearner/django-keel

logger = logging.getLogger(__name__)


class Role(models.IntegerChoices):
    # PostHog's membership levels (MIT), leaving room between them
    MEMBER = 1, _("Member")
    ADMIN = 8, _("Admin")


class TeamQuerySet(models.QuerySet):
    def for_user(self, user) -> TeamQuerySet:
        return self.filter(memberships__user=user)


class Team(BaseModel):
    """A team on one site; the directory calls it a business. Its admins are its owners."""

    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="teams")
    name = models.CharField(_("name"), max_length=100)
    slug = models.SlugField(max_length=100)
    # The payer: Stripe fields and get_stripe_subscription() from Read the Docs' organizations (MIT)
    stripe_customer = models.OneToOneField(
        "djstripe.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="team"
    )
    # re-picked with get_stripe_subscription() after every subscription webhook
    stripe_subscription = models.OneToOneField(
        "djstripe.Subscription", null=True, blank=True, on_delete=models.SET_NULL, related_name="team"
    )

    objects = TeamQuerySet.as_manager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["site", "slug"], name="team_unique_slug_per_site")]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("teams:home", args=[self.slug])

    @property
    def site_key(self) -> str:
        return site_key_for(self.site)

    def get_stripe_subscription(self):
        """The customer's subscription that decides the team's plan: by status, then the latest; None without one."""
        if self.stripe_customer is None:
            return None
        subscriptions = self.stripe_customer.subscriptions.order_by("created")
        for status in ["active", "past_due", "trialing", "incomplete"]:
            matching = subscriptions.filter(stripe_data__status=status)
            if len(matching) > 1:
                # Two paid subscriptions: both are billed. Cancel one in the Stripe dashboard.
                logger.error("Team %s has %s %s subscriptions", self.pk, len(matching), status)
            if matching:
                return matching[len(matching) - 1]
        return subscriptions.last()


class MembershipQuerySet(models.QuerySet):
    def admins(self) -> MembershipQuerySet:
        return self.filter(role=Role.ADMIN)


class Membership(BaseModel):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="team_memberships")
    role = models.PositiveSmallIntegerField(choices=Role.choices, default=Role.MEMBER)

    objects = MembershipQuerySet.as_manager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["team", "user"], name="membership_unique_user_per_team")]

    def __str__(self) -> str:
        return f"{self.user} in {self.team} ({self.get_role_display()})"

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN


def validate_role_change(actor: Membership, target: Membership, new_role: int | None) -> None:
    """
    Raise ValidationError unless `actor` may give `target` the role `new_role` (None removes `target`).
    Call it inside transaction.atomic(), followed by the change: it locks the team until the transaction ends.
    Last-admin guard from Read the Docs' organizations (MIT): readthedocs/organizations/querysets.py
    """
    # serialise role changes in a team, so two admins demoting each other can't both pass the count,
    # and decide on both rows as they are once the lock is held
    Team.objects.select_for_update().get(pk=target.team_id)
    roles = dict(Membership.objects.filter(pk__in=[actor.pk, target.pk]).values_list("pk", "role"))
    if actor.pk not in roles or target.pk not in roles:
        raise ValidationError(_("That person is no longer a member."), code="not_member")
    actor.role, target.role = roles[actor.pk], roles[target.pk]
    if not actor.is_admin and not (actor.pk == target.pk and new_role is None):
        raise ValidationError(_("Only admins can change roles or remove members."), code="not_admin")
    if (
        target.is_admin
        and new_role != Role.ADMIN
        and Membership.objects.filter(team_id=target.team_id).admins().count() == 1
    ):
        raise ValidationError(_("Every team needs an admin. Make someone else an admin first."), code="last_admin")


def generate_token() -> str:
    return secrets.token_urlsafe(32)


class InvitationQuerySet(models.QuerySet):
    # open()/expired() named after Read the Docs' pending()/expired() (MIT): readthedocs/invitations/models.py
    def open(self) -> InvitationQuerySet:
        return self.filter(accepted_at__isnull=True)

    def expired(self) -> InvitationQuerySet:
        return self.open().filter(sent_at__lte=timezone.now() - timedelta(days=settings.TEAM_INVITATION_EXPIRY_DAYS))


class Invitation(BaseModel):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField(_("email"))  # stored lowercased
    role = models.PositiveSmallIntegerField(choices=Role.choices, default=Role.MEMBER)
    token = models.CharField(max_length=64, unique=True, default=generate_token, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="sent_team_invitations"
    )
    sent_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)

    objects = InvitationQuerySet.as_manager()

    class Meta:
        constraints = [
            # one open invitation per address and team; accepted ones stay as a record, so people can be re-invited
            models.UniqueConstraint(
                fields=["team", "email"], condition=Q(accepted_at__isnull=True), name="invitation_unique_open_email"
            )
        ]

    def __str__(self) -> str:
        return f"Invitation for {self.email} to {self.team}"

    def save(self, *args, **kwargs) -> None:
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("teams:invitation", args=[self.token])

    @property
    def is_expired(self) -> bool:
        return self.sent_at <= timezone.now() - timedelta(days=settings.TEAM_INVITATION_EXPIRY_DAYS)

    def validate(self, user=None) -> None:
        """
        Raise ValidationError if `user` may not accept this invitation; without a user, check only the expiry.
        The site is checked by the views' lookup.
        Error codes in the style of PostHog's OrganizationInvite.validate (MIT): posthog/models/organization_invite.py
        """
        if self.is_expired:
            raise ValidationError(
                _("This invitation has expired. Ask an admin of %(team)s to invite you again."),
                code="expired",
                params={"team": self.team},
            )
        if user is None:
            return
        if Membership.objects.filter(team_id=self.team_id, user=user).exists():
            raise ValidationError(
                _("You are already a member of %(team)s."), code="already_member", params={"team": self.team}
            )
        if not EmailAddress.objects.filter(user=user, email__iexact=self.email, verified=True).exists():
            raise ValidationError(
                _("This invitation was sent to %(email)s. Log in with that address, or verify it on your account."),
                code="email_mismatch",
                params={"email": self.email},
            )

    def accept(self, user) -> Membership:
        """Validate, add `user` to the team and mark the invitation accepted. Raises ValidationError."""
        with transaction.atomic():
            # Row lock as in PostHog's OrganizationInvite.use: concurrent accepts of one link run one after the other,
            # and the second finds the invitation already accepted.
            try:
                locked = Invitation.objects.open().select_for_update().get(pk=self.pk)
            except Invitation.DoesNotExist:
                raise ValidationError(_("This invitation has already been used."), code="expired") from None
            locked.validate(user)
            membership = Membership.objects.create(team_id=locked.team_id, user=user, role=locked.role)
            locked.accepted_at = timezone.now()
            locked.save(update_fields=["accepted_at", "updated_at"])
        self.accepted_at = locked.accepted_at
        return membership
