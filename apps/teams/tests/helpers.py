from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.sites.models import Site

from apps.teams.models import Membership, Role, Team
from apps.users.models import CustomUser

PASSWORD = "a-long-password-1"


def make_user(email: str, verified: bool = True) -> CustomUser:
    user = CustomUser.objects.create_user(username=email, email=email, password=PASSWORD)
    EmailAddress.objects.create(user=user, email=email, verified=verified, primary=True)
    return user


def make_team(site_key: str, admin: CustomUser, slug: str = "acme") -> Team:
    site = Site.objects.get(domain=settings.SITES[site_key]["domain"])
    team = Team.objects.create(site=site, name=slug.title(), slug=slug)
    Membership.objects.create(team=team, user=admin, role=Role.ADMIN)
    return team
