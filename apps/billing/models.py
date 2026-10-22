from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.multisite.helpers import site_key_for
from apps.utils.models import BaseModel

# Features in the style of Chargebee's (on/off or a quantity), with a value per Stripe product.


class Feature(BaseModel):
    class Kind(models.TextChoices):
        ON_OFF = "on_off", _("On/off")
        QUANTITY = "quantity", _("Quantity")

    key = models.CharField(max_length=100, unique=True, help_text=_("<site key>.<name>, e.g. productivity.export"))
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="features")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    free_value = models.PositiveIntegerField(help_text=_("For teams without a paid plan. 0 or 1 for on/off."))

    def __str__(self) -> str:
        return self.key

    def clean(self) -> None:
        if self.site_id:
            try:
                site_key = site_key_for(self.site)
            except KeyError:
                raise ValidationError({"site": _("This site is not in settings.SITES.")}) from None
            if not self.key.startswith(f"{site_key}."):
                raise ValidationError({"key": _("The key must start with %s") % f"{site_key}."})
        if self.kind == self.Kind.ON_OFF and self.free_value not in (0, 1):
            raise ValidationError({"free_value": _("An on/off feature's free value is 0 or 1.")})


class ProductFeature(BaseModel):
    product = models.ForeignKey("djstripe.Product", on_delete=models.CASCADE, related_name="feature_values")
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="product_values")
    value = models.PositiveIntegerField(help_text=_("Per unit of the plan. For on/off, anything above 0 is on."))

    class Meta:
        constraints = [models.UniqueConstraint(fields=["product", "feature"], name="product_feature_unique")]

    def __str__(self) -> str:
        return f"{self.feature} = {self.value} on {self.product}"
