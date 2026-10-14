FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Static files are collected at build time; WhiteNoise serves them from the image.
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && useradd --create-home --uid 1000 rentora \
    && mkdir -p /data \
    && chown -R rentora:rentora /data /app/staticfiles \
    && chmod +x docker-entrypoint.sh

USER rentora

# SQLite database, uploaded photos and private chat media live on the /data volume.
ENV DJANGO_DEBUG=0 \
    SQLITE_PATH=/data/db.sqlite3 \
    MEDIA_ROOT=/data/media \
    CHAT_MEDIA_ROOT=/data/chat-media \
    SERVE_MEDIA=1 \
    CACHE_DIR=/data/cache

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=4)"

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--worker-class", "gthread", "--threads", "4", "--timeout", "600", "--access-logfile", "-"]
