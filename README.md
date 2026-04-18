<div align="center">
  <a href="https://cotoo.ru">cotoo.ru</a>
  <h1>🍿 Coto - Платформа для совместного просмотра видео</h1>
  <p><strong>Coto</strong> — это удобная функциональная платформа, которая позволяет загружать свои видео или использовать внешние ссылки (YouTube, Google Drive), чтобы наслаждаться просмотром вместе с друзьями в реальном времени.</p>
  
  <p>
    <a href="https://github.com/mavinsplay/coto/actions/workflows/ci-cd-pipeline.yml"><img src="https://img.shields.io/github/actions/workflow/status/mavinsplay/coto/ci-cd-pipeline.yml?style=for-the-badge&logo=github&label=CI%2FCD" alt="CI/CD Pipeline"></a>
    <img src="https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12">
    <img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django">
    <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
  </p>
</div>

---

## ✨ Особенности

* **📺 Совместный просмотр (Watch Parties):** Синхронизированное воспроизведение видео для всех участников комнаты без рассинхрона.
* **🔗 Внешние источники видео:** Поддержка загрузки собственных видеофайлов, а также нативная интеграция стриминга по ссылкам с **YouTube** и **Google Drive**.
* **🎉 Интерактивность в реальном времени:** Общение через эмоции! Отправляйте красивые анимированные реакции (сердечки, смех) и эффекты (например, размытие экрана) прямо поверх видео всем зрителям.
* **📱 Адаптивный и современный дизайн:** Плавный и красивый UI на базе кастомного плеера (Plyr), который отлично работает как на ПК, так и на мобильных устройствах.

## 🛠 Технологический стек

* **Backend:** Python 3.12, Django, Django Channels (WebSockets)
* **Асинхронные задачи:** Celery
* **Брокер сообщений и кэш:** Redis 7
* **База данных:** PostgreSQL 17
* **Инфраструктура:** Docker, Docker Compose, Nginx, GitHub Actions
* **Frontend:** Кастомный Plyr (JS/CSS), адаптивный UI-интерфейс

---

## 🚀 Быстрый старт

Проект можно запустить двумя способами: нативно (локально на вашем устройстве) и через Docker (наиболее простой и предпочтительный способ). 

Сначала в любом случае необходимо склонировать репозиторий:
```bash
git clone https://github.com/mavinsplay/coto.git
cd coto
```

### 🐳 Запуск через Docker (рекомендуется)

Убедитесь, что у вас установлены `Docker` и `Docker Compose`.

1. Создайте конфигурационный файл переменных окружения на основе примера:
   ```bash
   cp .env.example .env
   ```
   *(Отредактируйте `.env`, если требуется изменить пароли для БД, Redis или доменные доступы).*

2. Соберите и запустите контейнеры для локальной разработки (используя профиль `dev`):
   ```bash
   docker-compose --profile dev up -d --build
   ```

3. Выполните миграции базы данных:
   ```bash
   docker exec -it coto_django python manage.py migrate
   ```

4. Сайт будет доступен по адресу: http://localhost

> **Для продакшена (HTTPS):**
> Используйте `docker-compose --profile prod up -d --build`. Будет запущен Nginx с автоматическим получением SSL-сертификатов через Certbot.

### 💻 Локальный запуск (Нативно)

Если вы хотите запустить проект без Docker (на вашем компьютере должны быть предварительно установлены PostgreSQL и Redis).

1. Создайте виртуальное окружение и активируйте его:
   ```bash
   # Создание окружения
   python -m venv .venv
   
   # Активация для Windows (PowerShell/CMD):
   .venv\Scripts\activate
   
   # Активация для Linux/macOS:
   source .venv/bin/activate
   ```

2. Установите зависимости проекта для разработки:
   ```bash
   pip install -r requirements/dev.txt
   ```

3. Подготовьте переменные окружения:
   ```bash
   cp .env.example .env
   ```
   Укажите в `.env` корректные доступы к вашим локальным серверам **PostgreSQL** и **Redis**.

4. Примените миграции:
   ```bash
   python manage.py migrate
   ```

5. Запустите воркер Celery (потребуется открыть отдельное окно терминала):
   ```bash
   # Не забудьте активировать виртуальное окружение (.venv) в новом окне!
   celery -A coto worker --loglevel=INFO
   ```

6. Запустите сервер разработки Django:
   ```bash
   python manage.py runserver
   ```
   Проект будет доступен по адресу: http://127.0.0.1:8000

---

## 🤝 Разработка и вклад в проект

Мы всегда рады новым Pull Request'ам! Прежде чем вносить крупные изменения, пожалуйста, создайте Issue для их обсуждения. 
Проект использует форматер **black** (настройки определены в `pyproject.toml`).

## 📄 Лицензия

Проект распространяется под лицензией (дополнительную информацию см. в файле `LICENSE`).
