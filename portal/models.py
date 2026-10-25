from django.conf import settings
from django.core.validators import URLValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.utils import unique_slug

HTTP_URL = [URLValidator(schemes=["http", "https"])]


class School(models.Model):
    PRIVATE, PUBLIC, COMMUNITY = "private", "public", "community"
    KIND_CHOICES = [(PRIVATE, "Private"), (PUBLIC, "Public / Government"), (COMMUNITY, "Community")]

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default=PRIVATE)
    city = models.CharField(max_length=80, help_text="City / district")
    address = models.CharField(max_length=200, blank=True)
    levels_offered = models.CharField(max_length=120, blank=True, help_text="e.g. Nursery - Class 12")
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True, validators=HTTP_URL)
    description = models.CharField(max_length=300, blank=True)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["city", "name"]

    def __str__(self):
        return f"{self.name} ({self.city})"


class BlogPost(models.Model):
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, unique=True, blank=True, help_text="Leave empty to auto-generate.")
    excerpt = models.CharField(max_length=300, blank=True)
    body = models.TextField(help_text="Plain text. Blank line = new paragraph.")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="blog_posts")
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(BlogPost, self.title, self, max_length=80)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("portal:blog_detail", args=[self.slug])


class Opportunity(models.Model):
    """Scholarships and career/job openings (same fields, two sidebar pages)."""

    SCHOLARSHIP, CAREER = "scholarship", "career"
    KIND_CHOICES = [(SCHOLARSHIP, "Scholarship"), (CAREER, "Career / Job")]

    kind = models.CharField(max_length=12, choices=KIND_CHOICES, db_index=True)
    title = models.CharField(max_length=160)
    organization = models.CharField(max_length=120, help_text="Who is offering it")
    location = models.CharField(max_length=100, blank=True)
    level = models.ForeignKey("core.Level", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="opportunities", verbose_name="Class / level (optional)")
    deadline = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    apply_url = models.URLField(blank=True, validators=HTTP_URL, help_text="Official link to apply / read more")
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["deadline", "-created_at"]
        verbose_name_plural = "opportunities"

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"

    @property
    def is_open(self):
        return self.deadline is None or self.deadline >= timezone.localdate()


class Post(models.Model):
    """Community question / discussion."""

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="community_posts")
    title = models.CharField(max_length=150)
    body = models.TextField(max_length=3000)
    level = models.ForeignKey("core.Level", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="community_posts", verbose_name="Class / level")
    subject = models.ForeignKey("core.Subject", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="community_posts")
    is_hidden = models.BooleanField(default=False, help_text="Moderation: hide from the community.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("portal:post_detail", args=[self.pk])


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="community_comments")
    body = models.TextField(max_length=1500)
    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.author} on {self.post_id}"


class TutorMessage(models.Model):
    """One question/answer with the AI Tutor (also used for the daily limit)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tutor_messages")
    subject = models.ForeignKey("core.Subject", on_delete=models.SET_NULL, null=True, blank=True)
    question = models.TextField(max_length=1000)
    answer = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user}: {self.question[:40]}"


class ContactMessage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=80)
    email = models.EmailField()
    subject = models.CharField(max_length=120)
    message = models.TextField(max_length=3000)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}: {self.subject}"
