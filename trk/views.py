from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail
from django.core.cache import cache
from django.db.models import Sum, Prefetch, Q
from django.http import JsonResponse, FileResponse, Http404
from django.core.files.storage import default_storage
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Vehicle, FuelEntry, ServiceRecord, Document, OTPCode
from .forms import (
    VehicleForm, FuelEntryForm, ServiceRecordForm, DocumentForm,
    RegisterForm, LoginForm, OTPRequestForm, OTPVerifyForm,
)
from datetime import date, timedelta
from django.utils import timezone
from collections import defaultdict
import os
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────
# Auth
# ─────────────────────────────────────────

class OTPSendError(Exception):
    """Raised when an OTP email could not be delivered (bad SMTP creds,
    network hiccup, etc). Callers should show a friendly message instead of
    letting this bubble up into a 500 page."""
    pass


def _issue_otp(user, purpose):
    """
    Create and email a fresh OTP for (user, purpose), honouring the resend
    cooldown. Returns (otp, None) on success, or (None, remaining_wait) if
    the caller needs to wait before another code can be sent. Raises
    OTPSendError if the email backend fails to deliver — nothing is saved in
    that case, so the cooldown isn't wasted on a code the user never got.
    """
    cooldown = timedelta(seconds=settings.OTP_RESEND_COOLDOWN_SECONDS)
    recent = (OTPCode.objects
              .filter(user=user, purpose=purpose, is_used=False)
              .order_by('-created_at')
              .first())
    if recent and timezone.now() - recent.created_at < cooldown:
        return None, cooldown - (timezone.now() - recent.created_at)

    code = OTPCode.generate_code()
    otp = OTPCode(
        user=user, purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
    )
    otp.set_code(code)

    verb = 'verify your email' if purpose == 'register' else 'sign in'
    try:
        send_mail(
            subject=f'Your PitLog code: {code}',
            message=(
                f'Use this code to {verb}: {code}\n\n'
                f'It expires in {settings.OTP_EXPIRY_MINUTES} minutes.\n\n'
                "If you didn't request this, you can safely ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Failed to send OTP email to %s (purpose=%s)', user.email, purpose)
        raise OTPSendError()

    # Only persist the code once we know it was actually sent — otherwise a
    # failed send would still count against the resend cooldown.
    otp.save()
    return otp, None


def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        # Reclaim a never-verified registration attempt so retrying with the
        # same username/email doesn't hit "already exists" forever. Only a
        # pending account that is either *this browser's own* attempt or has
        # been abandoned past the OTP expiry may be reclaimed — otherwise a
        # stranger could repeatedly wipe someone else's sign-up mid-flow just
        # by submitting their username or email.
        stale_username = (request.POST.get('username') or '').strip()
        stale_email = (request.POST.get('email') or '').strip()
        if stale_username or stale_email:
            match = Q()
            if stale_username:
                match |= Q(username=stale_username)
            if stale_email:
                match |= Q(email=stale_email)
            abandoned_before = timezone.now() - timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
            reclaimable = Q(date_joined__lt=abandoned_before)
            own_attempt_id = request.session.get('otp_user_id')
            if own_attempt_id:
                reclaimable |= Q(id=own_attempt_id)
            User.objects.filter(match, reclaimable, is_active=False).delete()

        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # activated only once the OTP is verified
            user.save()
            try:
                _issue_otp(user, 'register')
            except OTPSendError:
                messages.error(
                    request,
                    "Your account was created, but we couldn't send the verification "
                    "email right now. Please try registering again in a moment."
                )
                return redirect('register')
            request.session['otp_user_id'] = user.id
            request.session['otp_purpose'] = 'register'
            messages.info(request, f'We emailed a 6-digit code to {user.email}. Enter it below to finish creating your account.')
            return redirect('verify_otp')
    else:
        form = RegisterForm()
    return render(request, 'trk/auth/register.html', {'form': form})


LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60  # 15 minutes


def _client_ip(request):
    # The *left-most* X-Forwarded-For entry is whatever the client chose to
    # send, so trusting it lets an attacker pick a fresh "IP" per request and
    # walk straight past the login throttle. The *right-most* entry is the one
    # appended by our own hosting proxy (Vercel/Render), which the client
    # cannot forge.
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[-1].strip()
    return request.META.get('REMOTE_ADDR', '')


def _login_throttle_key(request, identifier):
    # Keyed by IP + identifier together: an attacker spraying one password
    # across many accounts from one IP gets throttled without a stranger
    # being able to lock a specific victim out from a different IP.
    return f'login_fail:{_client_ip(request)}:{(identifier or "").strip().lower()}'


def _login_is_throttled(request, identifier):
    return cache.get(_login_throttle_key(request, identifier), 0) >= LOGIN_ATTEMPT_LIMIT


def _register_login_failure(request, identifier):
    key = _login_throttle_key(request, identifier)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, LOGIN_ATTEMPT_WINDOW_SECONDS)


def _clear_login_failures(request, identifier):
    cache.delete(_login_throttle_key(request, identifier))


def _safe_next_url(request):
    """Where to send the user after login. ?next= is attacker-controllable
    (e.g. a phishing link to /login/?next=https://evil.example), so only
    same-site paths are honoured; anything else falls back to the dashboard."""
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return next_url
    return 'home'


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    # Defaults for a plain GET; either gets overwritten below on POST.
    form = LoginForm(request)
    otp_form = OTPRequestForm()

    if request.method == 'POST':
        if request.POST.get('mode') == 'otp_request':
            otp_form = OTPRequestForm(request.POST)
            if otp_form.is_valid():
                identifier = otp_form.cleaned_data['identifier'].strip()
                user = User.objects.filter(
                    Q(username__iexact=identifier) | Q(email__iexact=identifier),
                    is_active=True,
                ).first()
                if not user:
                    messages.error(request, 'No verified account found with that username or email.')
                    return redirect('login')
                try:
                    otp, wait = _issue_otp(user, 'login')
                except OTPSendError:
                    messages.error(request, "We couldn't send the code right now. Please try again shortly, or sign in with your password instead.")
                    return redirect('login')
                if otp is None:
                    messages.error(request, f'Please wait about {int(wait.total_seconds())}s before requesting another code.')
                    return redirect('login')
                request.session['otp_user_id'] = user.id
                request.session['otp_purpose'] = 'login'
                messages.success(request, f'We emailed a 6-digit code to {user.email}.')
                return redirect('verify_otp')
            # else: otp_form has errors — fall through and re-render with them
        else:
            identifier = request.POST.get('username', '')
            if _login_is_throttled(request, identifier):
                messages.error(
                    request,
                    'Too many failed sign-in attempts. Please wait 15 minutes and try '
                    'again, or sign in with an emailed code instead.'
                )
                form = LoginForm(request)
            else:
                form = LoginForm(request, data=request.POST)
                if form.is_valid():
                    user = form.get_user()
                    login(request, user)
                    _clear_login_failures(request, identifier)
                    messages.success(request, f'Welcome back, {user.username}!')
                    return redirect(_safe_next_url(request))
                else:
                    _register_login_failure(request, identifier)
                # else: form has errors — fall through and re-render with them

    return render(request, 'trk/auth/login.html', {'form': form, 'otp_form': otp_form})


def verify_otp_view(request):
    user_id = request.session.get('otp_user_id')
    purpose = request.session.get('otp_purpose')
    if not user_id or purpose not in ('register', 'login'):
        messages.error(request, 'Nothing to verify — please start again.')
        return redirect('register' if purpose == 'register' else 'login')

    user = get_object_or_404(User, id=user_id)
    form = OTPVerifyForm()

    if request.method == 'POST':
        if 'resend' in request.POST:
            try:
                otp, wait = _issue_otp(user, purpose)
            except OTPSendError:
                messages.error(request, "We couldn't send a new code right now. Please try again shortly.")
                return redirect('verify_otp')
            if otp is None:
                messages.error(request, f'Please wait about {int(wait.total_seconds())}s before requesting another code.')
            else:
                messages.success(request, 'A new code has been sent.')
            return redirect('verify_otp')

        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            otp = (OTPCode.objects
                   .filter(user=user, purpose=purpose, is_used=False)
                   .order_by('-created_at')
                   .first())
            if not otp or otp.is_expired:
                form.add_error('code', 'That code has expired. Request a new one below.')
            elif otp.attempts >= settings.OTP_MAX_ATTEMPTS:
                form.add_error('code', 'Too many incorrect attempts. Request a new code below.')
            elif not otp.check_code(code):
                otp.attempts += 1
                otp.save(update_fields=['attempts'])
                form.add_error('code', 'Incorrect code.')
            else:
                otp.is_used = True
                otp.save(update_fields=['is_used'])
                if purpose == 'register':
                    user.is_active = True
                    user.save(update_fields=['is_active'])
                    profile = _get_or_create_profile(user)
                    profile.email_verified = True
                    profile.save(update_fields=['email_verified'])
                    messages.success(request, f'Welcome, {user.username}! Your account is verified.')
                else:
                    messages.success(request, f'Welcome back, {user.username}!')
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                if purpose == 'login':
                    # Proves ownership of the account's email just as well as a
                    # password would — let them set a new password without
                    # knowing the old one for a short window, in case that's
                    # why they used OTP login in the first place. Set after
                    # login() since it can rotate/flush session state.
                    request.session['recent_otp_login_at'] = timezone.now().timestamp()
                del request.session['otp_user_id']
                del request.session['otp_purpose']
                return redirect('home')

    return render(request, 'trk/auth/verify_otp.html', {
        'form': form, 'purpose': purpose, 'email': user.email,
    })


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
    try:
        vehicle_id = int(vehicle_id)
    except (TypeError, ValueError):
        # Non-numeric / missing id would otherwise hit Django's ORM as an
        # uncaught ValueError (get_object_or_404 only catches DoesNotExist),
        # turning a bad request into a 500. Treat it as "not found" instead.
        raise Http404('Vehicle not found.')
    return get_object_or_404(Vehicle, id=vehicle_id, user=user)


def _validate_odometer_order(base_qs, date_field, odo_field, new_date, new_odo, exclude_id=None):
    """
    Keep odometer readings non-decreasing in *chronological* order.

    The previous implementation compared a new reading against whichever row
    had the highest primary key (i.e. insertion order). That breaks as soon
    as someone backfills an older entry after already having newer ones —
    it either rejects perfectly valid historical data, or lets a genuinely
    out-of-order reading slip through depending on insertion order, silently
    corrupting the mileage calculations (which walk entries by date).

    This compares against the nearest neighbours by date instead: the new
    reading must be >= the closest earlier (or same-day) entry and
    <= the closest later entry. Returns an error message, or None if valid.
    """
    qs = base_qs
    if exclude_id is not None:
        qs = qs.exclude(id=exclude_id)

    prev = qs.filter(**{f'{date_field}__lte': new_date}).order_by(f'-{date_field}', '-id').first()
    if prev and new_odo < getattr(prev, odo_field):
        return (f'Must be ≥ the reading from {getattr(prev, date_field):%d %b %Y} '
                f'({getattr(prev, odo_field)} km).')

    nxt = qs.filter(**{f'{date_field}__gt': new_date}).order_by(date_field, 'id').first()
    if nxt and new_odo > getattr(nxt, odo_field):
        return (f'Must be ≤ the reading from {getattr(nxt, date_field):%d %b %Y} '
                f'({getattr(nxt, odo_field)} km).')

    return None


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

def home(request):
    # Public landing page for signed-out visitors; the dashboard below is
    # only for authenticated users. Kept on the same view/URL (rather than a
    # login_required redirect) so `/` works as a real marketing entry point.
    if not request.user.is_authenticated:
        return render(request, 'trk/landing.html')

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
    monthly_chart_data = {'labels': [], 'values': []}
    mileage_chart_data = {'labels': [], 'values': []}
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
        monthly_chart_data = {'labels': list(monthly.keys()), 'values': [round(v,2) for v in monthly.values()]}
        mileage_chart_data = {'labels': [s['date'].strftime('%Y-%m-%d') for s in segs], 'values': [s['mileage'] for s in segs]}

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
            error = _validate_odometer_order(
                FuelEntry.objects.filter(vehicle=vehicle), 'date', 'odometer',
                form.cleaned_data['date'], odometer,
            )
            if error:
                form.add_error('odometer', error)
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
            error = _validate_odometer_order(
                FuelEntry.objects.filter(vehicle=vehicle), 'date', 'odometer',
                form.cleaned_data['date'], odometer, exclude_id=entry.id,
            )
            if error:
                form.add_error('odometer', error)
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
                error = _validate_odometer_order(
                    ServiceRecord.objects.filter(vehicle=vehicle, odometer__isnull=False),
                    'date', 'odometer', form.cleaned_data['date'], odometer,
                )
                if error:
                    form.add_error('odometer', error)
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
    service_chart_data = {'labels': list(svc_by_vehicle.keys()), 'values': list(svc_by_vehicle.values())}
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
            vehicle  = form.cleaned_data['vehicle']
            odometer = form.cleaned_data.get('odometer')
            error = None
            if odometer:
                error = _validate_odometer_order(
                    ServiceRecord.objects.filter(vehicle=vehicle, odometer__isnull=False),
                    'date', 'odometer', form.cleaned_data['date'], odometer, exclude_id=record.id,
                )
            if error:
                form.add_error('odometer', error)
            else:
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
    mileage_chart_data = {'labels': [], 'values': [], 'avg': None}
    cost_per_km_data = {'labels': [], 'values': []}
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
            mileage_chart_data = {
                'labels': [m['date'].strftime('%d %b %Y') for m in mileage_list],
                'values': effs,
                'avg': avg_mileage,
            }
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
            cost_per_km_data = {'labels': [s['date'] for s in cpkm_segs], 'values': [s['cpkm'] for s in cpkm_segs]}

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


# profile view moved to Phase 6 section below


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


def robots_txt(request):
    # Everything except the public landing/legal pages requires login anyway,
    # so there's nothing else behind it worth a crawler's time.
    lines = [
        'User-agent: *',
        'Allow: /$',
        'Allow: /privacy/$',
        'Allow: /terms/$',
        'Disallow: /',
        '',
        f'Sitemap: {request.scheme}://{request.get_host()}/sitemap.xml',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain')


def sitemap_xml(request):
    # Hand-rolled to match robots_txt above rather than pulling in
    # django.contrib.sitemaps for three public URLs.
    base = f'{request.scheme}://{request.get_host()}'
    urls = [
        (base + '/',         '1.0'),
        (base + '/privacy/', '0.3'),
        (base + '/terms/',   '0.3'),
    ]
    entries = '\n'.join(
        f'  <url><loc>{loc}</loc><priority>{priority}</priority></url>'
        for loc, priority in urls
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'{entries}\n'
        '</urlset>'
    )
    return HttpResponse(xml, content_type='application/xml')


def privacy_view(request):
    return render(request, 'trk/privacy.html', {
        'support_email': getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None),
    })


def terms_view(request):
    return render(request, 'trk/terms.html', {
        'support_email': getattr(settings, 'DEFAULT_FROM_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None),
    })


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


# ─────────────────────────────────────────
# Phase 6 — Profile Customization
# ─────────────────────────────────────────

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from .models import UserProfile
from .forms import UserProfileForm, FeedbackForm, AccountEmailForm


def _get_or_create_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


@login_required
def profile_edit(request):
    """Edit personal info + avatar + units + theme + notifications in one form."""
    profile = _get_or_create_profile(request.user)
    email_form = AccountEmailForm(instance=request.user)

    if request.method == 'POST':
        form       = UserProfileForm(request.POST, request.FILES, instance=profile)
        email_form = AccountEmailForm(request.POST, instance=request.user)
        if form.is_valid() and email_form.is_valid():
            email_form.save()
            form.save()
            messages.success(request, 'Profile updated successfully.')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=profile)

    return render(request, 'trk/profile_edit.html', {
        'form': form,
        'email_form': email_form,
        'profile': profile,
    })


RECENT_OTP_LOGIN_WINDOW_SECONDS = 900  # 15 minutes


def _otp_login_is_recent(request):
    ts = request.session.get('recent_otp_login_at')
    return bool(ts) and (timezone.now().timestamp() - ts) < RECENT_OTP_LOGIN_WINDOW_SECONDS


@login_required
def profile_password(request):
    """
    Change password. If the user is here shortly after signing in with an
    emailed OTP (rather than a password), that already proves they own the
    account, so let them set a new password without knowing the old one —
    otherwise anyone who forgets their password would be stuck using OTP
    login forever with no way to actually set a new password.
    """
    otp_recent = _otp_login_is_recent(request)
    FormClass = SetPasswordForm if otp_recent else PasswordChangeForm
    form_args = (request.user,)

    if request.method == 'POST':
        form = FormClass(*form_args, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # keep user logged in
            request.session.pop('recent_otp_login_at', None)  # one-time use
            messages.success(request, 'Password changed successfully.')
            return redirect('profile')
    else:
        form = FormClass(*form_args)
    # Apply form-control class to all fields
    for field in form.fields.values():
        field.widget.attrs.setdefault('class', 'form-control')
    return render(request, 'trk/profile_password.html', {
        'form': form, 'otp_recent': otp_recent,
    })


@login_required
def profile_feedback(request):
    """Submit feedback to developer."""
    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            fb = form.save(commit=False)
            fb.user       = request.user
            fb.user_agent = request.META.get('HTTP_USER_AGENT', '')[:300]
            fb.save()
            messages.success(request, 'Thank you for your feedback!')
            return redirect('profile')
    else:
        form = FeedbackForm()
    return render(request, 'trk/profile_feedback.html', {'form': form})


# ── Updated main profile view (now includes profile data) ──

@login_required
def profile(request):
    profile_obj    = _get_or_create_profile(request.user)
    user_vehicles  = _user_vehicles(request.user)
    total_vehicles = user_vehicles.count()
    total_fuel     = FuelEntry.objects.filter(vehicle__user=request.user).count()
    total_services = ServiceRecord.objects.filter(vehicle__user=request.user).count()
    total_docs     = Document.objects.filter(vehicle__user=request.user).count()
    total_cost     = FuelEntry.objects.filter(vehicle__user=request.user).aggregate(t=Sum('cost'))['t'] or 0
    return render(request, 'trk/profile.html', {
        'profile':         profile_obj,
        'total_vehicles':  total_vehicles,
        'total_fuel':      total_fuel,
        'total_services':  total_services,
        'total_docs':      total_docs,
        'total_cost':      round(total_cost, 2),
    })
