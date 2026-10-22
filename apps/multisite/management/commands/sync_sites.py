from typing import Any

from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update a Site row (domain and name) for each entry in settings.SITES. Safe to run again."

    def handle(self, *args: Any, **options: Any) -> None:
        for key, site in settings.SITES.items():
            # iexact, like Site.objects.get_current(request), so no second row differs only in case
            _, created = Site.objects.update_or_create(
                domain__iexact=site["domain"], defaults={"domain": site["domain"], "name": site["name"]}
            )
            self.stdout.write(f"{'Created' if created else 'Updated'} site {key}: {site['domain']}")
