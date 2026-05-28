from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('register/', views.register_view, name='register'),
    path('login/',    views.login_view,    name='login'),
    path('logout/',   views.logout_view,   name='logout'),

    # Dashboard & profile
    path('',         views.home,    name='home'),
    path('profile/', views.profile, name='profile'),

    # Vehicles
    path('vehicles/',                views.vehicles,       name='vehicles'),
    path('add-vehicle/',             views.add_vehicle,    name='add_vehicle'),
    path('edit-vehicle/<int:id>/',   views.edit_vehicle,   name='edit_vehicle'),
    path('delete-vehicle/<int:id>/', views.delete_vehicle, name='delete_vehicle'),

    # Fuel
    path('fuel/',                 views.fuel_entry,   name='fuel_entry'),
    path('fuel-history/',         views.fuel_history, name='fuel_history'),
    path('edit-fuel/<int:id>/',   views.edit_fuel,    name='edit_fuel'),
    path('delete-fuel/<int:id>/', views.delete_fuel,  name='delete_fuel'),

    # Service
    path('service/',                 views.service_entry,   name='service_entry'),
    path('service-history/',         views.service_history, name='service_history'),
    path('edit-service/<int:id>/',   views.edit_service,    name='edit_service'),
    path('delete-service/<int:id>/', views.delete_service,  name='delete_service'),

    # Reports
    path('mileage/', views.mileage_report, name='mileage'),

    # Documents
    path('documents/',                   views.documents,        name='documents'),
    path('documents/add/',               views.add_document,     name='add_document'),
    path('documents/delete/<int:id>/',   views.delete_document,  name='delete_document'),
    path('documents/download/<int:id>/', views.download_document,name='download_document'),

    # Chart APIs
    path('api/chart/mileage/<int:vehicle_id>/',           views.chart_mileage,           name='chart_mileage'),
    path('api/chart/monthly-cost/<int:vehicle_id>/',      views.chart_monthly_cost,      name='chart_monthly_cost'),
    path('api/chart/service-breakdown/<int:vehicle_id>/', views.chart_service_breakdown, name='chart_service_breakdown'),


    # CSV Exports (Phase 5B)
    path('export/fuel/',    views.export_fuel,    name='export_fuel'),
    path('export/service/', views.export_service, name='export_service'),
    path('export/mileage/', views.export_mileage, name='export_mileage'),
    # PWA
    path('manifest.json', views.pwa_manifest, name='pwa_manifest'),
    path('offline/',      views.pwa_offline,  name='pwa_offline'),
]
