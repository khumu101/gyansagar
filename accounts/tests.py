from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Level, Program

from .models import Profile

User = get_user_model()
PW = "Tr1cky-Pass-92"


class AuthBase(TestCase):
    def setUp(self):
        cache.clear()
        self.level = Level.objects.create(name="Bachelor", subtitle="UG", icon="🎓", category="degree")
        self.program = Program.objects.create(level=self.level, name="BSc CSIT")

    def signup_data(self, **over):
        data = {"first_name": "Khumu", "last_name": "B", "username": "khumu", "email": "Khumu@Example.com",
                "level": self.level.pk, "program": self.program.pk, "password1": PW, "password2": PW}
        data.update(over)
        return data


class SignupTests(AuthBase):
    def test_signup_creates_user_profile_and_logs_in(self):
        r = self.client.post(reverse("accounts:signup"), self.signup_data())
        self.assertRedirects(r, reverse("core:home"), fetch_redirect_response=False)
        user = User.objects.get(username="khumu")
        self.assertEqual(user.email, "khumu@example.com")  # normalised
        self.assertEqual(user.profile.program, self.program)
        self.assertEqual(user.profile.level, self.level)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertContains(self.client.get(reverse("core:home")), "Logout")

    def test_new_user_can_log_in_again_afterwards(self):
        self.client.post(reverse("accounts:signup"), self.signup_data())
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)
        r = self.client.post(reverse("accounts:login"), {"username": "khumu", "password": PW})
        self.assertRedirects(r, reverse("core:home"), fetch_redirect_response=False)

    @override_settings(SIGNUP_AUTO_LOGIN=False)
    def test_signup_without_autologin_goes_to_login_page(self):
        r = self.client.post(reverse("accounts:signup"), self.signup_data())
        self.assertRedirects(r, reverse("accounts:login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(self.client.get(reverse("accounts:login")), "Account created")

    def test_duplicate_email_and_username_rejected(self):
        User.objects.create_user("other", "khumu@example.com", PW)
        r = self.client.post(reverse("accounts:signup"), self.signup_data())
        self.assertContains(r, "already exists")
        self.client.post(reverse("accounts:signup"), self.signup_data(email="new@example.com", username="OTHER"))
        self.assertEqual(User.objects.filter(username__iexact="other").count(), 1)

    def test_password_rule_is_just_minimum_length(self):
        # too short -> rejected, with a clear message
        r = self.client.post(reverse("accounts:signup"),
                             self.signup_data(email="a@example.com", username="u1", password1="abc12", password2="abc12"))
        self.assertContains(r, "at least 6 characters")
        self.assertFalse(User.objects.filter(username="u1").exists())
        # numeric-only, common, or similar-to-username passwords are all fine now
        for i, pw in enumerate(["123456", "password", "khumu123", "abcdefghijklmnopqrstuvwxyz"]):
            self.client.logout()
            r = self.client.post(reverse("accounts:signup"), self.signup_data(
                email=f"x{i}@example.com", username=f"user{i}", password1=pw, password2=pw))
            self.assertEqual(r.status_code, 302, pw)

    def test_password_mismatch(self):
        r = self.client.post(reverse("accounts:signup"), self.signup_data(password2="different-Pass-1"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="khumu").exists())

    def test_program_must_match_level(self):
        other = Level.objects.create(name="Master", subtitle="PG", icon="x", category="degree")
        r = self.client.post(reverse("accounts:signup"), self.signup_data(level=other.pk))
        self.assertContains(r, "does not belong")

    def test_level_and_program_optional(self):
        r = self.client.post(reverse("accounts:signup"), self.signup_data(level="", program=""))
        self.assertEqual(r.status_code, 302)

    def test_signup_next_only_same_site(self):
        r = self.client.post(reverse("accounts:signup"), self.signup_data(next="https://evil.example/"))
        self.assertEqual(r["Location"], reverse("core:home"))


class LoginTests(AuthBase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("asha", "asha@example.com", PW)

    def test_login_with_username_and_email(self):
        for ident in ("asha", "ASHA@example.com"):
            self.client.logout()
            r = self.client.post(reverse("accounts:login"), {"username": ident, "password": PW})
            self.assertEqual(r.status_code, 302, ident)
            self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_wrong_password(self):
        r = self.client.post(reverse("accounts:login"), {"username": "asha", "password": "nope"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        r = self.client.post(reverse("accounts:login"), {"username": "asha", "password": PW})
        self.assertEqual(r.status_code, 200)

    def test_ambiguous_email_is_refused(self):
        User.objects.create_user("asha2", "asha@example.com", PW)
        r = self.client.post(reverse("accounts:login"), {"username": "asha@example.com", "password": PW})
        self.assertEqual(r.status_code, 200)

    def test_lockout_after_repeated_failures(self):
        for _ in range(5):
            self.client.post(reverse("accounts:login"), {"username": "asha", "password": "bad"})
        r = self.client.post(reverse("accounts:login"), {"username": "asha", "password": PW})  # even correct pw
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Too many failed attempts")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_success_resets_failure_counter(self):
        for _ in range(3):
            self.client.post(reverse("accounts:login"), {"username": "asha", "password": "bad"})
        self.client.post(reverse("accounts:login"), {"username": "asha", "password": PW})
        self.client.logout()
        for _ in range(3):
            self.client.post(reverse("accounts:login"), {"username": "asha", "password": "bad"})
        r = self.client.post(reverse("accounts:login"), {"username": "asha", "password": PW})
        self.assertEqual(r.status_code, 302)

    def test_next_is_honoured_but_external_ignored(self):
        r = self.client.post(reverse("accounts:login"),
                             {"username": "asha", "password": PW, "next": "/search/?q=c"})
        self.assertEqual(r["Location"], "/search/?q=c")
        self.client.logout()
        r = self.client.post(reverse("accounts:login"),
                             {"username": "asha", "password": PW, "next": "https://evil.example/"})
        self.assertEqual(r["Location"], reverse("core:home"))

    def test_without_remember_me_session_is_browser_session(self):
        self.client.post(reverse("accounts:login"), {"username": "asha", "password": PW})
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.client.logout()
        self.client.post(reverse("accounts:login"), {"username": "asha", "password": PW, "remember_me": "on"})
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_logout_is_post_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.client.post(reverse("accounts:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logged_in_user_skips_login_page(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 302)
        self.assertEqual(self.client.get(reverse("accounts:signup")).status_code, 302)

    def test_csrf_enforced(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        r = c.post(reverse("accounts:login"), {"username": "asha", "password": PW})
        self.assertEqual(r.status_code, 403)

    def test_header_buttons_work_for_guests(self):
        r = self.client.get(reverse("core:home"))
        self.assertContains(r, reverse("accounts:login"))
        self.assertContains(r, reverse("accounts:signup"))


class ProfileTests(AuthBase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("asha", "asha@example.com", PW, first_name="Asha")

    def test_profile_requires_login(self):
        r = self.client.get(reverse("accounts:profile"))
        self.assertRedirects(r, f"{reverse('accounts:login')}?next={reverse('accounts:profile')}")

    def test_profile_created_for_every_user(self):
        self.assertTrue(Profile.objects.filter(user=self.user).exists())
        admin = User.objects.create_superuser("root", "root@example.com", PW)
        self.assertTrue(Profile.objects.filter(user=admin).exists())

    def test_update_profile(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("accounts:profile"), {
            "first_name": "Asha", "last_name": "K", "email": "new@example.com", "phone": "+977 9800000000",
            "level": self.level.pk, "program": self.program.pk, "bio": "CSIT student"})
        self.assertRedirects(r, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertEqual(self.user.profile.program, self.program)

    def test_cannot_take_someone_elses_email_or_bad_phone(self):
        User.objects.create_user("bob", "bob@example.com", PW)
        self.client.force_login(self.user)
        r = self.client.post(reverse("accounts:profile"), {
            "first_name": "Asha", "last_name": "", "email": "BOB@example.com", "phone": "abc", "bio": ""})
        self.assertContains(r, "already exists")
        self.assertContains(r, "valid phone")

    def test_role_cannot_be_self_assigned(self):
        self.client.force_login(self.user)
        self.client.post(reverse("accounts:profile"), {
            "first_name": "Asha", "last_name": "", "email": "asha@example.com", "phone": "", "bio": "",
            "role": "teacher"})
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.role, Profile.STUDENT)

    def test_password_change(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("accounts:password_change"), {
            "old_password": PW, "new_password1": "Another-Pass-77", "new_password2": "Another-Pass-77"})
        self.assertRedirects(r, reverse("accounts:password_change_done"))
        self.client.logout()
        self.assertTrue(self.client.login(username="asha", password="Another-Pass-77"))


class PasswordResetTests(AuthBase):
    def test_reset_flow_sends_email_and_sets_new_password(self):
        from django.core import mail
        user = User.objects.create_user("asha", "asha@example.com", PW)
        r = self.client.post(reverse("accounts:password_reset"), {"email": "asha@example.com"})
        self.assertRedirects(r, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        link = [l for l in mail.outbox[0].body.splitlines() if "/accounts/password/reset/" in l][0].strip()
        path = "/" + link.split("://", 1)[1].split("/", 1)[1]
        r = self.client.get(path, follow=True)  # token redirects to the set-password form
        form_url = r.redirect_chain[-1][0]
        r = self.client.post(form_url, {"new_password1": "Brand-New-Pass-5", "new_password2": "Brand-New-Pass-5"})
        self.assertRedirects(r, reverse("accounts:password_reset_complete"))
        self.assertTrue(self.client.login(username="asha", password="Brand-New-Pass-5"))

    def test_unknown_email_does_not_leak(self):
        from django.core import mail
        r = self.client.post(reverse("accounts:password_reset"), {"email": "ghost@example.com"})
        self.assertRedirects(r, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)
