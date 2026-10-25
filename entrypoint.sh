#!/bin/sh
# Runs on every container start: wait for the database, apply migrations, create the first admin, then start gunicorn.
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  python - <<'PY'
import os, sys, time
url = os.environ.get("DATABASE_URL", "")
if url.startswith(("postgres", "pgsql")):
    import psycopg
    for i in range(40):
        try:
            psycopg.connect(url, connect_timeout=3).close()
            break
        except Exception as exc:
            print(f"Waiting for database ({i + 1}/40): {exc}", flush=True)
            time.sleep(2)
    else:
        sys.exit("Database never became ready.")
PY
  python manage.py migrate --noinput
  python manage.py ensure_superuser
fi

exec "$@"
