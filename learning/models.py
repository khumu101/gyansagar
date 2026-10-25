import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.validators import validate_resource_extension, validate_resource_size


class Quiz(models.Model):
    """A multiple-choice practice test. Each question has exactly one correct choice."""

    subject = models.ForeignKey("core.Subject", on_delete=models.CASCADE, related_name="quizzes")
    chapter = models.ForeignKey("core.Chapter", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="quizzes", help_text="Optional.")
    title = models.CharField(max_length=160)
    description = models.CharField(max_length=300, blank=True)
    pass_percent = models.PositiveSmallIntegerField(default=40, help_text="Percent needed to pass (0-100).")
    is_published = models.BooleanField(default=False, help_text="Tick when all questions are ready.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   editable=False, related_name="quizzes_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "quizzes"

    def __str__(self):
        return self.title

    def clean(self):
        if self.pass_percent > 100:
            raise ValidationError({"pass_percent": "Must be between 0 and 100."})
        if self.chapter_id and self.subject_id and self.chapter.subject_id != self.subject_id:
            raise ValidationError({"chapter": "This chapter belongs to a different subject."})

    def get_absolute_url(self):
        return reverse("learning:quiz_take", args=[self.pk])


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    explanation = models.CharField(max_length=400, blank=True, help_text="Shown after the quiz, next to the right answer.")
    order = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.text[:80]


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.text


class Attempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts")
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    score = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    percent = models.PositiveSmallIntegerField(default=0)
    passed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "quiz"])]

    def __str__(self):
        return f"{self.user} - {self.quiz} ({self.score}/{self.total})"

    def get_absolute_url(self):
        return reverse("learning:attempt_detail", args=[self.pk])


class AttemptAnswer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="+")
    choice = models.ForeignKey(Choice, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["question__order", "question_id"]


class Assignment(models.Model):
    subject = models.ForeignKey("core.Subject", on_delete=models.CASCADE, related_name="assignments")
    title = models.CharField(max_length=160)
    instructions = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    max_marks = models.PositiveSmallIntegerField(default=10)
    is_published = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   editable=False, related_name="assignments_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_at", "-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_past_due(self):
        return bool(self.due_at and timezone.now() > self.due_at)

    def get_absolute_url(self):
        return reverse("learning:assignment_detail", args=[self.pk])


def submission_upload_path(instance, filename):
    safe = os.path.basename(filename).replace(" ", "_")[:80]
    return f"submissions/{instance.assignment_id}/{uuid.uuid4().hex[:10]}_{safe}"


class Submission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions")
    text = models.TextField(blank=True)
    file = models.FileField(upload_to=submission_upload_path, blank=True,
                            validators=[validate_resource_extension, validate_resource_size])
    submitted_at = models.DateTimeField(default=timezone.now)
    marks = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    feedback = models.CharField(max_length=500, blank=True)
    graded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="+")
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [models.UniqueConstraint(fields=["assignment", "student"], name="one_submission_per_student")]

    def __str__(self):
        return f"{self.student} -> {self.assignment}"

    @property
    def is_graded(self):
        return self.marks is not None

    @property
    def is_late(self):
        return bool(self.assignment.due_at and self.submitted_at > self.assignment.due_at)

    @property
    def filename(self):
        base = os.path.basename(self.file.name) if self.file else ""
        return base.split("_", 1)[1] if "_" in base else base
