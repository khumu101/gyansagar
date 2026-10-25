"""python manage.py restore backups/<file>-db.dump --yes [--media backups/<file>-media.tar.gz]

REPLACES the current database (and optionally the uploaded files). Stop the web app first.
"""
import shutil
import tarfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from .backup import pg_args, pg_env, run


class Command(BaseCommand):
    help = "Restore the database (and optionally media) from a backup made by `manage.py backup`."

    def add_arguments(self, parser):
        parser.add_argument("database_file", help="path to *-db.dump (PostgreSQL) or *-db.sqlite3 (SQLite)")
        parser.add_argument("--media", help="path to *-media.tar.gz")
        parser.add_argument("--yes", action="store_true", help="confirm that the current data may be overwritten")

    def handle(self, *args, **opts):
        if not opts["yes"]:
            raise CommandError("This overwrites the current database. Re-run with --yes if you are sure.")
        src = Path(opts["database_file"])
        if not src.is_file():
            raise CommandError(f"{src} not found.")
        db = settings.DATABASES["default"]
        engine = db["ENGINE"]

        if engine.endswith("sqlite3"):
            if src.suffix != ".sqlite3":
                raise CommandError("A SQLite database needs a *-db.sqlite3 backup.")
            target = Path(db["NAME"])
            if target.exists():
                shutil.copy2(target, target.with_name(target.name + ".before-restore"))
            shutil.copy2(src, target)
        elif engine.endswith("postgresql"):
            if src.suffix != ".dump":
                raise CommandError("A PostgreSQL database needs a *-db.dump backup.")
            run(["pg_restore", "--clean", "--if-exists", "--no-owner", "--dbname", str(db["NAME"]),
                 *pg_args(db), str(src)], pg_env(db))
        else:
            raise CommandError(f"Restore is not supported for {engine}.")
        self.stdout.write(self.style.SUCCESS(f"Database restored from {src.name}"))

        if opts["media"]:
            media_root = Path(settings.MEDIA_ROOT)
            media_root.parent.mkdir(parents=True, exist_ok=True)
            with tarfile.open(opts["media"]) as tar:
                tar.extractall(media_root.parent, filter="data")  # 'data' filter blocks unsafe paths
            self.stdout.write(self.style.SUCCESS("Uploaded files restored."))
