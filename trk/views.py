from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Prefetch
from django.http import JsonResponse, FileResponse, Http404
from django.core.files.storage import default_storage

from .models import Vehicle, FuelEntry, ServiceRecord, Document
from .forms import VehicleForm, FuelEntryForm, ServiceRecordForm, DocumentForm, RegisterForm, LoginForm
from datetime import date
from collections import defaultdict
import json, os


# ─────────────────────────────────────────
# Auth
# ─────────────────────────────────────────

def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.username}! Your account is ready.')
            return redirect('home')
    else:
        form = RegisterForm()
    return render(request, 'trk/auth/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            return redirect(request.GET.get('next', 'home'))
    else:
        form = LoginForm(request)
    return render(request, 'trk/auth/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, 'You have been signed out.')
    return redirect('login')


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def _user_vehicles(user):
    return Vehicle.objects.filter(user=user)


def _get_vehicle(user, vehicle_id):
    return get_object_or_404(Vehicle, id=vehicle_id, user=user)


def _compute_mileage_segments(entries, vehicle):
    mileage_list = []
    start_odometer = None
    fuel_sum = 0.0
    tracking_started = False
    for entry in entries:
        if not tracking_started:
            if entry.full_tank:
                start_odometer = entry.odometer
                tracking_started = True
                fuel_sum = 0.0
            continue
        fuel_sum += entry.litres
        if entry.full_tank:
            distance = entry.odometer - start_odometer
            if distance > 0 and fuel_sum > 0:
                mileage_list.append({
                    'vehicle': vehicle,
                    'distance': round(distance, 1),
                    'fuel': round(fuel_sum, 2),
                    'mileage': round(distance / fuel_sum, 2),
                    'date': entry.date,
                })
            start_odometer = entry.odometer
            fuel_sum = 0.0
    return mileage_list


def _last_segment_mileage(entries):
    full_tank_indices = [i for i, e in enumerate(entries) if e.full_tank]
    if len(full_tank_indices) < 2:
        return None
    end_idx   = full_tank_indices[-1]
    start_idx = full_tank_indices[-2]
    fuel_sum  = sum(e.litres for e in entries[start_idx + 1: end_idx + 1])
    distance  = entries[end_idx].odometer - entries[start_idx].odometer
    if distance > 0 and fuel_sum > 0:
        return round(distance / fuel_sum, 2)
    return None


def _monthly_cost(fuel_entries):
    monthly = defaultdict(float)
    for entry in fuel_entries:
        monthly[entry.date.strftime('%Y-%m')] += entry.cost
    return dict(sorted(monthly.items()))


def _smart_insights(fuel_entries_list, mileage_segments):
    insights = []
    if mileage_segments:
        effs  = [s['mileage'] for s in mileage_segments]
        best  = max(effs)
        avg   = round(sum(effs) / len(effs), 2)
        trend = round(effs[-1] - effs[-2], 2) if len(effs) >= 2 else 0
        insights.append({'label': 'Best ever mileage', 'value': f'{best} km/L', 'icon': 'trending-up',    'color': 'green'})
        insights.append({'label': 'Average mileage',   'value': f'{avg} km/L',  'icon': 'bar-chart-2',    'color': 'blue'})
        if trend > 0:
            insights.append({'label': 'Mileage improving', 'value': f'+{trend} km/L', 'icon': 'arrow-up-right',   'color': 'green'})
        elif trend < 0:
            insights.append({'label': 'Mileage declining', 'value': f'{trend} km/L',  'icon': 'arrow-down-right', 'color': 'red'})
    if fuel_entries_list:
        avg_cost     = round(sum(e.cost for e in fuel_entries_list) / len(fuel_entries_list), 2)
        total_litres = round(sum(e.litres for e in fuel_entries_list), 2)
        insights.append({'label': 'Avg cost per fill-up', 'value': f'₹{avg_cost}',     'icon': 'indian-rupee', 'color': 'amber'})
        insights.append({'label': 'Total fuel consumed',  'value': f'{total_litres} L', 'icon': 'droplets',     'color': 'blue'})
    return insights


# ─────────────────────────────────────────
# Dashboard  — OPTIMISED with prefetch
# ─────────────────────────────────────────

@login_required
def home(request):
    # prefetch_related eliminates N+1 when iterating vehicle list in template
    vehicles = _user_vehicles(request.user).prefetch_related(
        Prefetch('fuel_entries', queryset=FuelEntry.objects.order_by('date', 'id')),
        Prefetch('service_records', queryset=ServiceRecord.objects.order_by('-date')),
        'documents',
    )

    selected_vehicle = None
    total_fuel_entries = total_fuel_cost = total_services = 0
    last_service = last_mileage = None
    insights = []
    monthly_chart_data = mileage_chart_data = '{}'
    expiring_docs = []

    if request.method == 'POST':
        vehicle_id = request.POST.get('vehicle')
        selected_vehicle = _get_vehicle(request.user, vehicle_id)
    else:
        selected_vehicle = vehicles.order_by('-id').first()

    if selected_vehicle:
        fuel_qs   = FuelEntry.objects.filter(vehicle=selected_vehicle).order_by('date', 'id')
        fuel_list = list(fuel_qs)
        services  = ServiceRecord.objects.filter(vehicle=selected_vehicle)

        total_fuel_entries = len(fuel_list)
        total_services     = services.count()
        total_fuel_cost    = round(fuel_qs.aggregate(t=Sum('cost'))['t'] or 0, 2)
        last_service       = services.order_by('-date').first()
        last_mileage       = _last_segment_mileage(fuel_list)

        segs     = _compute_mileage_segments(fuel_list, selected_vehicle)
        insights = _smart_insights(fuel_list, segs)

        monthly = _monthly_cost(fuel_list)
        monthly_chart_data = json.dumps({'labels': list(monthly.keys()), 'values': [round(v,2) for v in monthly.values()]})
        mileage_chart_data = json.dumps({'labels': [s['date'].strftime('%Y-%m-%d') for s in segs], 'values': [s['mileage'] for s in segs]})

        # single optimised query for expiring docs across all user vehicles
        all_docs = (Document.objects
                    .filter(vehicle__user=request.user)
                    .exclude(expiry_date__isnull=True)
                    .select_related('vehicle')
                    .order_by('expiry_date'))
        expiring_docs = [d for d in all_docs if d.days_until_expiry is not None and d.days_until_expiry <= 60]

    return render(request, 'trk/home.html', {
        'vehicles': vehicles, 'selected_vehicle': selected_vehicle,
        'total_fuel_entries': total_fuel_entries, 'total_fuel_cost': total_fuel_cost,
        'total_services': total_services, 'last_service': last_service,
        'last_mileage': last_mileage, 'insights': insights,
        'monthly_chart_data': monthly_chart_data, 'mileage_chart_data': mileage_chart_data,
        'expiring_docs': expiring_docs,
    })


# ─────────────────────────────────────────
# Vehicles  — OPTIMISED
# ─────────────────────────────────────────

@login_required
def vehicles(request):
    # prefetch avoids N+1 if template accesses counts
    data = (_user_vehicles(request.user)
            .prefetch_related('fuel_entries', 'service_records', 'documents')
            .order_by('-id'))
    return render(request, 'trk/vehicles.html', {'vehicles': data})


@login_required
def add_vehicle(request):
    if request.method == 'POST':
        form = VehicleForm(request.POST)
        if form.is_valid():
            v = form.save(commit=False)
            v.user = request.user
            v.save()
            messages.success(request, 'Vehicle added.')
            return redirect('vehicles')
    else:
        form = VehicleForm()
    return render(request, 'trk/add_vehicle.html', {'form': form})


@login_required
def edit_vehicle(request, id):
    vehicle = _get_vehicle(request.user, id)
    if request.method == 'POST':
        form = VehicleForm(request.POST, instance=vehicle)
        if form.is_valid():
            form.save()
            messages.success(request, 'Vehicle updated.')
            return redirect('vehicles')
    else:
        form = VehicleForm(instance=vehicle)
    return render(request, 'trk/edit_vehicle.html', {'form': form, 'vehicle': vehicle})


@login_required
@require_POST
def delete_vehicle(request, id):
    vehicle = _get_vehicle(request.user, id)
    vehicle.delete()
    messages.success(request, 'Vehicle deleted.')
    return redirect('vehicles')


# ─────────────────────────────────────────
# Fuel  — OPTIMISED with select_related
# ─────────────────────────────────────────

@login_required
def fuel_entry(request):
    if request.method == 'POST':
        form = FuelEntryForm(request.POST)
        form.fields['vehicle'].queryset = _user_vehicles(request.user)
        if form.is_valid():
            vehicle  = form.cleaned_data['vehicle']
            odometer = form.cleaned_data['odometer']
            last     = FuelEntry.objects.filter(vehicle=vehicle).order_by('-id').first()
            if last and odometer < last.odometer:
                form.add_error('odometer', f'Must be ≥ last entry ({last.odometer} km).')
            else:
                form.save()
                messages.success(request, 'Fuel entry saved.')
                return redirect('home')
    else:
        form = FuelEntryForm(initial={'date': date.today()})
        form.fields['vehicle'].queryset = _user_vehicles(request.user)
    return render(request, 'trk/fuel_entry.html', {'form': form})


@login_required
def fuel_history(request):
    user_vehicles = _user_vehicles(request.user)
    fuel_data, selected_vehicle = [], None
    vehicle_id = request.POST.get('vehicle') or request.GET.get('vehicle')
    if vehicle_id:
        selected_vehicle = _get_vehicle(request.user, vehicle_id)
        fuel_data = (FuelEntry.objects
                     .filter(vehicle=selected_vehicle)
                     .select_related('vehicle')       # avoids N+1 on vehicle FK in template
                     .order_by('-date', '-id'))
    return render(request, 'trk/fuel_history.html', {
        'vehicles': user_vehicles, 'fuel': fuel_data, 'selected_vehicle': selected_vehicle,
    })


@login_required
def edit_fuel(request, id):
    entry = get_object_or_404(FuelEntry, id=id, vehicle__user=request.user)
    if request.method == 'POST':
        form = FuelEntryForm(request.POST, instance=entry)
        form.fields['vehicle'].queryset = _user_vehicles(request.user)
        if form.is_valid():
            vehicle  = form.cleaned_data['vehicle']
            odometer = form.cleaned_data['odometer']
            last     = FuelEntry.objects.filter(vehicle=vehicle).exclude(id=entry.id).order_by('-id').first()
            if last and odometer < last.odometer:
                form.add_error('odometer', f'Must be ≥ last entry ({last.odometer} km).')
            else:
                form.save()
                messages.success(request, 'Fuel entry updated.')
                return redirect(f'/fuel-history/?vehicle={vehicle.id}')
    else:
        form = FuelEntryForm(instance=entry)
        form.fields['vehicle'].queryset = _user_vehicles(request.user)
    return render(request, 'trk/edit_fuel.html', {'form': form, 'entry': entry})


@login_required
@require_POST
def delete_fuel(request, id):
    entry = get_object_or_404(FuelEntry, id=id, vehicle__user=request.user)
    vid = entry.vehicle_id
    entry.delete()
    messages.success(request, 'Fuel entry deleted.')
    return redirect(f'/fuel-history/?vehicle={vid}')


# ─────────────────────────────────────────
# Service  — OPTIMISED
# ─────────────────────────────────────────

@login_required
def service_entry(request):
    if request.method == 'POST':
        form = ServiceRecordForm(request.POST)
        form.fields['vehicle'].queryset = _user_vehicles(request.user)
        if form.is_valid():
            vehicle  = form.cleaned_data['vehicle']
            odometer = form.cleaned_data.get('odometer')
            if odometer:
                last = ServiceRecord.objects.filter(vehicle=vehicle, odometer__isnull=False).order_by('-id').first()
                if last and odometer < last.odometer:
                    form.add_error('odometer', f'Must be ≥ last service ({last.odometer} km).')
                    return render(request, 'trk/service_entry.html', {'form': form})
            form.save()
            messages.success(request, 'Service record saved.')
            return redirect('service_history')
    else:
        form = ServiceRecordForm(initial={'date': date.today()})
        form.fields['vehicle'].queryset = _user_vehicles(request.user)
    return render(request, 'trk/service_entry.html', {'form': form})


@login_required
def service_history(request):
    services = (ServiceRecord.objects
                .filter(vehicle__user=request.user)
                .select_related('vehicle')   # single JOIN instead of N queries
                .order_by('-date'))
    svc_by_vehicle = {}
    for s in services:
        name = str(s.vehicle)
        svc_by_vehicle[name] = round(svc_by_vehicle.get(name, 0) + s.cost, 2)
    service_chart_data = json.dumps({'labels': list(svc_by_vehicle.keys()), 'values': list(svc_by_vehicle.values())})
    return render(request, 'trk/service_history.html', {
        'services': services, 'service_chart_data': service_chart_data,
    })


@login_required
def edit_service(request, id):
    record = get_object_or_404(ServiceRecord, id=id, vehicle__user=request.user)
    if request.method == 'POST':
        form = ServiceRecordForm(request.POST, instance=record)
        form.fields['vehicle'].queryset = _user_vehicles(request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Service record updated.')
            return redirect('service_history')
    else:
        form = ServiceRecordForm(instance=record)
        form.fields['vehicle'].queryset = _user_vehicles(request.user)
    return render(request, 'trk/edit_service.html', {'form': form, 'record': record})


@login_required
@require_POST
def delete_service(request, id):
    record = get_object_or_404(ServiceRecord, id=id, vehicle__user=request.user)
    record.delete()
    messages.success(request, 'Service record deleted.')
    return redirect('service_history')


# ─────────────────────────────────────────
# Mileage  — OPTIMISED
# ─────────────────────────────────────────

@login_required
def mileage_report(request):
    user_vehicles = _user_vehicles(request.user)
    mileage_list, selected_vehicle = [], None
    mileage_chart_data = cost_per_km_data = '{}'
    avg_mileage = best_mileage = None

    vehicle_id = request.POST.get('vehicle') or request.GET.get('vehicle')
    if vehicle_id:
        selected_vehicle = _get_vehicle(request.user, vehicle_id)
        entries      = list(FuelEntry.objects.filter(vehicle=selected_vehicle).order_by('date', 'id'))
        mileage_list = _compute_mileage_segments(entries, selected_vehicle)

        if mileage_list:
            effs         = [m['mileage'] for m in mileage_list]
            avg_mileage  = round(sum(effs) / len(effs), 2)
            best_mileage = max(effs)
            mileage_chart_data = json.dumps({
                'labels': [m['date'].strftime('%d %b %Y') for m in mileage_list],
                'values': effs,
                'avg': avg_mileage,
            })
            tracking, start_odo, cost_sum, cpkm_segs = False, 0, 0.0, []
            for entry in entries:
                if not tracking:
                    if entry.full_tank:
                        tracking, start_odo, cost_sum = True, entry.odometer, 0.0
                    continue
                cost_sum += entry.cost
                if entry.full_tank:
                    dist = entry.odometer - start_odo
                    if dist > 0:
                        cpkm_segs.append({'date': entry.date.strftime('%d %b %Y'), 'cpkm': round(cost_sum / dist, 2)})
                    start_odo, cost_sum = entry.odometer, 0.0
            cost_per_km_data = json.dumps({'labels': [s['date'] for s in cpkm_segs], 'values': [s['cpkm'] for s in cpkm_segs]})

    return render(request, 'trk/mileage.html', {
        'vehicles': user_vehicles, 'data': mileage_list, 'selected_vehicle': selected_vehicle,
        'mileage_chart_data': mileage_chart_data, 'cost_per_km_data': cost_per_km_data,
        'avg_mileage': avg_mileage, 'best_mileage': best_mileage,
    })


# ─────────────────────────────────────────
# Documents  — OPTIMISED
# ─────────────────────────────────────────

@login_required
def documents(request):
    vehicle_id    = request.GET.get('vehicle')
    user_vehicles = _user_vehicles(request.user)
    selected_vehicle = None
    docs = (Document.objects
            .filter(vehicle__user=request.user)
            .select_related('vehicle')   # avoids extra query per doc in template
            .order_by('expiry_date'))
    if vehicle_id:
        selected_vehicle = _get_vehicle(request.user, vehicle_id)
        docs = docs.filter(vehicle=selected_vehicle)
    return render(request, 'trk/documents.html', {
        'docs': docs, 'vehicles': user_vehicles, 'selected_vehicle': selected_vehicle,
    })


@login_required
def add_document(request):
    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES)
        form.fields['vehicle'].queryset = _user_vehicles(request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Document uploaded.')
            return redirect('documents')
    else:
        form = DocumentForm()
        form.fields['vehicle'].queryset = _user_vehicles(request.user)
        if request.GET.get('vehicle'):
            form.fields['vehicle'].initial = request.GET.get('vehicle')
    return render(request, 'trk/add_document.html', {'form': form})


@login_required
@require_POST
def delete_document(request, id):
    doc = get_object_or_404(Document, id=id, vehicle__user=request.user)
    if doc.file and default_storage.exists(doc.file.name):
        default_storage.delete(doc.file.name)
    doc.delete()
    messages.success(request, 'Document deleted.')
    return redirect('documents')


@login_required
def download_document(request, id):
    doc = get_object_or_404(Document, id=id, vehicle__user=request.user)
    if not doc.file or not default_storage.exists(doc.file.name):
        raise Http404('File not found.')
    return FileResponse(
        default_storage.open(doc.file.name, 'rb'),
        as_attachment=True,
        filename=os.path.basename(doc.file.name)
    )


# ─────────────────────────────────────────
# Profile  — OPTIMISED (aggregates in one pass)
# ─────────────────────────────────────────

@login_required
def profile(request):
    user_vehicles  = _user_vehicles(request.user)
    total_vehicles = user_vehicles.count()
    total_fuel     = FuelEntry.objects.filter(vehicle__user=request.user).count()
    total_services = ServiceRecord.objects.filter(vehicle__user=request.user).count()
    total_docs     = Document.objects.filter(vehicle__user=request.user).count()
    total_cost     = FuelEntry.objects.filter(vehicle__user=request.user).aggregate(t=Sum('cost'))['t'] or 0
    return render(request, 'trk/profile.html', {
        'total_vehicles': total_vehicles, 'total_fuel': total_fuel,
        'total_services': total_services, 'total_docs': total_docs,
        'total_cost': round(total_cost, 2),
    })


# ─────────────────────────────────────────
# Chart JSON APIs
# ─────────────────────────────────────────

@login_required
def chart_mileage(request, vehicle_id):
    vehicle = _get_vehicle(request.user, vehicle_id)
    entries = list(FuelEntry.objects.filter(vehicle=vehicle).order_by('date', 'id'))
    segs    = _compute_mileage_segments(entries, vehicle)
    return JsonResponse({'labels': [s['date'].strftime('%d %b %Y') for s in segs], 'values': [s['mileage'] for s in segs]})


@login_required
def chart_monthly_cost(request, vehicle_id):
    vehicle = _get_vehicle(request.user, vehicle_id)
    entries = list(FuelEntry.objects.filter(vehicle=vehicle).order_by('date'))
    monthly = _monthly_cost(entries)
    return JsonResponse({'labels': list(monthly.keys()), 'values': [round(v,2) for v in monthly.values()]})


@login_required
def chart_service_breakdown(request, vehicle_id):
    vehicle  = _get_vehicle(request.user, vehicle_id)
    services = ServiceRecord.objects.filter(vehicle=vehicle)
    by_type  = defaultdict(float)
    for s in services:
        by_type[s.service_type] += s.cost
    return JsonResponse({'labels': list(by_type.keys()), 'values': [round(v,2) for v in by_type.values()]})


# ─────────────────────────────────────────
# PWA views
# ─────────────────────────────────────────

def pwa_manifest(request):
    return render(request, 'trk/pwa/manifest.json', content_type='application/manifest+json')


def pwa_offline(request):
    return render(request, 'trk/pwa/offline.html')


# ─────────────────────────────────────────
# Error handlers (wired in fstp/urls.py)
# ─────────────────────────────────────────

def error_404(request, exception=None):
    return render(request, 'trk/errors/404.html', status=404)


def error_500(request):
    return render(request, 'trk/errors/500.html', status=500)


# ─────────────────────────────────────────
# CSV Exports  (Phase 5B)
# ─────────────────────────────────────────

import csv
from django.http import HttpResponse
from django.utils import timezone


def _csv_response(filename):
    """Return an HttpResponse pre-configured for CSV download."""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    # UTF-8 BOM so Excel opens it correctly without import wizard
    response.write('\ufeff')
    return response


@login_required
def export_fuel(request):
    """Export fuel history for a vehicle (or all vehicles) as CSV."""
    vehicle_id = request.GET.get('vehicle')
    qs = (FuelEntry.objects
          .filter(vehicle__user=request.user)
          .select_related('vehicle')
          .order_by('vehicle__id', 'date', 'id'))

    if vehicle_id:
        vehicle = _get_vehicle(request.user, vehicle_id)
        qs = qs.filter(vehicle=vehicle)
        filename = f'fuel_{vehicle.brand}_{vehicle.name}_{date.today()}.csv'.replace(' ', '_')
    else:
        filename = f'fuel_all_{date.today()}.csv'

    response = _csv_response(filename)
    writer = csv.writer(response)
    writer.writerow(['Date', 'Vehicle', 'Litres', 'Cost (INR)', 'Odometer (km)', 'Full Tank'])
    for entry in qs:
        writer.writerow([
            entry.date,
            f'{entry.vehicle.brand} {entry.vehicle.name}',
            entry.litres,
            entry.cost,
            entry.odometer,
            'Yes' if entry.full_tank else 'No',
        ])
    return response


@login_required
def export_service(request):
    """Export service history as CSV."""
    vehicle_id = request.GET.get('vehicle')
    qs = (ServiceRecord.objects
          .filter(vehicle__user=request.user)
          .select_related('vehicle')
          .order_by('vehicle__id', '-date'))

    if vehicle_id:
        vehicle = _get_vehicle(request.user, vehicle_id)
        qs = qs.filter(vehicle=vehicle)
        filename = f'service_{vehicle.brand}_{vehicle.name}_{date.today()}.csv'.replace(' ', '_')
    else:
        filename = f'service_all_{date.today()}.csv'

    response = _csv_response(filename)
    writer = csv.writer(response)
    writer.writerow(['Date', 'Vehicle', 'Service Type', 'Cost (INR)', 'Odometer (km)', 'Notes'])
    for s in qs:
        writer.writerow([
            s.date,
            f'{s.vehicle.brand} {s.vehicle.name}',
            s.service_type,
            s.cost,
            s.odometer if s.odometer else '',
            s.description,
        ])
    return response


@login_required
def export_mileage(request):
    """Export mileage segments as CSV."""
    vehicle_id = request.GET.get('vehicle')
    if not vehicle_id:
        messages.error(request, 'Select a vehicle before exporting mileage.')
        return redirect('mileage')

    vehicle = _get_vehicle(request.user, vehicle_id)
    entries = list(FuelEntry.objects.filter(vehicle=vehicle).order_by('date', 'id'))
    segs    = _compute_mileage_segments(entries, vehicle)

    filename = f'mileage_{vehicle.brand}_{vehicle.name}_{date.today()}.csv'.replace(' ', '_')
    response = _csv_response(filename)
    writer = csv.writer(response)
    writer.writerow(['Date', 'Vehicle', 'Distance (km)', 'Fuel Used (L)', 'Mileage (km/L)'])
    for s in segs:
        writer.writerow([
            s['date'],
            f'{vehicle.brand} {vehicle.name}',
            s['distance'],
            s['fuel'],
            s['mileage'],
        ])
    return response
