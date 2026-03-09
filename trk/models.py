from django.db import models


class Vehicle(models.Model):
    brand = models.CharField(max_length=100)
    name = models.CharField(max_length=100)
    year = models.IntegerField()
    fuel_type = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.brand} {self.name}"

class FuelEntry(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE)
    litres = models.FloatField()
    cost = models.FloatField()
    odometer = models.FloatField()
    date = models.DateField()
    full_tank = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.vehicle} - {self.litres}L"


class ServiceRecord(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE)
    service_type = models.CharField(max_length=100)
    odometer = models.DecimalField(max_digits=8, decimal_places=1, null=True, blank=True)
    cost = models.FloatField()
    date = models.DateField()
    description = models.TextField()

    def __str__(self):
        return f"{self.vehicle} - {self.service_type}"