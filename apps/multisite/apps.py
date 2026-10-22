from django.apps import AppConfig


class MultisiteConfig(AppConfig):
    name = "apps.multisite"
    # not "sites": that label belongs to django.contrib.sites
    label = "multisite"

    def ready(self) -> None:
        from . import signals  # noqa F401
