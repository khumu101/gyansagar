import os

from django.conf import settings
from django.core.exceptions import ValidationError


def validate_resource_extension(f):
    ext = os.path.splitext(f.name)[1].lstrip(".").lower()
    if not ext:
        raise ValidationError("The file needs an extension, e.g. .pdf, .docx, .jpg.")
    if ext in settings.RESOURCE_BLOCKED_EXTENSIONS:
        raise ValidationError(f"'.{ext}' files are not allowed (programs, scripts and web pages are blocked for safety).")


def validate_resource_size(f):
    limit = settings.RESOURCE_MAX_UPLOAD_MB * 1024 * 1024
    if f.size > limit:
        raise ValidationError(f"File is too large (max {settings.RESOURCE_MAX_UPLOAD_MB} MB).")
