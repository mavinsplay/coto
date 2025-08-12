#!/bin/sh
set -e  # чтобы скрипт падал при ошибке

python manage.py makemigrations
python manage.py migrate
python manage.py init_superuser
python manage.py compilemessages
python manage.py collectstatic --no-input

exec "$@"
