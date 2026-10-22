from typing import Any

from allauth.account.signals import user_signed_up
from django.dispatch import receiver
from django.http import HttpRequest

from apps.users.models import CustomUser

from .models import SignupSite


@receiver(user_signed_up)
def record_signup_site(request: HttpRequest, user: CustomUser, **kwargs: Any) -> None:
    """Record the site of the signup request (set by MultisiteMiddleware)."""
    SignupSite.objects.create(user=user, site=request.site)
