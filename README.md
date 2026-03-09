# Fuel Service Tracker 🚗⛽

![Python](https://img.shields.io/badge/Python-3.x-blue)
![Django](https://img.shields.io/badge/Django-Web%20Framework-green)
![Status](https://img.shields.io/badge/Project-Active-success)

A **Django-based web application** that helps users track vehicle fuel usage and maintain service records.

This project allows users to **manage vehicles, record fuel entries, and maintain service history** in one place. It provides a simple dashboard that displays useful vehicle statistics like fuel expenses and service details.

---

## Features

### 🚗 Vehicle Management
- Add and manage multiple vehicles
- Select a vehicle to view its details

### ⛽ Fuel Entry Tracking
- Record fuel fill-ups
- Store fuel cost and fuel details
- Track total number of fuel entries

### 🛠 Service Record Management
- Record vehicle service details
- Maintain service history
- Track service mileage

### 📊 Vehicle Dashboard
Displays useful vehicle statistics such as:

- Total fuel entries
- Total fuel cost
- Total service records
- Last service performed
- Previous mileage information

---

## Tech Stack

| Technology | Purpose |
|------------|---------|
| Python | Backend programming |
| Django | Web framework |
| HTML | Page structure |
| Bootstrap | Frontend styling |
| SQLite | Database |
| Git | Version control |

---
## Project Structure
fuel_service_tracker/
│
├── tracker/ # Main Django app
│ ├── models.py
│ ├── views.py
│ ├── admin.py
│ ├── urls.py
│ └── templates/
│
├── templates/
│ └── base.html
│
├── static/
│ ├── css/
│ └── js/
│
├── manage.py
├── db.sqlite3
└── README.md
---

## Installation

### 1. Clone the repository
git clone https://github.com/your-username/fuel-service-tracker.git

cd fuel-service-tracker


### 2. Create a virtual environment

python -m venv venv


### 3. Activate the virtual environment

Windows
venv\Scripts\activate

Mac/Linux
source venv/bin/activate

### 4. Install Django
pip install django

### 5. Apply migrations
python manage.py migrate

### 6. Run the development server
python manage.py runserver

Open the application in your browser:
http://127.0.0.1:8000


---

## Future Improvements

Planned improvements for the project:

- Fuel mileage calculation
- Fuel expense graphs
- Service reminder notifications
- User authentication system
- Multi-user support
- Data export functionality

---

## Author

AK  
Student | Learning Django and Web Development

---

## License

This project is created for **learning and educational purposes**.
