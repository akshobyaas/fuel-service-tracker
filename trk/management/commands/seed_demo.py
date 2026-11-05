"""
Management command to seed realistic demo data for PitLog.

Usage:
    python manage.py seed_demo --username demo --password demo1234

Creates:
  - 1 demo user (or uses existing)
  - 2 vehicles (Royal Enfield Classic 350 + Maruti Swift)
  - 6 months of fuel entries per vehicle
  - Several service records
  - 2 sample documents (no actual files — metadata only)
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from trk.models import Vehicle, FuelEntry, ServiceRecord, Document, UserProfile
from datetime import date, timedelta


def _date_ago(days):
    return date.today() - timedelta(days=days)


class Command(BaseCommand):
    help = 'Seed demo data for PitLog interviews and demonstrations'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='demo',    help='Demo username (default: demo)')
        parser.add_argument('--password', default='demo1234', help='Demo password (default: demo1234)')
        parser.add_argument('--clear',    action='store_true', help='Delete existing data for this user first')

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']

        # ── User ──
        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_password(password)
            user.first_name = 'Demo'
            user.last_name  = 'User'
            user.email      = f'{username}@pitlog.app'
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Created user: {username}'))
        else:
            self.stdout.write(f'Using existing user: {username}')

        # Ensure profile exists
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.display_name = 'Demo User'
        profile.bio = 'PitLog demo account. Tracks a Royal Enfield and a Swift.'
        profile.email_verified = True  # seeded account skips the OTP registration flow
        profile.save()

        if options['clear']:
            Vehicle.objects.filter(user=user).delete()
            self.stdout.write(self.style.WARNING('Cleared existing vehicle data.'))

        # ── Vehicle 1: Royal Enfield Classic 350 ──
        bike, _ = Vehicle.objects.get_or_create(
            user=user, brand='Royal Enfield', name='Classic 350',
            defaults={'year': 2021, 'fuel_type': 'Petrol'}
        )
        self.stdout.write(f'Vehicle: {bike}')

        # ── Vehicle 2: Maruti Swift ──
        car, _ = Vehicle.objects.get_or_create(
            user=user, brand='Maruti', name='Swift',
            defaults={'year': 2020, 'fuel_type': 'Petrol'}
        )
        self.stdout.write(f'Vehicle: {car}')

        # ── Fuel entries: Bike (RE Classic 350) ──
        # ~35 km/L, fill-ups every ~14 days, tank ~13L
        if not FuelEntry.objects.filter(vehicle=bike).exists():
            bike_entries = [
                # (days_ago, litres, cost, odometer, full_tank)
                (175, 13.0, 1378, 12400, True),
                (161, 12.5, 1325, 12845, True),
                (148,  4.0,  424, 13020, False),
                (145, 11.0, 1166, 13390, True),
                (131, 12.8, 1357, 13838, True),
                (117, 13.2, 1399, 14300, True),
                (103, 12.0, 1272, 14718, True),
                ( 89, 13.5, 1431, 15190, True),
                ( 75, 11.5, 1219, 15591, True),
                ( 61, 13.0, 1378, 16046, True),
                ( 47, 12.5, 1325, 16484, True),
                ( 33, 13.8, 1463, 16967, True),
                ( 19, 12.0, 1272, 17385, True),
                (  5, 13.2, 1399, 17847, True),
            ]
            for days, litres, cost, odo, full in bike_entries:
                FuelEntry.objects.create(
                    vehicle=bike, litres=litres, cost=cost,
                    odometer=odo, date=_date_ago(days), full_tank=full
                )
            self.stdout.write(self.style.SUCCESS(f'  Added {len(bike_entries)} fuel entries for {bike}'))

        # ── Fuel entries: Car (Swift) ──
        # ~18 km/L city, fill-ups every ~20 days, tank ~37L
        if not FuelEntry.objects.filter(vehicle=car).exists():
            car_entries = [
                (180, 35.0, 3710, 28500, True),
                (160, 36.5, 3869, 29140, True),
                (141, 12.0, 1272, 29420, False),
                (138, 30.0, 3180, 29890, True),
                (118, 37.0, 3922, 30540, True),
                ( 98, 34.5, 3657, 31162, True),
                ( 78, 36.0, 3816, 31810, True),
                ( 58, 35.5, 3763, 32449, True),
                ( 38, 37.5, 3975, 33125, True),
                ( 18, 34.0, 3604, 33737, True),
                (  4, 36.0, 3816, 34390, True),
            ]
            for days, litres, cost, odo, full in car_entries:
                FuelEntry.objects.create(
                    vehicle=car, litres=litres, cost=cost,
                    odometer=odo, date=_date_ago(days), full_tank=full
                )
            self.stdout.write(self.style.SUCCESS(f'  Added {len(car_entries)} fuel entries for {car}'))

        # ── Service records: Bike ──
        if not ServiceRecord.objects.filter(vehicle=bike).exists():
            bike_services = [
                (170, 'Engine Oil Change',    12400, 850.0,  'Switched to 10W-40 semi-synthetic.'),
                (120, 'Chain Lubrication',    14200, 150.0,  'Cleaned and lubed chain.'),
                ( 90, 'Engine Oil Change',    15000, 850.0,  'Routine 3000 km oil change.'),
                ( 60, 'Tyre Pressure Check',  15900,  50.0,  'All tyres inflated to spec.'),
                ( 30, 'Engine Oil Change',    16800, 850.0,  'Routine service.'),
                ( 10, 'General Inspection',   17700, 300.0,  'Brake pads, cables, chain tension checked.'),
            ]
            for days, stype, odo, cost, desc in bike_services:
                ServiceRecord.objects.create(
                    vehicle=bike, service_type=stype, odometer=odo,
                    cost=cost, date=_date_ago(days), description=desc
                )
            self.stdout.write(self.style.SUCCESS(f'  Added {len(bike_services)} service records for {bike}'))

        # ── Service records: Car ──
        if not ServiceRecord.objects.filter(vehicle=car).exists():
            car_services = [
                (165, 'Engine Oil Change',    28600, 2200.0, 'Full synthetic 5W-30. Filter replaced.'),
                (110, 'Tyre Rotation',        29800, 400.0,  'All four tyres rotated.'),
                ( 70, 'Engine Oil Change',    31000, 2200.0, 'Routine 5000 km service.'),
                ( 20, 'AC Service',           33500, 1800.0, 'Refrigerant topped up, filter cleaned.'),
            ]
            for days, stype, odo, cost, desc in car_services:
                ServiceRecord.objects.create(
                    vehicle=car, service_type=stype, odometer=odo,
                    cost=cost, date=_date_ago(days), description=desc
                )
            self.stdout.write(self.style.SUCCESS(f'  Added {len(car_services)} service records for {car}'))

        # ── Documents (metadata only, no actual files) ──
        if not Document.objects.filter(vehicle=bike).exists():
            Document.objects.create(
                vehicle=bike, doc_type='Insurance', title='RE Classic 350 — Comprehensive Insurance',
                file='', expiry_date=date.today() + timedelta(days=45),
                note='New India Assurance. Renew before expiry.'
            )
            Document.objects.create(
                vehicle=bike, doc_type='PUC', title='PUC Certificate',
                file='', expiry_date=date.today() + timedelta(days=12),
                note='Near expiry — renew at nearest emission centre.'
            )

        if not Document.objects.filter(vehicle=car).exists():
            Document.objects.create(
                vehicle=car, doc_type='Insurance', title='Swift — Comprehensive Insurance',
                file='', expiry_date=date.today() + timedelta(days=180),
                note='HDFC Ergo. Valid for another 6 months.'
            )
            Document.objects.create(
                vehicle=car, doc_type='RC Book', title='Registration Certificate',
                file='', expiry_date=None,
                note='Original RC book. Valid for 15 years from registration.'
            )

        self.stdout.write(self.style.SUCCESS('\nDemo data seeded successfully!'))
        self.stdout.write(f'  Login at /login/ with username="{username}" password="{password}"')
        self.stdout.write( '  Dashboard will show charts, insights, and expiring documents.')
