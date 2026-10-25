import ipaddress

from django.conf import settings
from django.utils.text import slugify


def unique_slug(model, base, instance=None, max_length=50):
    """Return a slug for `base` that is unique for `model` (adds -2, -3 ... when taken)."""
    base = (slugify(base) or "item")[:max_length]
    qs = model._default_manager.all()
    if instance is not None and instance.pk:
        qs = qs.exclude(pk=instance.pk)
    slug, n = base, 2
    while qs.filter(slug=slug).exists():
        suffix = f"-{n}"
        slug = f"{base[:max_length - len(suffix)]}{suffix}"
        n += 1
    return slug


def client_ip(request):
    """The visitor's IP. Behind nginx set CLIENT_IP_HEADER=X-Client-IP (nginx overwrites it, so it can't be spoofed)."""
    header = getattr(settings, "CLIENT_IP_HEADER", "REMOTE_ADDR")
    if header and header != "REMOTE_ADDR":
        raw = request.META.get("HTTP_" + header.upper().replace("-", "_"), "").split(",")[0].strip()
        try:
            return str(ipaddress.ip_address(raw))
        except ValueError:
            pass
    return request.META.get("REMOTE_ADDR", "?")
