#!/bin/sh
# entrypoint.sh - VERSIÓN CON DJANGO RUNSERVER

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
if not Account.objects.filter(email='admin@gmail.com').exists():
    Account.objects.create_superuser(
        first_name='Admin',
        last_name='Docker',
        email='admin@gmail.com',
        username='admin',
        password='admin1234'
    )
    print('Superuser created: admin@gmail.com / admin123')
else:
    print('Superuser already exists')
"

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Django development server..."
exec python manage.py runserver 0.0.0.0:8000 --noreload