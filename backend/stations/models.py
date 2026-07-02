from django.db import models


class FuelStation(models.Model):
    opis_id = models.PositiveIntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    rack_id = models.CharField(max_length=20)
    price_per_gallon = models.DecimalField(max_digits=6, decimal_places=5)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["state", "city"])]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state}) - ${self.price_per_gallon}"
