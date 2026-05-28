from django.db import models
from django.contrib.auth.models import User
from datetime import date

FUEL_TYPE_CHOICES = [
    ('Petrol', 'Petrol'),
    ('Diesel', 'Diesel'),
    ('Electric', 'Electric'),
    ('CNG', 'CNG'),
    ('Hybrid', 'Hybrid'),
]

DOC_TYPE_CHOICES = [
    ('Insurance', 'Insurance'),
    ('RC Book', 'RC Book'),
    ('PUC', 'PUC Certificate'),
    ('Invoice', 'Service Invoice'),
    ('Warranty', 'Warranty Card'),
    ('Other', 'Other'),
]

class Vehicle(models.Model):
    user      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vehicles', null=True, blank=True)
    brand     = models.CharField(max_length=100)
    name      = models.CharField(max_length=100)
    year      = models.IntegerField()
    fuel_type = models.CharField(max_length=20, choices=FUEL_TYPE_CHOICES)
    class Meta:
        verbose_name = 'Vehicle'; verbose_name_plural = 'Vehicles'; ordering = ['-id']
    def __str__(self):
        return f"{self.brand} {self.name} ({self.year})"

class FuelEntry(models.Model):
    vehicle   = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='fuel_entries')
    litres    = models.FloatField()
    cost      = models.FloatField()
    odometer  = models.FloatField()
    date      = models.DateField()
    full_tank = models.BooleanField(default=False)
    class Meta:
        verbose_name = 'Fuel Entry'; verbose_name_plural = 'Fuel Entries'; ordering = ['date', 'id']
    def __str__(self):
        return f"{self.vehicle} — {self.litres}L on {self.date}"

class ServiceRecord(models.Model):
    vehicle      = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='service_records')
    service_type = models.CharField(max_length=100)
    odometer     = models.DecimalField(max_digits=8, decimal_places=1, null=True, blank=True)
    cost         = models.FloatField()
    date         = models.DateField()
    description  = models.TextField(blank=True, default='')
    class Meta:
        verbose_name = 'Service Record'; verbose_name_plural = 'Service Records'; ordering = ['-date']
    def __str__(self):
        return f"{self.vehicle} — {self.service_type} on {self.date}"

class Document(models.Model):
    vehicle     = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='documents')
    doc_type    = models.CharField(max_length=30, choices=DOC_TYPE_CHOICES)
    title       = models.CharField(max_length=150)
    file        = models.FileField(upload_to='documents/%Y/%m/')
    expiry_date = models.DateField(null=True, blank=True)
    note        = models.TextField(blank=True, default='')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        verbose_name = 'Document'; verbose_name_plural = 'Documents'; ordering = ['-uploaded_at']
    def __str__(self):
        return f"{self.doc_type} — {self.vehicle}"
    @property
    def days_until_expiry(self):
        if not self.expiry_date: return None
        return (self.expiry_date - date.today()).days
    @property
    def expiry_status(self):
        days = self.days_until_expiry
        if days is None: return 'none'
        if days < 0: return 'expired'
        if days <= 30: return 'critical'
        if days <= 90: return 'warning'
        return 'ok'
