from django.contrib import admin

from .models import Feature, ProductFeature


class ProductFeatureInline(admin.TabularInline):
    model = ProductFeature
    extra = 0


@admin.register(Feature)
class FeatureAdmin(admin.ModelAdmin):
    list_display = ("key", "site", "kind", "free_value")
    list_filter = ("site", "kind")
    search_fields = ("key",)
    inlines = [ProductFeatureInline]
