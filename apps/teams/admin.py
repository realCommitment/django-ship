from django.contrib import admin

from .models import Invitation, Membership, Team


class MembershipInline(admin.TabularInline):
    model = Membership
    raw_id_fields = ("user",)
    extra = 0


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "site", "created_at")
    list_filter = ("site",)
    search_fields = ("name", "slug")
    # set by Checkout and the Stripe webhooks; an admin form save would write back a stale subscription
    readonly_fields = ("stripe_customer", "stripe_subscription")
    inlines = [MembershipInline]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "team", "role", "created_at")
    list_filter = ("role", "team__site")
    search_fields = ("user__email", "team__name")
    raw_id_fields = ("user", "team")


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ("email", "team", "role", "invited_by", "sent_at", "accepted_at")
    list_filter = ("role", "team__site")
    search_fields = ("email", "team__name")
    raw_id_fields = ("team", "invited_by")
