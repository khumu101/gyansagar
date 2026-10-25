"""Tests for production features: health checks, file serving modes, client IP, throttles, backup/restore."""
import io
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase, override_settings

from core.models import Level, Program, Resource, Subject
from core.utils import client_ip

User = get_user_model()


class HealthTests(TestCase):
    def test_healthz(self):
        r = self.client.get("/healthz/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")
        self.assertIn("version", r.json())

    def test_readyz_ok(self):
        r = self.client.get("/readyz/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["checks"]["database"], "ok")

    def test_readyz_db_down(self):
        with mock.patch("core.views.connection.cursor", side_effect=Exception("down")):
            r = self.client.get("/readyz/")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["checks"]["database"], "error")

    def test_post_not_allowed(self):
        self.assertEqual(self.client.post("/healthz/").status_code, 405)


class ClientIpTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_default_uses_remote_addr(self):
        req = self.rf.get("/", REMOTE_ADDR="1.2.3.4", HTTP_X_CLIENT_IP="9.9.9.9")
        self.assertEqual(client_ip(req), "1.2.3.4")

    @override_settings(CLIENT_IP_HEADER="X-Client-IP")
    def test_header_used(self):
        req = self.rf.get("/", REMOTE_ADDR="172.18.0.2", HTTP_X_CLIENT_IP="203.0.113.7")
        self.assertEqual(client_ip(req), "203.0.113.7")

    @override_settings(CLIENT_IP_HEADER="X-Client-IP")
    def test_garbage_header_falls_back(self):
        req = self.rf.get("/", REMOTE_ADDR="172.18.0.2", HTTP_X_CLIENT_IP="not-an-ip")
        self.assertEqual(client_ip(req), "172.18.0.2")


class ThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def _signup(self, n):
        return Client().post("/accounts/signup/", {
            "first_name": "T", "username": f"user{n}", "email": f"u{n}@example.com",
            "password1": "abc123", "password2": "abc123"})

    @override_settings(SIGNUP_MAX_PER_HOUR=2)
    def test_signup_limited(self):
        self.assertNotEqual(self._signup(1).status_code, 429)
        self.assertNotEqual(self._signup(2).status_code, 429)
        self.assertEqual(self._signup(3).status_code, 429)

    @override_settings(PASSWORD_RESET_MAX_PER_HOUR=2)
    def test_password_reset_limited(self):
        for _ in range(2):
            self.assertEqual(self.client.post("/accounts/password/reset/", {"email": "a@b.com"}).status_code, 302)
        self.assertEqual(self.client.post("/accounts/password/reset/", {"email": "a@b.com"}).status_code, 429)


class ServeMethodTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ov = override_settings(MEDIA_ROOT=self._tmp.name)
        self.ov.enable()
        self.addCleanup(self.ov.disable)
        level = Level.objects.create(name="Bachelor", subtitle="UG", icon="🎓", category=Level.DEGREE)
        program = Program.objects.create(level=level, name="BSc CSIT", duration="4 Years")
        subject = Subject.objects.create(level=level, program=program, name="Maths", semester=1)
        self.res = Resource.objects.create(
            subject=subject, title="Notes", kind="notes",
            file=SimpleUploadedFile("my notes.pdf", b"%PDF-1.4 test", content_type="application/pdf"))
        User.objects.create_user("stu", "s@x.com", "abc123")
        self.client.login(username="stu", password="abc123")

    def url(self):
        return f"/resource/{self.res.pk}/open/"

    @override_settings(RESOURCE_SERVE_METHOD="nginx", RESOURCE_ACCEL_PREFIX="/protected-media/")
    def test_nginx_accel_redirect(self):
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["X-Accel-Redirect"].startswith("/protected-media/"))
        self.assertEqual(r.content, b"")
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.res.refresh_from_db()
        self.assertEqual(self.res.download_count, 1)

    @override_settings(RESOURCE_SERVE_METHOD="redirect")
    def test_redirect_method(self):
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 302)
        self.assertIn("/media/", r["Location"])

    @override_settings(RESOURCE_SERVE_METHOD="nginx")
    def test_nginx_missing_file_404(self):
        Path(self.res.file.path).unlink()
        self.assertEqual(self.client.get(self.url()).status_code, 404)

    def test_login_still_required(self):
        self.client.logout()
        with override_settings(RESOURCE_SERVE_METHOD="nginx"):
            r = self.client.get(self.url())
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("X-Accel-Redirect", r)


class BackupRestoreTests(TestCase):
    """SQLite file-based round trip (runs in CI on SQLite; Postgres is covered by manual/CI pg job)."""

    def test_ensure_superuser(self):
        env = {"DJANGO_SUPERUSER_USERNAME": "boss", "DJANGO_SUPERUSER_PASSWORD": "pw12345",
               "DJANGO_SUPERUSER_EMAIL": "b@x.com"}
        with mock.patch.dict(os.environ, env):
            call_command("ensure_superuser", stdout=io.StringIO())
            call_command("ensure_superuser", stdout=io.StringIO())  # idempotent
        self.assertEqual(User.objects.filter(username="boss", is_superuser=True).count(), 1)

    def test_ensure_superuser_without_env_is_noop(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DJANGO_SUPERUSER_USERNAME", None)
            call_command("ensure_superuser", stdout=io.StringIO())
        self.assertFalse(User.objects.exists())

    def test_restore_requires_yes(self):
        with self.assertRaises(CommandError):
            call_command("restore", "whatever.dump")

    def test_sqlite_backup_rotation_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            dbfile = Path(tmp) / "live.sqlite3"
            con = sqlite3.connect(dbfile)
            con.execute("create table t (v text)")
            con.execute("insert into t values ('hello')")
            con.commit()
            con.close()
            media = Path(tmp) / "media"
            media.mkdir()
            (media / "a.txt").write_text("file")
            dbs = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(dbfile)}}
            out = Path(tmp) / "bk"
            with override_settings(DATABASES=dbs, MEDIA_ROOT=str(media)):
                for _ in range(3):
                    call_command("backup", dir=str(out), keep=2, stdout=io.StringIO())
                    # distinct timestamps
                    import time; time.sleep(1.1)
                self.assertEqual(len(list(out.glob("*-db.sqlite3"))), 2)  # rotation
                self.assertEqual(len(list(out.glob("*-media.tar.gz"))), 2)
                latest = sorted(out.glob("*-db.sqlite3"))[-1]
                tar = sorted(out.glob("*-media.tar.gz"))[-1]
                # break the live data, then restore
                con = sqlite3.connect(dbfile); con.execute("delete from t"); con.commit(); con.close()
                (media / "a.txt").unlink()
                call_command("restore", str(latest), media=str(tar), yes=True, stdout=io.StringIO())
                con = sqlite3.connect(dbfile)
                self.assertEqual(con.execute("select v from t").fetchone()[0], "hello")
                con.close()
                self.assertTrue((media / "a.txt").exists())


class PreviewTests(TestCase):
    """PDF/image/text are shown in the browser; any other format downloads; typed text is read on the page."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        ov = override_settings(MEDIA_ROOT=self._tmp.name)
        ov.enable()
        self.addCleanup(ov.disable)
        level = Level.objects.create(name="Bachelor", subtitle="UG", icon="🎓", category=Level.DEGREE)
        self.subject = Subject.objects.create(level=level, name="Maths", semester=1)
        User.objects.create_user("stu", "s@x.com", "abc123")
        self.client.login(username="stu", password="abc123")

    def make(self, name, data, **extra):
        return Resource.objects.create(subject=self.subject, title=name, kind="notes",
                                       file=SimpleUploadedFile(name, data), **extra)

    def test_pdf_has_viewer_page_and_inline_open(self):
        r = self.make("paper.pdf", b"%PDF-1.4 x")
        page = self.client.get(r.get_view_url())
        self.assertContains(page, "<iframe")
        self.assertContains(page, "Download")
        inline = self.client.get(r.get_open_url())
        self.assertTrue(inline["Content-Disposition"].startswith("inline"))
        self.assertEqual(inline["X-Frame-Options"], "SAMEORIGIN")  # our own page may embed it
        self.assertTrue(self.client.get(r.get_download_url())["Content-Disposition"].startswith("attachment"))

    def test_row_links_to_viewer(self):
        r = self.make("paper.pdf", b"%PDF-1.4 x")
        page = self.client.get(self.subject.get_absolute_url() + "?tab=notes")
        self.assertContains(page, r.get_view_url())
        self.assertContains(page, "?dl=1")

    def test_txt_file_rendered_on_page_and_escaped(self):
        r = self.make("q.txt", "प्रश्न १ <script>alert(1)</script>".encode())
        page = self.client.get(r.get_view_url())
        self.assertContains(page, "प्रश्न १")
        self.assertNotContains(page, "<script>alert(1)</script>")

    def test_typed_text_resource(self):
        r = Resource.objects.create(subject=self.subject, title="Old Q 2080", kind="question-banks",
                                    content="Q1. What is a matrix?\nQ2. Define limit.")
        self.assertTrue(r.is_text_only)
        page = self.client.get(r.get_view_url())
        self.assertContains(page, "Q1. What is a matrix?")
        self.assertRedirects(self.client.get(r.get_open_url()), r.get_view_url(), fetch_redirect_response=False)
        r.refresh_from_db()
        self.assertEqual(r.download_count, 1)
        listing = self.client.get(self.subject.get_absolute_url() + "?tab=question-banks")
        self.assertContains(listing, "Read online")
        self.assertContains(self.client.get("/search/", {"q": "matrix"}), "Old Q 2080")

    def test_word_file_downloads_not_previewed(self):
        r = self.make("notes.docx", b"PK")
        self.assertEqual(r.preview_kind, "")
        self.assertEqual(r.action_label, "Download")
        self.assertRedirects(self.client.get(r.get_view_url()), r.get_open_url(), fetch_redirect_response=False)
        self.assertTrue(self.client.get(r.get_open_url())["Content-Disposition"].startswith("attachment"))

    def test_any_format_but_not_dangerous_ones(self):
        from django.core.exceptions import ValidationError
        for ok in ("book.epub", "sheet.ods", "data.rar", "pic.bmp", "notes.odt", "song.flac"):
            Resource(subject=self.subject, title="t", file=SimpleUploadedFile(ok, b"x")).full_clean()
        for bad in ("a.exe", "a.html", "a.svg", "a.js", "a.php", "noext"):
            with self.assertRaises(ValidationError, msg=bad):
                Resource(subject=self.subject, title="t", file=SimpleUploadedFile(bad, b"x")).full_clean()

    def test_login_required_and_unpublished_hidden(self):
        r = self.make("paper.pdf", b"%PDF-1.4 x")
        r.is_published = False
        r.save()
        self.assertEqual(self.client.get(r.get_view_url()).status_code, 404)
        self.client.logout()
        r.is_published = True
        r.save()
        self.assertEqual(self.client.get(r.get_view_url()).status_code, 302)

    def test_empty_resource_rejected(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            Resource(subject=self.subject, title="empty", content="   ").full_clean()
