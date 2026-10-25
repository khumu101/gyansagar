from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import google
from accounts.models import SocialAccount

User = get_user_model()
CONFIGURED = dict(GOOGLE_CLIENT_ID="cid.apps.googleusercontent.com", GOOGLE_CLIENT_SECRET="secret")


def profile(**kw):
    base = {"sub": "1234567890", "email": "Asha.Sharma@Gmail.com", "email_verified": True,
            "given_name": "Asha", "family_name": "Sharma", "name": "Asha Sharma"}
    base.update(kw)
    return base


@override_settings(**CONFIGURED)
class GoogleLoginTests(TestCase):
    def start(self, **params):
        r = self.client.get(reverse("accounts:google_login"), params)
        state = self.client.session["google_state"]
        return r, state

    def callback(self, info, state=None, **extra):
        if state is None:
            _, state = self.start(**extra)
        with mock.patch("accounts.google.fetch_profile", return_value=info) as fetch:
            r = self.client.get(reverse("accounts:google_callback"), {"code": "abc", "state": state})
        return r, fetch

    # ---- visibility
    @override_settings(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="")
    def test_disabled_without_keys(self):
        self.assertEqual(self.client.get(reverse("accounts:google_login")).status_code, 404)
        self.assertEqual(self.client.get(reverse("accounts:google_callback")).status_code, 404)
        self.assertNotContains(self.client.get(reverse("accounts:login")), "Continue with Google")

    def test_button_on_login_and_signup(self):
        self.assertContains(self.client.get(reverse("accounts:login")), "Continue with Google")
        self.assertContains(self.client.get(reverse("accounts:signup")), "Continue with Google")

    # ---- start
    def test_start_redirects_to_google_with_state(self):
        r, state = self.start()
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?"))
        self.assertIn(f"state={state}", r["Location"])
        self.assertIn("redirect_uri=http%3A%2F%2Ftestserver%2Faccounts%2Fgoogle%2Fcallback%2F", r["Location"])

    # ---- callback safety
    def test_wrong_or_missing_state_rejected(self):
        self.start()
        with mock.patch("accounts.google.fetch_profile") as fetch:
            r = self.client.get(reverse("accounts:google_callback"), {"code": "abc", "state": "forged"})
        self.assertRedirects(r, reverse("accounts:login"))
        fetch.assert_not_called()
        self.assertEqual(User.objects.count(), 0)

    def test_state_is_single_use(self):
        r, fetch = self.callback(profile())
        self.assertEqual(User.objects.count(), 1)
        self.client.logout()
        with mock.patch("accounts.google.fetch_profile") as again:
            self.client.get(reverse("accounts:google_callback"), {"code": "abc", "state": self.client.session.get("google_state", "x")})
        again.assert_not_called()

    def test_user_cancelled(self):
        self.start()
        r = self.client.get(reverse("accounts:google_callback"), {"error": "access_denied"})
        self.assertRedirects(r, reverse("accounts:login"))

    def test_google_unreachable_shows_message(self):
        _, state = self.start()
        with mock.patch("accounts.google.fetch_profile", side_effect=google.GoogleError("Could not reach Google.")):
            r = self.client.get(reverse("accounts:google_callback"), {"code": "abc", "state": state}, follow=True)
        self.assertContains(r, "Could not reach Google.")

    # ---- account creation / linking
    def test_new_user_created_logged_in_and_verified(self):
        r, _ = self.callback(profile())
        self.assertRedirects(r, reverse("core:home"), fetch_redirect_response=False)
        user = User.objects.get()
        self.assertEqual((user.email, user.first_name, user.last_name), ("asha.sharma@gmail.com", "Asha", "Sharma"))
        self.assertEqual(user.username, "asha.sharma")
        self.assertFalse(user.has_usable_password())
        self.assertTrue(user.profile.email_verified)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertEqual(SocialAccount.objects.get().uid, "1234567890")

    def test_username_collision_gets_suffix(self):
        User.objects.create_user("asha.sharma", "someone@else.com", "abc123")
        self.callback(profile())
        self.assertTrue(User.objects.filter(username="asha.sharma2", email="asha.sharma@gmail.com").exists())

    def test_existing_verified_account_is_linked(self):
        user = User.objects.create_user("asha", "asha.sharma@gmail.com", "abc123")
        user.profile.email_verified = True
        user.profile.save()
        self.callback(profile())
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(SocialAccount.objects.get().user_id, user.pk)
        user.refresh_from_db()
        self.assertTrue(user.has_usable_password())  # real owner keeps their password

    def test_squatted_unverified_account_loses_its_password(self):
        squatter = User.objects.create_user("squat", "asha.sharma@gmail.com", "abc123")  # never verified the e-mail
        self.callback(profile())
        squatter.refresh_from_db()
        self.assertFalse(squatter.has_usable_password())
        self.assertTrue(squatter.profile.email_verified)
        self.assertFalse(self.client.login(username="squat", password="abc123"))

    def test_returning_user_matched_by_google_id_even_if_email_changed(self):
        self.callback(profile())
        self.client.logout()
        user = User.objects.get()
        User.objects.filter(pk=user.pk).update(email="new@example.com")
        self.callback(profile(email="asha.sharma@gmail.com"))
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))

    def test_unverified_google_email_refused(self):
        r, _ = self.callback(profile(email_verified=False))
        self.assertEqual(User.objects.count(), 0)
        self.assertRedirects(r, reverse("accounts:login"))

    def test_missing_email_refused(self):
        self.callback(profile(email=""))
        self.assertEqual(User.objects.count(), 0)

    def test_superuser_cannot_be_taken_over_by_email_match(self):
        User.objects.create_superuser("root", "asha.sharma@gmail.com", "abc123")
        self.callback(profile())
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_inactive_user_refused(self):
        User.objects.create_user("gone", "asha.sharma@gmail.com", "abc123", is_active=False)
        self.callback(profile())
        self.assertNotIn("_auth_user_id", self.client.session)

    # ---- redirects
    def test_next_is_honoured_and_open_redirect_blocked(self):
        r, _ = self.callback(profile(), next="/learn/")
        self.assertEqual(r["Location"], "/learn/")
        self.client.logout()
        r, _ = self.callback(profile(sub="999", email="b@gmail.com"), next="https://evil.example.com/")
        self.assertEqual(r["Location"], reverse("core:home"))

    def test_password_reset_lets_google_user_set_a_password(self):
        self.callback(profile())
        self.client.logout()
        from django.core import mail
        self.client.post(reverse("accounts:password_reset"), {"email": "asha.sharma@gmail.com"})
        self.assertEqual(len(mail.outbox), 1)
