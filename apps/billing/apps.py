from django.apps import AppConfig


class BillingConfig(AppConfig):
    name = "apps.billing"

    def ready(self) -> None:
        # connects after dj-stripe's own handlers (djstripe comes first in INSTALLED_APPS), so they sync first
        from . import handlers  # noqa F401
