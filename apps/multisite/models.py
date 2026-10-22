from django.conf import settings
from django.contrib.sites.models import Site
from django.db import models

from apps.utils.models import BaseModel


class SignupSite(BaseModel):
    """The site a person signed up on. Accounts are global; this only records where they came from."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    site = models.ForeignKey(Site, null=True, on_delete=models.SET_NULL)

    def __str__(self) -> str:
        return f"{self.user} signed up on {self.site}"
