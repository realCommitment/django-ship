from django.urls import path

from . import views

app_name = "teams"
urlpatterns = [
    path("teams/new/", views.create_team, name="create"),
    path("a/<slug:team_slug>/", views.team_home, name="home"),
    path("a/<slug:team_slug>/members/", views.members, name="members"),
    path("a/<slug:team_slug>/members/invite/", views.invite, name="invite"),
    path("a/<slug:team_slug>/members/<int:membership_id>/role/", views.change_role, name="change_role"),
    path("a/<slug:team_slug>/members/<int:membership_id>/remove/", views.remove_member, name="remove_member"),
    path("a/<slug:team_slug>/leave/", views.leave, name="leave"),
    path("a/<slug:team_slug>/invitations/<int:invitation_id>/revoke/", views.revoke_invitation, name="revoke"),
    path("invitations/<slug:token>/", views.invitation, name="invitation"),
]
