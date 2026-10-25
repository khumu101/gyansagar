"""E-mail verification with signed, expiring links (nothing extra is stored in the database)."""
from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

SALT = "gyansagar.email-verify"


def make_token(user):
    # the e-mail is part of the token: changing the address invalidates old links
    return signing.dumps({"u": user.pk, "e": user.email.lower()}, salt=SALT)


def read_token(token):
    """-> (user_pk, email) or None when the link is invalid / expired."""
    try:
        data = signing.loads(token, salt=SALT, max_age=settings.EMAIL_VERIFY_MAX_AGE_HOURS * 3600)
    except signing.BadSignature:
        return None
    return data.get("u"), data.get("e")


def is_verified(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, "profile", None)
    return bool(profile and profile.email_verified)


def send_verification(request, user):
    """Returns True if the e-mail was handed to the mail backend."""
    if not user.email:
        return False
    link = request.build_absolute_uri(reverse("accounts:verify_email", args=[make_token(user)]))
    body = render_to_string("accounts/verify_email.txt", {"user": user, "link": link,
                                                          "hours": settings.EMAIL_VERIFY_MAX_AGE_HOURS})
    try:
        send_mail("Verify your Gyansagar e-mail", body, None, [user.email])
    except Exception:  # never break signup because the mail server is down
        import logging
        logging.getLogger(__name__).exception("Could not send verification e-mail to user %s", user.pk)
        return False
    return True


def verified_required(view):
    """Use under @login_required. Only enforced when REQUIRE_VERIFIED_EMAIL=1."""
    from functools import wraps

    from django.contrib import messages
    from django.shortcuts import redirect

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if settings.REQUIRE_VERIFIED_EMAIL and not is_verified(request.user):
            messages.error(request, "Please verify your e-mail first (check your inbox for the link).")
            return redirect("accounts:profile")
        return view(request, *args, **kwargs)
    return wrapper
