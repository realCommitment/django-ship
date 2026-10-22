from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from apps.users.adapter import EmailAsUsernameAdapter

from .models import Invitation

# the invitation a visitor without an account came from; redeemed once their email is verified
INVITATION_SESSION_KEY = "invitation:pk"
# where get_signup_redirect_url sends someone who joined a team on verifying their email
JOINED_TEAM_URL_SESSION_KEY = "invitation:joined_team_url"


class TeamInvitationAdapter(EmailAsUsernameAdapter):
    """Pegasus's adapter, plus redeeming the team invitation that sent a new visitor to signup."""

    def confirm_email(self, request, email_address):
        confirmed = super().confirm_email(request, email_address)
        invitation_pk = request.session.pop(INVITATION_SESSION_KEY, None)
        if confirmed and invitation_pk:
            # Read the Docs redeems at signup (core/adapters.py, MIT) without checking the email; accept() checks it
            invitation = Invitation.objects.select_related("team").filter(pk=invitation_pk).first()
            try:
                if invitation is None:
                    raise ValidationError(_("Your team invitation was revoked."))
                invitation.accept(email_address.user)
            except ValidationError as e:
                messages.error(request, e.messages[0])
            else:
                request.session[JOINED_TEAM_URL_SESSION_KEY] = invitation.team.get_absolute_url()
        return confirmed

    def get_signup_redirect_url(self, request):
        return request.session.pop(JOINED_TEAM_URL_SESSION_KEY, None) or super().get_signup_redirect_url(request)
