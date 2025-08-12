FROM python:3.12.4-slim

# Установка зависимостей
RUN apt update && apt install -y \
    gettext \
    ffmpeg \
    build-essential \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Копируем requirements и устанавливаем зависимости
COPY ./requirements /requirements
RUN pip install --upgrade pip && pip install -r /requirements/dev.txt
RUN rm -rf /requirements

# Копируем проект
COPY ./coto /coto/
WORKDIR /coto

# Создаём папки для логов, статики и медиа
RUN mkdir -p /coto/logs /coto/static /coto/media

# Стартовый скрипт полностью в CMD
CMD python manage.py makemigrations \
 && python manage.py migrate \
 && python manage.py init_superuser \
#  && python manage.py compilemessages \
 && python manage.py collectstatic --no-input \
 && daphne -b 0.0.0.0 -p 8000 coto.asgi:application
