FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DJANGO_STATIC_ROOT=/data/static DJANGO_MEDIA_ROOT=/data/media

# postgresql-client gives us pg_dump / pg_restore for `manage.py backup`
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh \
    && useradd --create-home --uid 10001 app \
    && mkdir -p /data/static /data/media /backups \
    && chown -R app:app /data /backups /app

USER app
# Build-time collectstatic only needs *a* key; the real one comes from the environment at run time.
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "gyansagar.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "4", \
     "--worker-class", "gthread", "--timeout", "120", "--access-logfile", "-", "--max-requests", "1000", "--max-requests-jitter", "100"]
