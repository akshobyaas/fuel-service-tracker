# Fuel Service Tracker

## 🔗 Live Demo
**[https://fst-ujb6.onrender.com](https://fst-ujb6.onrender.com)**

> Hosted on Render (free tier — may take ~30s to wake up on first load)

A premium, full-featured Django web application for tracking vehicle fuel consumption, mileage efficiency, service records, and documents. Built for bike and car owners who want clean data and real insights.

---

## Features

**Fuel Tracking**
- Log every fill-up: litres, cost, odometer, full-tank flag
- Correct tank-to-tank mileage calculation (km/L)
- Odometer rollback protection

**Analytics & Charts**
- Monthly fuel cost bar chart
- Mileage trend line chart with average overlay
- Cost per km chart
- Service cost breakdown by vehicle
- Smart insights: best/average mileage, trend direction, avg cost per fill-up

**Service Records**
- Log any service type: oil change, tyre change, chain lube, etc.
- Odometer-based service history

**Document Storage**
- Upload insurance, RC book, PUC certificate, invoices, warranties
- Expiry tracking with colour-coded status (ok / warning / critical / expired)
- Dashboard banner for documents expiring within 60 days
- Secure per-user file storage

**User Accounts**
- Register, login, logout
- All data is private and scoped per user

**Export**
- Download fuel history, service history, and mileage report as CSV
- UTF-8 BOM for seamless Excel compatibility

**PWA — Progressive Web App**
- Installable on Android, iOS, and desktop (Chrome/Edge)
- Offline fallback page
- App shortcuts to Add Fuel and Add Service
- Service worker caches CSS/fonts for fast repeat loads

**Accessibility (WCAG 2.1 AA)**
- Skip-to-content link
- `aria-current`, `aria-live`, `aria-modal`, `aria-required` throughout
- Focus-visible rings for keyboard navigation
- `prefers-reduced-motion` support
- Print-friendly stylesheet

**Design**
- Dark mode / light mode toggle (persisted in localStorage, no flash)
- Lucide SVG icons — no emojis
- DM Sans + Space Mono fonts
- Responsive — works on mobile, tablet, desktop

---

## Tech Stack

| Layer      | Technology                        |
|------------|-----------------------------------|
| Backend    | Django 5.2, Python 3.11+          |
| Database   | SQLite (dev) — swap to PostgreSQL |
| Static     | WhiteNoise (gzip + cache-busting) |
| Charts     | Chart.js 4.4                      |
| CSS        | Custom design system (no Tailwind)|
| PWA        | Vanilla service worker            |

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/akshobyaas/fst.git
cd fst
```

### 2. Create virtual environment

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
cp .env.example .env
# Edit .env — set a strong SECRET_KEY
```

`.env.example`:
```
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

### 5. Run migrations

```bash
python manage.py migrate
```

### 6. Create your account

```bash
python manage.py createsuperuser   # optional, for admin access
```

Or just register at `/register/` in the browser.

### 7. Run the dev server

```bash
python manage.py runserver
```

Open [http://localhost:8000](http://localhost:8000).

---

## Production Deployment

This app is deployed on [Railway](https://railway.app) at https://f-s-t.up.railway.app

### Environment variables required

| Variable | Value |
|---|---|
| `SECRET_KEY` | Long random string |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `your-app.railway.app` |
| `CSRF_TRUSTED_ORIGINS` | `https://your-app.railway.app` |
| `DATABASE_URL` | Set automatically by Railway PostgreSQL |

### Recommended: swap SQLite → PostgreSQL

```python
# fstp/settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'fueltracker',
        'USER': 'youruser',
        'PASSWORD': 'yourpassword',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

Add `psycopg2-binary` to `requirements.txt`.

### Recommended: swap local file storage → S3

For document uploads in production, use `django-storages` with S3 or any S3-compatible service (Backblaze B2, Cloudflare R2).

---

## Project Structure

```
fuel-service-tracker/
├── fstp/                    # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── trk/                     # Main app
│   ├── models.py            # Vehicle, FuelEntry, ServiceRecord, Document
│   ├── views.py             # All views incl. exports, PWA, charts
│   ├── forms.py             # Django ModelForms with validation
│   ├── urls.py              # All URL routes
│   ├── migrations/
│   ├── static/trk/css/
│   │   └── style.css        # Full design system (~1800 lines)
│   └── templates/trk/
│       ├── base.html        # Layout, sidebar, theme, SW, modal
│       ├── home.html        # Dashboard with charts + insights
│       ├── vehicles.html
│       ├── fuel_entry.html
│       ├── fuel_history.html
│       ├── mileage.html
│       ├── service_entry.html
│       ├── service_history.html
│       ├── documents.html
│       ├── profile.html
│       ├── auth/            # login.html, register.html
│       ├── errors/          # 404.html, 500.html
│       └── pwa/             # manifest.json, offline.html
├── static/
│   ├── js/sw.js             # Service worker
│   └── pwa/                 # icon-192.png, icon-512.png
├── manage.py
├── requirements.txt
└── .env.example
```

---

## Development Phases

This project was built across 5 phases:

| Phase | Focus |
|-------|-------|
| 1     | Bug fixes, Django Forms, security (@require_POST, CSRF) |
| 2     | Premium UI design system, dark/light mode, animations |
| 3     | Charts (Chart.js), smart insights, Lucide SVG icons |
| 4     | User authentication, document storage, expiry tracking |
| 5A    | Performance (select_related/prefetch_related), PWA, WhiteNoise |
| 5B    | CSV export for fuel, service, mileage |
| 5C    | Accessibility (WCAG 2.1 AA) |
| 5D    | Final polish — skeleton loaders, print styles, animations |

---

## URLs Reference

| URL | View | Description |
|-----|------|-------------|
| `/` | `home` | Dashboard |
| `/register/` | `register_view` | Create account |
| `/login/` | `login_view` | Sign in |
| `/logout/` | `logout_view` | Sign out (POST) |
| `/vehicles/` | `vehicles` | Vehicle list |
| `/fuel/` | `fuel_entry` | Add fuel entry |
| `/fuel-history/` | `fuel_history` | Fuel history |
| `/mileage/` | `mileage_report` | Mileage report |
| `/service/` | `service_entry` | Add service record |
| `/service-history/` | `service_history` | Service history |
| `/documents/` | `documents` | Document list |
| `/documents/add/` | `add_document` | Upload document |
| `/profile/` | `profile` | User profile |
| `/export/fuel/` | `export_fuel` | CSV export — fuel |
| `/export/service/` | `export_service` | CSV export — service |
| `/export/mileage/` | `export_mileage` | CSV export — mileage |
| `/manifest.json` | `pwa_manifest` | PWA manifest |
| `/offline/` | `pwa_offline` | Offline fallback |
| `/api/chart/mileage/<id>/` | `chart_mileage` | Chart JSON API |
| `/api/chart/monthly-cost/<id>/` | `chart_monthly_cost` | Chart JSON API |
| `/api/chart/service-breakdown/<id>/` | `chart_service_breakdown` | Chart JSON API |

---

## License

MIT — free to use, modify, and deploy.
