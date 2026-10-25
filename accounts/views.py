from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

import secrets

from django.http import Http404

from . import google, throttle, verification
from .forms import LoginForm, ProfileUpdateForm, SignupForm, UserUpdateForm
from .models import Profile

User = get_user_model()
BACKEND = "accounts.backends.EmailOrUsernameBackend"


def _safe_next(request):
    """Return the ?next= target only if it points back to this site (prevents open redirects)."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    ok = url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                         require_https=request.is_secure())
    return target if target and ok else ""


def signup(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    next_url = _safe_next(request)
    form = SignupForm(request.POST or None)
    if request.method == "POST" and not throttle.hit(request, "signup", settings.SIGNUP_MAX_PER_HOUR):
        form.add_error(None, "Too many sign-ups from your network. Please try again in an hour.")
        return render(request, "accounts/signup.html", {"form": form, "next": next_url}, status=429)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        if verification.send_verification(request, user):
            messages.info(request, "We sent a verification link to your e-mail.")
        if settings.SIGNUP_AUTO_LOGIN:
            login(request, user, backend=BACKEND)
            return redirect(next_url or settings.LOGIN_REDIRECT_URL)
        messages.success(request, "Account created! Please log in.")
        login_url = reverse("accounts:login")
        return redirect(f"{login_url}?next={next_url}" if next_url else login_url)
    return render(request, "accounts/signup.html", {"form": form, "next": next_url})


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(0)  # session ends when the browser closes
        return response


class PasswordResetView(auth_views.PasswordResetView):
    """Same as Django's, but limited per IP so nobody can spam people's inboxes."""

    def post(self, request, *args, **kwargs):
        if not throttle.hit(request, "pwreset", settings.PASSWORD_RESET_MAX_PER_HOUR):
            form = self.get_form()
            form.add_error(None, "Too many reset requests. Please try again in an hour.")
            response = self.render_to_response(self.get_context_data(form=form))
            response.status_code = 429
            return response
        return super().post(request, *args, **kwargs)


@login_required
def profile(request):
    prof, _ = Profile.objects.get_or_create(user=request.user)
    user_form = UserUpdateForm(request.POST or None, instance=request.user)
    profile_form = ProfileUpdateForm(request.POST or None, instance=prof)
    if request.method == "POST":
        if user_form.is_valid() & profile_form.is_valid():  # '&' so both forms show their errors
            email_changed = "email" in user_form.changed_data
            user_form.save()
            profile_form.save()
            if email_changed:
                Profile.objects.filter(pk=prof.pk).update(email_verified=False)
                verification.send_verification(request, request.user)
                messages.info(request, "E-mail changed - we sent a new verification link.")
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"user_form": user_form, "profile_form": profile_form})


def verify_email(request, token):
    data = verification.read_token(token)
    user = User.objects.filter(pk=data[0]).first() if data else None
    if not user or user.email.lower() != data[1]:
        messages.error(request, "This verification link is invalid or has expired. Please request a new one.")
        return redirect("accounts:profile" if request.user.is_authenticated else "accounts:login")
    Profile.objects.update_or_create(user=user, defaults={"email_verified": True})
    messages.success(request, "Thank you! Your e-mail is verified.")
    return redirect("accounts:profile" if request.user.is_authenticated else "accounts:login")


@login_required
@require_POST
def resend_verification(request):
    if verification.is_verified(request.user):
        messages.info(request, "Your e-mail is already verified.")
    elif not throttle.hit(request, "verify-resend", 5):
        messages.error(request, "Too many requests. Please try again in an hour.")
    elif verification.send_verification(request, request.user):
        messages.success(request, "Verification link sent. Check your inbox (and spam folder).")
    else:
        messages.error(request, "We could not send the e-mail right now. Please try again later.")
    return redirect(_safe_next(request) or "accounts:profile")


# ------------------------------------------------------------------ Sign in with Google
def _google_redirect_uri(request):
    return settings.GOOGLE_REDIRECT_URI or request.build_absolute_uri(reverse("accounts:google_callback"))


def google_login(request):
    if not google.enabled():
        raise Http404("Google sign-in is not set up.")
    state = secrets.token_urlsafe(32)
    request.session["google_state"] = state
    request.session["google_next"] = _safe_next(request)
    return redirect(google.authorize_url(_google_redirect_uri(request), state))


def google_callback(request):
    if not google.enabled():
        raise Http404("Google sign-in is not set up.")
    expected = request.session.pop("google_state", "")
    next_url = request.session.pop("google_next", "")
    given = request.GET.get("state", "")
    if request.GET.get("error"):
        messages.error(request, "Google sign-in was cancelled.")
        return redirect("accounts:login")
    if not expected or not secrets.compare_digest(expected, given) or not request.GET.get("code"):
        messages.error(request, "The Google sign-in session expired. Please try again.")
        return redirect("accounts:login")
    if not throttle.hit(request, "google", 30):
        messages.error(request, "Too many sign-in attempts. Please try again later.")
        return redirect("accounts:login")
    try:
        info = google.fetch_profile(request.GET["code"], _google_redirect_uri(request))
        user = google.get_or_create_user(info)
    except google.GoogleError as exc:
        messages.error(request, str(exc))
        return redirect("accounts:login")
    login(request, user, backend=BACKEND)
    messages.success(request, f"Welcome, {user.first_name or user.get_username()}!")
    return redirect(next_url or settings.LOGIN_REDIRECT_URL)
