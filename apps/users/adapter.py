from allauth.account import app_settings
from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.utils import user_email, user_field
from allauth.core import context
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class EmailAsUsernameAdapter(DefaultAccountAdapter):
    """
    Adapter that always sets the username equal to the user's email address.
    """

    def __init__(self, request=None):
        super().__init__(request)
        # Prevent leaking whether someone is already signed up.
        self.error_messages["email_taken"] = _("There was an issue creating the account. Please contact support.")

    def populate_username(self, request, user):
        # override the username population to always use the email
        user_field(user, app_settings.USER_MODEL_USERNAME_FIELD, user_email(user))

    def get_from_email(self):
        # allauth passes no request here; its middleware keeps the current one in a context variable
        if context.request is None:
            return settings.DEFAULT_FROM_EMAIL
        return settings.SITES[context.request.site_key]["from_email"]


class NoNewUsersAccountAdapter(DefaultAccountAdapter):
    """
    Adapter that can be used to disable public sign-ups for your app.
    """

    def is_open_for_signup(self, request):
        # see https://stackoverflow.com/a/29799664/8207
        return False
