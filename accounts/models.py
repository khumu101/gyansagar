from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


class Profile(models.Model):
    """Extra info for every user (created automatically with the user)."""

    STUDENT = "student"
    TEACHER = "teacher"
    ROLE_CHOICES = [(STUDENT, "Student"), (TEACHER, "Teacher")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=STUDENT,
                            help_text="Teachers are set by an admin (also add them to the 'Teachers' group + Staff).")
    phone = models.CharField(
        max_length=20, blank=True,
        validators=[RegexValidator(r"^\+?[0-9][0-9\- ]{6,18}$", "Enter a valid phone number.")],
    )
    level = models.ForeignKey("core.Level", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="students", verbose_name="Class / level")
    program = models.ForeignKey("core.Program", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="students")
    bio = models.CharField(max_length=300, blank=True)
    email_verified = models.BooleanField(default=False, help_text="Set automatically when the person clicks the link in the e-mail.")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"


class SocialAccount(models.Model):
    """Links a Gyansagar user to their Google account (Google's permanent user id, not the e-mail)."""

    GOOGLE = "google"
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_accounts")
    provider = models.CharField(max_length=20, default=GOOGLE)
    uid = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "uid"], name="unique_social_uid")]

    def __str__(self):
        return f"{self.provider}:{self.uid} -> {self.user}"
