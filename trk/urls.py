from django.urls import path
from . import views

urlpatterns = [
    path('vehicles/', views.vehicles, name='vehicles'),
    path('add-vehicle/', views.add_vehicle, name='add_vehicle'),
    path('fuel/', views.fuel_entry, name='fuel_entry'),
    path('fuel-history/', views.fuel_history, name='fuel_history'),
    path('service/', views.service_entry, name='service_entry'),
    path('service-history/', views.service_history, name='service_history'),
    path('mileage/', views.mileage_report, name='mileage'),
    path('', views.home, name='home'),
    path('delete-vehicle/<int:id>/', views.delete_vehicle, name='delete_vehicle'),
    path('delete-fuel/<int:id>/', views.delete_fuel, name='delete_fuel'),
    path('delete-service/<int:id>/', views.delete_service, name='delete_service'),
    path('edit-vehicle/<int:id>/', views.edit_vehicle, name='edit_vehicle'),
    path('edit-fuel/<int:id>/', views.edit_fuel, name='edit_fuel'),
    path('edit-service/<int:id>/', views.edit_service, name='edit_service'),    
]