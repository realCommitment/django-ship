import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from apps.web.meta import get_protocol

from .models import Invitation

logger = logging.getLogger(__name__)


@shared_task
def send_invitation_email(invitation_id: int) -> None:
    """Email an invitation from its team's site: that site's domain in the link, its sender address and label."""
    invitation = Invitation.objects.open().select_related("team__site", "invited_by").filter(pk=invitation_id).first()
    if invitation is None:  # revoked (or accepted) before the worker got to it: nothing to send
        logger.info("Team invitation %s is no longer open; not sending its email", invitation_id)
        return
    team = invitation.team
    site = settings.SITES[team.site_key]
    path = reverse("teams:invitation", args=[invitation.token], urlconf=site["urlconf"])
    context = {
        "invitation": invitation,
        "team": team,
        "team_label": site["team_label"],
        "site_name": team.site.name,
        "invitation_url": f"{get_protocol()}://{team.site.domain}{path}",
    }
    send_mail(
        # one line even if the team name has a line break, as allauth does for its subjects
        subject=" ".join(render_to_string("teams/email/invitation_subject.txt", context).splitlines()).strip(),
        message=render_to_string("teams/email/invitation_message.txt", context),
        html_message=render_to_string("teams/email/invitation_message.html", context),
        from_email=site["from_email"],
        recipient_list=[invitation.email],
    )
