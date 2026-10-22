from django.urls import path

from . import views

app_name = "billing"
urlpatterns = [
    path("a/<slug:team_slug>/billing/", views.billing, name="billing"),
    path("a/<slug:team_slug>/billing/checkout/", views.checkout, name="checkout"),
    path("a/<slug:team_slug>/billing/portal/", views.portal, name="portal"),
]
