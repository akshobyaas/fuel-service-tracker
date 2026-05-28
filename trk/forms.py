from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Vehicle, FuelEntry, ServiceRecord, Document, FUEL_TYPE_CHOICES, DOC_TYPE_CHOICES
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
