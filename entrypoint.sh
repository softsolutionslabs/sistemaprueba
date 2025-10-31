#!/bin/sh
# entrypoint.sh

set -e

echo "Waiting for PostgreSQL..."

# Esperar a que PostgreSQL esté listo
while ! nc -z db 5432; do
  sleep 0.1
done

echo "PostgreSQL started"

# Ejecutar migraciones
echo "Running migrations..."
python manage.py migrate --noinput

# Crear superusuario si no existe
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

# Colectar archivos estáticos
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Iniciar servidor
echo "Starting server..."
exec gunicorn --bind 0.0.0.0:8000 --workers 3 ecommerce_core.wsgi:application