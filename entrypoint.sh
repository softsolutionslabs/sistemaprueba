#!/bin/sh
# entrypoint.sh - VERSIÓN CORREGIDA

set -e

echo "Waiting for PostgreSQL..."
while ! nc -z db 5432; do
  sleep 0.1
done
echo "PostgreSQL started"

echo "Running migrations..."
python manage.py migrate --noinput

echo "Creating superuser..."
python manage.py shell -c "
from accounts.models import Account
if not Account.objects.filter(email='admin@docker.com').exists():
    Account.objects.create_superuser(
        first_name='Admin',
        last_name='Docker',
        email='admin@docker.com',
        username='admin',
        password='admin123'
    )
    print('Superuser created: admin@docker.com / admin123')
else:
    print('Superuser already exists')
"

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting server..."
# CONFIGURACIÓN CORREGIDA PARA WINDOWS
exec gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --worker-class sync --max-requests 1000 --max-requests-jitter 100 ecommerce_core.wsgi:application