from django.contrib.sitemaps.views import sitemap
from django.urls import path
from django.views.generic import TemplateView

from apps.web.sitemaps import StaticViewSitemap
from project.urls import urlpatterns as shared_urlpatterns

from . import views


class ProductivitySitemap(StaticViewSitemap):
    def items(self):
        # this site's public pages, by URL name
        return ["home"]


# This site's pages first, then the routes every site shares (admin, accounts, users, API, Pegasus's web app).
urlpatterns = [
    path("", views.home, name="home"),
    path("robots.txt", TemplateView.as_view(template_name="productivity/robots.txt", content_type="text/plain")),
    path("sitemap.xml", sitemap, {"sitemaps": {"static": ProductivitySitemap()}}),
    path("a/<slug:team_slug>/export/", views.export, name="export"),
    *shared_urlpatterns,
]
