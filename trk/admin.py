from django.contrib import admin
from .models import Vehicle, FuelEntry, ServiceRecord

admin.site.register(Vehicle)
admin.site.register(FuelEntry)
admin.site.register(ServiceRecord)