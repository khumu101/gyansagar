"""python manage.py backup  ->  backups/gyansagar-<time>-db.(dump|sqlite3) + -media.tar.gz, old ones deleted.

Works with PostgreSQL (needs `pg_dump`/`pg_restore` installed) and SQLite. Run it daily from cron / the Docker
`backup` service, and copy the backups/ folder somewhere OFF the server (another disk, Google Drive, S3 ...).
"""
import os
import shutil
import sqlite3
import subprocess
import tarfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

SUFFIXES = ("-db.sqlite3", "-db.dump", "-media.tar.gz")


def pg_args(db):
    args = []
    if db.get("HOST"):
        args += ["--host", str(db["HOST"])]
    if db.get("PORT"):
        args += ["--port", str(db["PORT"])]
    if db.get("USER"):
        args += ["--username", str(db["USER"])]
    return args


def pg_env(db):
    env = dict(os.environ)
    if db.get("PASSWORD"):
        env["PGPASSWORD"] = str(db["PASSWORD"])  # via environment, never on the command line
    return env


def run(cmd, env=None):
    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    except FileNotFoundError:
        raise CommandError(f"'{cmd[0]}' is not installed. Install the PostgreSQL client tools (postgresql-client).")
    if result.returncode != 0:
        raise CommandError(f"{cmd[0]} failed: {result.stderr.strip()[:500]}")
    return result


class Command(BaseCommand):
    help = "Back up the database and uploaded files, and delete old backups."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=os.environ.get("BACKUP_DIR") or str(settings.BASE_DIR / "backups"))
        parser.add_argument("--keep", type=int, default=int(os.environ.get("BACKUP_KEEP", 14)),
                            help="how many backups of each kind to keep (default 14)")
        parser.add_argument("--no-media", action="store_true", help="database only")

    def handle(self, *args, **opts):
        out = Path(opts["dir"])
        out.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        db = settings.DATABASES["default"]
        engine = db["ENGINE"]
        made = []

        if engine.endswith("sqlite3"):
            dest = out / f"gyansagar-{stamp}-db.sqlite3"
            src, dst = sqlite3.connect(str(db["NAME"])), sqlite3.connect(str(dest))
            try:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise CommandError("SQLite backup failed its integrity check.")
            finally:
                src.close()
                dst.close()
        elif engine.endswith("postgresql"):
            dest = out / f"gyansagar-{stamp}-db.dump"
            try:
                run(["pg_dump", "--format=custom", "--no-owner", "--file", str(dest), *pg_args(db),
                     "--dbname", str(db["NAME"])], pg_env(db))
                run(["pg_restore", "--list", str(dest)])  # proves the dump is readable
            except CommandError:
                dest.unlink(missing_ok=True)
                raise
        else:
            raise CommandError(f"Backups are not supported for {engine}.")
        made.append(dest)

        if not opts["no_media"]:
            if settings.STORAGES["default"]["BACKEND"].endswith("FileSystemStorage"):
                media = Path(settings.MEDIA_ROOT)
                if media.is_dir() and any(media.rglob("*")):
                    tar_path = out / f"gyansagar-{stamp}-media.tar.gz"
                    with tarfile.open(tar_path, "w:gz") as tar:
                        tar.add(media, arcname=media.name)
                    made.append(tar_path)
            else:
                self.stdout.write("Uploads live in object storage - enable bucket versioning/backups there.")

        for suffix in SUFFIXES:  # rotation
            old = sorted(out.glob(f"gyansagar-*{suffix}"), reverse=True)[max(opts["keep"], 1):]
            for f in old:
                f.unlink()

        for f in made:
            self.stdout.write(self.style.SUCCESS(f"Backup written: {f} ({f.stat().st_size / 1024:.0f} KB)"))
