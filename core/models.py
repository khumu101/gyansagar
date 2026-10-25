import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.urls import reverse
from django.utils.text import get_valid_filename, slugify

from .utils import unique_slug
from .validators import validate_resource_extension, validate_resource_size


class Level(models.Model):
    """A stage in the Nursery-to-PhD journey (Nursery, Class 1, Bachelor, PhD, ...)."""

    SCHOOL = "school"
    DEGREE = "degree"
    CATEGORY_CHOICES = [(SCHOOL, "School"), (DEGREE, "Degree")]

    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True, blank=True, help_text="Leave empty to auto-generate from the name.")
    subtitle = models.CharField(max_length=50, help_text="e.g. '3+ Years' or 'Undergraduate'")
    icon = models.CharField(max_length=10, help_text="Emoji shown on the level chip")
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, default=SCHOOL)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Level, self.name, self)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("core:level_detail", args=[self.slug])


class Program(models.Model):
    """A degree program offered under a Level, e.g. BSc CSIT under Bachelor."""

    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name="programs")
    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True, blank=True, help_text="Leave empty to auto-generate from the name.")
    icon = models.CharField(max_length=10, default="🎓")
    duration = models.CharField(max_length=30, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Program, self.name, self)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("core:program_detail", args=[self.slug])


class Subject(models.Model):
    """A subject page — the unit users land on with all its resources."""

    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name="subjects")
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="subjects", null=True, blank=True)
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True, blank=True,
                            help_text="Leave empty to auto-generate (e.g. class-four-english).")
    description = models.CharField(max_length=200, blank=True)
    # Kept in sync automatically from uploaded Resources (see core/signals.py).
    books_count = models.PositiveIntegerField(default=0, help_text="Auto-updated from uploaded Notes + Books.")
    videos_count = models.PositiveIntegerField(default=0, help_text="Auto-updated from uploaded Videos.")
    semester = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Semester / year number for degree programs (e.g. 1 to 8). Used for ordering.")
    code = models.CharField(max_length=20, blank=True, help_text="Optional course code, e.g. CSC110.")

    class Meta:
        ordering = ["semester", "name"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.program_id and self.level_id and self.program.level_id != self.level_id:
            raise ValidationError({"program": "This program does not belong to the selected level."})

    def save(self, *args, **kwargs):
        if not self.slug:
            owner = self.program.slug if self.program_id else self.level.slug
            self.slug = unique_slug(Subject, f"{owner}-{self.name}", self, max_length=80)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("core:subject_detail", args=[self.slug])

    def refresh_counts(self):
        """Recalculate books_count / videos_count from published resources."""
        published = self.resources.filter(is_published=True)
        Subject.objects.filter(pk=self.pk).update(
            books_count=published.filter(kind__in=[Resource.NOTES, Resource.BOOKS]).count(),
            videos_count=published.filter(kind=Resource.VIDEOS).count(),
        )

    @property
    def chapters_count(self):
        return self.chapters.count()

    @property
    def topics_count(self):
        return sum(c.topics_count for c in self.chapters.all())

    @property
    def activities_count(self):
        return sum(c.activities_count for c in self.chapters.all())


class Chapter(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="chapters")
    order = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=120)
    description = models.CharField(max_length=200, blank=True)
    topics_count = models.PositiveIntegerField(default=0)
    activities_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.subject.name} — Ch.{self.order} {self.title}"


def resource_upload_path(instance, filename):
    """resources/<kind>/<subject id>/<random>_<clean name>  (no collisions, no path tricks)."""
    safe = get_valid_filename(os.path.basename(filename)) or "file"
    return f"resources/{instance.kind}/{instance.subject_id}/{uuid.uuid4().hex[:10]}_{safe}"


class Resource(models.Model):
    """Anything a teacher/admin uploads for a subject: notes, books, videos, old questions, ...

    `kind` values are identical to the tab keys on the subject page, so each tab lists its own kind.
    """

    NOTES = "notes"
    BOOKS = "books"
    QUESTION_BANKS = "question-banks"
    VIDEOS = "videos"
    LIVE_CLASSES = "live-classes"
    GAMES = "games"
    QUIZZES = "quizzes"
    WORKSHEETS = "worksheets"
    ACTIVITIES = "activities"
    KIND_CHOICES = [
        (NOTES, "Notes"),
        (BOOKS, "Books"),
        (QUESTION_BANKS, "Question Banks / Old Questions"),
        (VIDEOS, "Videos"),
        (LIVE_CLASSES, "Live Classes"),
        (GAMES, "Games"),
        (QUIZZES, "Quizzes"),
        (WORKSHEETS, "Worksheets"),
        (ACTIVITIES, "Activities"),
    ]

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="resources")
    chapter = models.ForeignKey(Chapter, on_delete=models.SET_NULL, null=True, blank=True, related_name="resources",
                                help_text="Optional. Leave empty if it covers the whole subject.")
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=NOTES, db_index=True)
    title = models.CharField(max_length=160)
    description = models.CharField(max_length=300, blank=True)
    file = models.FileField(upload_to=resource_upload_path, blank=True,
                            validators=[validate_resource_extension, validate_resource_size],
                            help_text="Upload a file (PDF, Word, PowerPoint, image, video, ...) OR give a link below.")
    external_url = models.URLField(blank=True, validators=[URLValidator(schemes=["http", "https"])],
                                   help_text="e.g. YouTube video, Google Drive file, Zoom/Meet link.")
    content = models.TextField(blank=True, help_text="Or type / paste the text here (e.g. old questions, short notes). "
                                                      "Students read it right on the page.")
    year = models.PositiveSmallIntegerField(null=True, blank=True,
                                            help_text="Exam year (useful for old questions), e.g. 2080.")
    scheduled_at = models.DateTimeField(null=True, blank=True, help_text="Start time (live classes).")
    is_published = models.BooleanField(default=True, help_text="Untick to hide it from students.")
    download_count = models.PositiveIntegerField(default=0, editable=False)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    editable=False, related_name="uploaded_resources")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["chapter__order", "-created_at"]
        indexes = [models.Index(fields=["subject", "kind", "is_published"])]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"

    def clean(self):
        super().clean()
        errors = {}
        if not self.file and not self.external_url and not self.content.strip():
            errors["external_url"] = "Upload a file, provide a link, or type the text (at least one is required)."
        if self.chapter_id and self.subject_id and self.chapter.subject_id != self.subject_id:
            errors["chapter"] = "This chapter belongs to a different subject."
        if self.kind == self.LIVE_CLASSES:
            if not self.external_url:
                errors["external_url"] = "Live classes need a join link (Zoom / Meet / YouTube Live)."
            if not self.scheduled_at:
                errors["scheduled_at"] = "Live classes need a start time."
        if errors:
            raise ValidationError(errors)

    ICONS = {
        "notes": "📝", "books": "📚", "question-banks": "❓", "videos": "▶️", "live-classes": "🎥",
        "games": "🎮", "quizzes": "🧠", "worksheets": "🗒️", "activities": "🧩",
    }

    @property
    def icon(self):
        return self.ICONS.get(self.kind, "📄")

    PREVIEW = {
        "pdf": {"PDF"},
        "image": {"PNG", "JPG", "JPEG", "GIF", "WEBP"},
        "video": {"MP4", "WEBM"},
        "audio": {"MP3", "OGG", "WAV", "M4A"},
        "text": {"TXT"},
    }

    @property
    def preview_kind(self):
        """What the viewer page can show right in the browser: pdf / image / video / audio / text, or '' (download only)."""
        if self.file:
            for kind, extensions in self.PREVIEW.items():
                if self.extension in extensions:
                    return kind
            return ""
        return "text" if self.content.strip() else ""

    @property
    def is_text_only(self):
        return not self.file and not self.external_url and bool(self.content.strip())

    @property
    def is_external(self):
        return not self.file and bool(self.external_url)

    @property
    def action_label(self):
        if self.kind == self.LIVE_CLASSES:
            return "Join"
        if self.kind == self.VIDEOS:
            return "Watch"
        if self.preview_kind:
            return "View"
        return "Open" if self.is_external else "Download"

    @property
    def filename(self):
        """Original filename without the random upload prefix."""
        if not self.file:
            return ""
        base = os.path.basename(self.file.name)
        return base.split("_", 1)[1] if "_" in base else base

    @property
    def extension(self):
        return os.path.splitext(self.filename)[1].lstrip(".").upper()

    @property
    def size_display(self):
        try:
            size = self.file.size if self.file else 0
        except (OSError, ValueError):
            return ""
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024

    def get_open_url(self):
        return reverse("core:resource_open", args=[self.pk])

    def get_download_url(self):
        return reverse("core:resource_open", args=[self.pk]) + "?dl=1"

    def get_view_url(self):
        return reverse("core:resource_view", args=[self.pk])

    def get_primary_url(self):
        """Where the main button goes: the viewer page when we can preview it, otherwise straight to the file/link."""
        return self.get_view_url() if self.preview_kind else self.get_open_url()


class ResourceReport(models.Model):
    """A student says 'this file is wrong / broken / copyrighted'. Enough reports hide the file until an admin checks it."""

    WRONG, BROKEN, COPYRIGHT, SPAM, OTHER = "wrong", "broken", "copyright", "spam", "other"
    REASON_CHOICES = [
        (WRONG, "Wrong class / subject / content"), (BROKEN, "File does not open"),
        (COPYRIGHT, "Copyright problem"), (SPAM, "Spam / inappropriate"), (OTHER, "Other"),
    ]

    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="reports")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="resource_reports")
    reason = models.CharField(max_length=12, choices=REASON_CHOICES, default=WRONG)
    note = models.CharField(max_length=300, blank=True)
    resolved = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["resolved", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["resource", "user"], name="one_report_per_user_resource")]

    def __str__(self):
        return f"{self.get_reason_display()} - {self.resource.title}"
