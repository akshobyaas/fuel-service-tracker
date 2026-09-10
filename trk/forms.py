from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Vehicle, FuelEntry, ServiceRecord, Document, FUEL_TYPE_CHOICES
from datetime import date

ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'webp'}
MAX_FILE_MB = 10

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'}))
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault('class', 'form-control')
    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError('An account with this email already exists.')
        return email

class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs.setdefault('class', 'form-control')

class VehicleForm(forms.ModelForm):
    fuel_type = forms.ChoiceField(choices=FUEL_TYPE_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    class Meta:
        model = Vehicle
        fields = ['brand', 'name', 'year', 'fuel_type']
        widgets = {
            'brand': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Honda, Royal Enfield'}),
            'name':  forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Activa, Bullet 350'}),
            'year':  forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2022', 'min': 1980, 'max': date.today().year}),
        }
    def clean_year(self):
        year = self.cleaned_data.get('year')
        if year and (year < 1980 or year > date.today().year):
            raise ValidationError(f'Year must be between 1980 and {date.today().year}.')
        return year

class FuelEntryForm(forms.ModelForm):
    class Meta:
        model = FuelEntry
        fields = ['vehicle', 'litres', 'cost', 'odometer', 'date', 'full_tank']
        widgets = {
            'vehicle':   forms.Select(attrs={'class': 'form-select'}),
            'litres':    forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01', 'placeholder': 'Litres', 'aria-required': 'true'}),
            'cost':      forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0',    'placeholder': 'Cost (₹)', 'aria-required': 'true'}),
            'odometer':  forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1',  'min': '0',    'placeholder': 'Odometer (km)', 'aria-required': 'true'}),
            'date':      forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'aria-required': 'true'}),
            'full_tank': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    def clean_litres(self):
        v = self.cleaned_data.get('litres')
        if v is not None and v <= 0: raise ValidationError('Litres must be greater than 0.')
        return v
    def clean_cost(self):
        v = self.cleaned_data.get('cost')
        if v is not None and v < 0: raise ValidationError('Cost cannot be negative.')
        return v
    def clean_odometer(self):
        v = self.cleaned_data.get('odometer')
        if v is not None and v < 0: raise ValidationError('Odometer cannot be negative.')
        return v
    def clean_date(self):
        d = self.cleaned_data.get('date')
        if d and d > date.today(): raise ValidationError('Date cannot be in the future.')
        return d

class ServiceRecordForm(forms.ModelForm):
    class Meta:
        model = ServiceRecord
        fields = ['vehicle', 'service_type', 'cost', 'odometer', 'date', 'description']
        widgets = {
            'vehicle':      forms.Select(attrs={'class': 'form-select'}),
            'service_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Oil Change, Chain Lube'}),
            'cost':         forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'placeholder': 'Cost (₹)'}),
            'odometer':     forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1',  'min': '0', 'placeholder': 'Odometer (km)'}),
            'date':         forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'description':  forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional notes'}),
        }
    def clean_cost(self):
        v = self.cleaned_data.get('cost')
        if v is not None and v < 0: raise ValidationError('Cost cannot be negative.')
        return v
    def clean_date(self):
        d = self.cleaned_data.get('date')
        if d and d > date.today(): raise ValidationError('Date cannot be in the future.')
        return d

class DocumentForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['vehicle', 'doc_type', 'title', 'file', 'expiry_date', 'note']
        widgets = {
            'vehicle':     forms.Select(attrs={'class': 'form-select'}),
            'doc_type':    forms.Select(attrs={'class': 'form-select'}),
            'title':       forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. My Bike Insurance 2025'}),
            'file':        forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png,.webp'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'note':        forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional notes'}),
        }
    def clean_file(self):
        f = self.cleaned_data.get('file')
        if f:
            ext = f.name.rsplit('.', 1)[-1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                raise ValidationError(f'Only {", ".join(sorted(ALLOWED_EXTENSIONS))} files are allowed.')
            if f.size > MAX_FILE_MB * 1024 * 1024:
                raise ValidationError(f'File must be smaller than {MAX_FILE_MB} MB.')
        return f


# ─── Phase 6: Profile forms ───────────────────────────────────────────────────

from .models import UserProfile, Feedback


class UserProfileForm(forms.ModelForm):
    class Meta:
        model  = UserProfile
        fields = ['display_name', 'bio', 'dob', 'avatar',
                  'unit_distance', 'unit_volume', 'theme_preference',
                  'notify_service', 'notify_docs', 'notify_fuel']
        widgets = {
            'display_name':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'How should we call you?', 'maxlength': 100}),
            'bio':              forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'A short bio (optional)', 'maxlength': 300}),
            'dob':              forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'avatar':           forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/jpeg,image/png,image/webp'}),
            'unit_distance':    forms.Select(attrs={'class': 'form-select'}),
            'unit_volume':      forms.Select(attrs={'class': 'form-select'}),
            'theme_preference': forms.Select(attrs={'class': 'form-select'}),
            'notify_service':   forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_docs':      forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notify_fuel':      forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_avatar(self):
        f = self.cleaned_data.get('avatar')
        if f and hasattr(f, 'name'):
            ext = f.name.rsplit('.', 1)[-1].lower()
            if ext not in {'jpg', 'jpeg', 'png', 'webp'}:
                raise forms.ValidationError('Only JPG, PNG, or WebP images are allowed.')
            if f.size > 3 * 1024 * 1024:
                raise forms.ValidationError('Avatar must be smaller than 3 MB.')
        return f

    def clean_dob(self):
        dob = self.cleaned_data.get('dob')
        if dob and dob >= date.today():
            raise forms.ValidationError('Date of birth must be in the past.')
        return dob


class FeedbackForm(forms.ModelForm):
    class Meta:
        model  = Feedback
        fields = ['category', 'message']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'message':  forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Tell us what you think, report a bug, or suggest a feature…', 'maxlength': 2000}),
        }
    def clean_message(self):
        msg = self.cleaned_data.get('message', '').strip()
        if len(msg) < 10:
            raise forms.ValidationError('Please write at least 10 characters.')
        return msg


class AccountEmailForm(forms.ModelForm):
    """Change the email on the underlying User object."""
    class Meta:
        model  = User
        fields = ['email']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'}),
        }
    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip()
        qs = User.objects.filter(email=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('This email is already used by another account.')
        return email


# ─── OTP auth ──────────────────────────────────────────────────────────────

class OTPRequestForm(forms.Form):
    """Used on the login page to request a one-time code by email instead of a password."""
    identifier = forms.CharField(
        label='Username or email',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username or email'}),
    )


class OTPVerifyForm(forms.Form):
    code = forms.CharField(
        max_length=6, min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control otp-input', 'inputmode': 'numeric', 'pattern': '[0-9]{6}',
            'autocomplete': 'one-time-code', 'placeholder': '••••••', 'maxlength': '6', 'autofocus': True,
        }),
    )

    def clean_code(self):
        code = self.cleaned_data['code'].strip()
        if not code.isdigit():
            raise ValidationError('Enter the 6-digit numeric code.')
        return code
