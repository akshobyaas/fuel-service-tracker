web: gunicorn fstp.wsgi --bind 0.0.0.0:$PORT --workers 2 --timeout 120
release: pip install -r requirements.txt && python manage.py collectstatic --noinput