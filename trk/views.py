from django.shortcuts import render, redirect, get_object_or_404
from .models import Vehicle
from .models import FuelEntry
from .models import ServiceRecord
from datetime import date



def home(request):

    vehicles = Vehicle.objects.all()

    selected_vehicle = None
    total_fuel_entries = 0
    total_fuel_cost = 0
    total_services = 0
    last_service = None
    previous_mileage = "NIL"

    # Determine selected vehicle
    if request.method == "POST":
        vehicle_id = vehicle_id = request.POST.get('vehicle')
        selected_vehicle = get_object_or_404(Vehicle, id=vehicle_id)

    else:
        # Default = most recently added vehicle
        selected_vehicle = Vehicle.objects.order_by('-id').first()

    if selected_vehicle:

        fuel_entries = FuelEntry.objects.filter(vehicle=selected_vehicle).order_by('date')
        services = ServiceRecord.objects.filter(vehicle=selected_vehicle)

        total_fuel_entries = fuel_entries.count()
        total_services = services.count()

        for f in fuel_entries:
            total_fuel_cost += f.cost

        last_service = services.order_by('-date').first()

        # Previous fill mileage
        if fuel_entries.count() >= 2:

            last = fuel_entries.last()
            previous = fuel_entries.reverse()[1]

            distance = last.odometer - previous.odometer
            if last.litres > 0:
                previous_mileage = round(distance / last.litres, 2)

    context = {
        'vehicles': vehicles,
        'selected_vehicle': selected_vehicle,
        'total_fuel_entries': total_fuel_entries,
        'total_fuel_cost': total_fuel_cost,
        'total_services': total_services,
        'last_service': last_service,
        'previous_mileage': previous_mileage
    }

    return render(request, 'trk/home.html', context)

def vehicles(request):
    data = Vehicle.objects.all()
    return render(request, 'trk/vehicles.html', {'vehicles': data})


def add_vehicle(request):

    if request.method == "POST":

        brand = request.POST.get('brand')
        name = request.POST.get('name')
        year = request.POST.get('year')
        fuel_type = request.POST.get('fuel_type')

        if brand and name and year and fuel_type:

            Vehicle.objects.create(
                brand=brand,
                name=name,
                year=year,
                fuel_type=fuel_type
            )

            return redirect('vehicles')

    return render(request, 'trk/add_vehicle.html')


def fuel_entry(request):

    vehicles = Vehicle.objects.all()
    context = {}

    if request.method == "POST":

        vehicle_id = request.POST.get('vehicle')
        litres = request.POST.get('litres')
        cost = request.POST.get('cost')
        odometer = request.POST.get('odometer')
        date_input = request.POST.get('date')
        full_tank = True if request.POST.get('full_tank') else False
        context["today"] = date.today()

        vehicle = get_object_or_404(Vehicle, id=vehicle_id)

        if litres and cost and odometer and date_input:

            FuelEntry.objects.create(
                vehicle=vehicle,
                litres=litres,
                cost=cost,
                odometer=odometer,
                date=date_input,
                full_tank=full_tank
            )

            return redirect('home')

    return render(request, 'trk/fuel_entry.html', {'vehicles': vehicles})

def fuel_history(request):

    vehicles = Vehicle.objects.all()
    fuel_data = []
    selected_vehicle = None

    if request.method == "POST":

        vehicle_id = vehicle_id = request.POST.get('vehicle')
        selected_vehicle = get_object_or_404(Vehicle, id=vehicle_id)

        fuel_data = FuelEntry.objects.filter(
            vehicle=selected_vehicle
        ).order_by('-date')

    return render(request, 'trk/fuel_history.html', {
        'vehicles': vehicles,
        'fuel': fuel_data,
        'selected_vehicle': selected_vehicle
    })


def service_entry(request):

    vehicles = Vehicle.objects.all()

    if request.method == "POST":

        vehicle_id = vehicle_id = request.POST.get('vehicle')
        service_type = request.POST['service_type']
        cost = request.POST['cost']
        date = request.POST['date']
        odometer = request.POST.get('odometer')
        description = request.POST['description']

        vehicle = get_object_or_404(Vehicle, id=vehicle_id)

        ServiceRecord.objects.create(
            vehicle=vehicle,
            service_type=service_type,
            cost=cost,
            date=date,
            description=description,
            odometer=odometer
        )

        return redirect('/')

    return render(request, 'trk/service_entry.html', {'vehicles': vehicles})

def mileage_report(request):

    vehicles = Vehicle.objects.all()
    mileage_list = []
    selected_vehicle = None

    if request.method == "POST":

        vehicle_id = request.POST.get('vehicle')

        if vehicle_id:
            selected_vehicle = get_object_or_404(Vehicle, id=vehicle_id)

            fuel_entries = FuelEntry.objects.filter(
                vehicle=selected_vehicle
            ).order_by('date')

            start_odometer = None
            fuel_sum = 0
            tracking_started = False

            for entry in fuel_entries:

                if entry.full_tank and not tracking_started:
                    # First full tank → start tracking
                    start_odometer = entry.odometer
                    tracking_started = True
                    fuel_sum = 0
                    continue

                if tracking_started:
                    fuel_sum += entry.litres

                if entry.full_tank and tracking_started:

                    distance = entry.odometer - start_odometer

                    if distance > 0 and fuel_sum > 0:

                        mileage = round(distance / fuel_sum, 2)

                        mileage_list.append({
                            'vehicle': entry.vehicle,
                            'distance': round(distance,1),
                            'fuel': round(fuel_sum,2),
                            'mileage': mileage,
                            'date': entry.date
                        })

                    start_odometer = entry.odometer
                    fuel_sum = 0
                    
    return render(request, 'trk/mileage.html', {
    'vehicles': vehicles,
    'data': mileage_list,
    'selected_vehicle': selected_vehicle
})

def service_history(request):

    data = ServiceRecord.objects.all().order_by('-date')

    return render(request, 'trk/service_history.html', {'services': data})

def delete_fuel(request, id):

    entry = get_object_or_404(FuelEntry, id=id)
    entry.delete()

    return redirect('fuel_history')

def edit_fuel(request, id):

    entry = get_object_or_404(FuelEntry, id=id)
    vehicles = Vehicle.objects.all()

    if request.method == "POST":

        entry.vehicle_id = vehicle_id = request.POST.get('vehicle')
        entry.litres = request.POST['litres']
        entry.cost = request.POST['cost']
        entry.odometer = request.POST['odometer']
        entry.date = request.POST['date']

        entry.save()

        return redirect('fuel_history')

    return render(request, 'trk/edit_fuel.html', {
        'entry': entry,
        'vehicles': vehicles
    })
    
def delete_vehicle(request, id):

    vehicle = get_object_or_404(Vehicle, id=id)
    vehicle.delete()

    return redirect('vehicles')

def edit_vehicle(request, id):

    vehicle = get_object_or_404(Vehicle, id=id)

    if request.method == "POST":

        vehicle.brand = request.POST.get('brand')
        vehicle.name = request.POST.get('name')
        vehicle.year = request.POST.get('year')
        vehicle.fuel_type = request.POST.get('fuel_type')

        vehicle.save()

        return redirect('vehicles')

    return render(request, 'trk/edit_vehicle.html', {'vehicle': vehicle})

def delete_service(request, id):

    record = get_object_or_404(ServiceRecord, id=id)
    record.delete()

    return redirect('service_history')

def edit_service(request, id):

    record = get_object_or_404(ServiceRecord, id=id)
    vehicles = Vehicle.objects.all()

    if request.method == "POST":

        record.vehicle_id = vehicle_id = request.POST.get('vehicle')
        record.service_type = request.POST['service_type']
        record.cost = request.POST['cost']
        record.date = request.POST['date']
        record.description = request.POST['description']

        record.save()

        return redirect('service_history')

    return render(request, 'trk/edit_service.html', {
        'record': record,
        'vehicles': vehicles
    })