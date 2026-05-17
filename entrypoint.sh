#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."

# Railway pe DATABASE_URL se host extract karo
# Local Docker pe "db" hostname use karo
if [ -n "$DATABASE_URL" ]; then
    DB_HOST=$(python3 -c "
import urllib.parse, os
url = urllib.parse.urlparse(os.environ['DATABASE_URL'])
print(url.hostname)
")
    DB_PORT=$(python3 -c "
import urllib.parse, os
url = urllib.parse.urlparse(os.environ['DATABASE_URL'])
print(url.port or 5432)
")
    echo "Connecting to: $DB_HOST:$DB_PORT"
    while ! nc -z $DB_HOST $DB_PORT; do
        sleep 0.5
    done
else
    echo "Using local Docker db host..."
    while ! nc -z db 5432; do
        sleep 0.5
    done
fi

echo "PostgreSQL is ready!"

echo "Running migrations..."
python manage.py migrate --noinput


echo "Creating superuser..."       
python manage.py create_superuser  

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn server..."
exec gunicorn core.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -