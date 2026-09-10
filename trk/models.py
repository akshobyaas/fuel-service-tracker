import secrets

from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import User
from django.utils import timezone
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


# ─────────────────────────────────────────
# UserProfile  — Phase 6 Profile Customization
# ─────────────────────────────────────────

UNIT_DISTANCE_CHOICES = [
    ('km', 'Kilometres (km)'),
    ('mi', 'Miles (mi)'),
]

UNIT_VOLUME_CHOICES = [
    ('L', 'Litres (L)'),
    ('gal', 'Gallons (gal)'),
]

THEME_CHOICES = [
    ('dark',  'Dark'),
    ('light', 'Light'),
    ('auto',  'Auto (system)'),
]


class UserProfile(models.Model):
    user             = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    display_name     = models.CharField(max_length=100, blank=True, default='')
    bio              = models.TextField(max_length=300, blank=True, default='')
    dob              = models.DateField(null=True, blank=True)
    avatar           = models.ImageField(upload_to='avatars/', null=True, blank=True)
    unit_distance    = models.CharField(max_length=5,  choices=UNIT_DISTANCE_CHOICES, default='km')
    unit_volume      = models.CharField(max_length=5,  choices=UNIT_VOLUME_CHOICES,   default='L')
    theme_preference = models.CharField(max_length=10, choices=THEME_CHOICES,          default='dark')
    notify_service   = models.BooleanField(default=True,  help_text='Remind about upcoming service')
    notify_docs      = models.BooleanField(default=True,  help_text='Remind about expiring documents')
    notify_fuel      = models.BooleanField(default=False, help_text='Weekly fuel summary')
    email_verified   = models.BooleanField(default=False, help_text='Verified via OTP at registration')
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'User Profile'

    def __str__(self):
        return f'Profile of {self.user.username}'

    @property
    def name_display(self):
        return self.display_name or self.user.username


class Feedback(models.Model):
    user       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    category   = models.CharField(max_length=50, choices=[
        ('bug',        'Bug Report'),
        ('feature',    'Feature Request'),
        ('ui',         'UI / Design'),
        ('general',    'General Feedback'),
    ], default='general')
    message    = models.TextField(max_length=2000)
    submitted_at = models.DateTimeField(auto_now_add=True)
    user_agent = models.CharField(max_length=300, blank=True, default='')

    class Meta:
        verbose_name = 'Feedback'
        verbose_name_plural = 'Feedback Submissions'
        ordering = ['-submitted_at']

    def __str__(self):
        return f'{self.category} by {self.user} at {self.submitted_at:%Y-%m-%d}'


# ─────────────────────────────────────────
# OTPCode — email-based one-time codes for
# registration verification and OTP login
# ─────────────────────────────────────────

class OTPCode(models.Model):
    PURPOSE_CHOICES = [
        ('register', 'Register'),
        ('login', 'Login'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_codes')
    purpose    = models.CharField(max_length=10, choices=PURPOSE_CHOICES)
    code_hash  = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts   = models.PositiveSmallIntegerField(default=0)
    is_used    = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'OTP Code'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.purpose} OTP for {self.user.username} ({"used" if self.is_used else "active"})'

    @staticmethod
    def generate_code():
        """Cryptographically-random 6-digit numeric code."""
        return f'{secrets.randbelow(1_000_000):06d}'

    def set_code(self, raw_code):
        # Hashed the same way passwords are — never store the raw code.
        self.code_hash = make_password(raw_code)

    def check_code(self, raw_code):
        return check_password(raw_code, self.code_hash)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at
