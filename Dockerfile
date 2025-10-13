FROM python:3.12.4-slim

# Avoid interactive prompts and make apt tolerant to release-info changes.
ARG DEBIAN_FRONTEND=noninteractive
ENV DEBIAN_FRONTEND=${DEBIAN_FRONTEND}

# Update + install. Use --no-install-recommends to keep image small.
RUN apt-get update --allow-releaseinfo-change -y \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      gnupg \
      dirmngr \
      git \
      gettext \
      ffmpeg \
      build-essential \
      libpq-dev \
 && apt-get clean \
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
