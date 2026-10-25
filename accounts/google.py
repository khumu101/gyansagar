"""Sign in with Google (OAuth 2.0 authorization-code flow, no extra packages).

Setup: Google Cloud Console -> APIs & Services -> Credentials -> OAuth client ID (Web application)
  Authorized redirect URI:  https://YOUR-DOMAIN/accounts/google/callback/
Then set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET. The button only appears when both are set.
"""
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from .models import Profile, SocialAccount

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
TIMEOUT = 10


class GoogleError(Exception):
    """Message is safe to show to the visitor."""


def enabled():
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def authorize_url(redirect_uri, state):
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": "openid email profile", "state": state, "prompt": "select_account",
    })


def _request(req):
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        logger.warning("Google sign-in request failed: %s", exc)
        raise GoogleError("Could not reach Google. Please try again, or log in with your password.")


def fetch_profile(code, redirect_uri):
    """Exchange the one-time code for the person's Google profile (sub, email, email_verified, names)."""
    body = urllib.parse.urlencode({
        "code": code, "client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code"}).encode()
    token = _request(urllib.request.Request(TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}))
    access = token.get("access_token")
    if not access:
        raise GoogleError("Google did not accept the sign-in. Please try again.")
    return _request(urllib.request.Request(USERINFO_URL, headers={"Authorization": f"Bearer {access}"}))


def _free_username(User, email):
    base = re.sub(r"[^\w.@+-]", "", email.split("@")[0])[:28] or "user"
    name, n = base, 1
    while User.objects.filter(username__iexact=name).exists():
        n += 1
        name = f"{base}{n}"
    return name


@transaction.atomic
def get_or_create_user(info):
    """Find (or create) the Gyansagar user for a Google profile. Raises GoogleError with a visitor-safe message."""
    User = get_user_model()
    uid = str(info.get("sub") or "")
    email = (info.get("email") or "").strip().lower()
    if not uid or not email or info.get("email_verified") is not True:
        raise GoogleError("Your Google account has no verified e-mail address, so we cannot sign you in with it.")

    link = SocialAccount.objects.select_related("user").filter(provider=SocialAccount.GOOGLE, uid=uid).first()
    if link:
        user = link.user
    else:
        user = User.objects.filter(email__iexact=email).order_by("pk").first()
        if user:
            if user.is_superuser:
                raise GoogleError("Administrator accounts must log in with their password.")
            profile, _ = Profile.objects.get_or_create(user=user)
            if not profile.email_verified:
                # Someone may have registered this address without owning it: cut off whoever knows that password.
                user.set_unusable_password()
                user.save(update_fields=["password"])
        else:
            user = User(username=_free_username(User, email), email=email,
                        first_name=(info.get("given_name") or info.get("name") or "")[:150],
                        last_name=(info.get("family_name") or "")[:150])
            user.set_unusable_password()
            user.save()
        SocialAccount.objects.create(user=user, provider=SocialAccount.GOOGLE, uid=uid)

    if not user.is_active:
        raise GoogleError("This account is disabled.")
    if user.is_superuser:
        raise GoogleError("Administrator accounts must log in with their password.")
    if user.email.lower() == email:
        Profile.objects.update_or_create(user=user, defaults={"email_verified": True})
    return user
