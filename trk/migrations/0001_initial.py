from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='Vehicle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('brand', models.CharField(max_length=100)),
                ('name', models.CharField(max_length=100)),
                ('year', models.IntegerField()),
                ('fuel_type', models.CharField(max_length=20)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='vehicles', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Vehicle', 'verbose_name_plural': 'Vehicles', 'ordering': ['-id']},
        ),
        migrations.CreateModel(
            name='FuelEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('litres', models.FloatField()),
                ('cost', models.FloatField()),
                ('odometer', models.FloatField()),
                ('date', models.DateField()),
                ('full_tank', models.BooleanField(default=False)),
                ('vehicle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='fuel_entries', to='trk.vehicle')),
            ],
            options={'verbose_name': 'Fuel Entry', 'verbose_name_plural': 'Fuel Entries', 'ordering': ['date', 'id']},
        ),
        migrations.CreateModel(
            name='ServiceRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('service_type', models.CharField(max_length=100)),
                ('odometer', models.DecimalField(blank=True, decimal_places=1, max_digits=8, null=True)),
                ('cost', models.FloatField()),
                ('date', models.DateField()),
                ('description', models.TextField(blank=True, default='')),
                ('vehicle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='service_records', to='trk.vehicle')),
            ],
            options={'verbose_name': 'Service Record', 'verbose_name_plural': 'Service Records', 'ordering': ['-date']},
        ),
        migrations.CreateModel(
            name='Document',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True)),
                ('doc_type', models.CharField(max_length=30, choices=[('Insurance','Insurance'),('RC Book','RC Book'),('PUC','PUC Certificate'),('Invoice','Service Invoice'),('Warranty','Warranty Card'),('Other','Other')])),
                ('title', models.CharField(max_length=150)),
                ('file', models.FileField(upload_to='documents/%Y/%m/')),
                ('expiry_date', models.DateField(blank=True, null=True)),
                ('note', models.TextField(blank=True, default='')),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('vehicle', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='trk.vehicle')),
            ],
            options={'verbose_name': 'Document', 'verbose_name_plural': 'Documents', 'ordering': ['-uploaded_at']},
        ),
    ]
