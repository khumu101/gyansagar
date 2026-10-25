from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.db import transaction

from core.models import Level, Program

from . import throttle
from .models import Profile

User = get_user_model()


class StyledFormMixin:
    """Give every widget the CSS class used by static/css/extras.css."""

    def _style(self):
        for field in self.fields.values():
            css = "form-check" if isinstance(field.widget, forms.CheckboxInput) else "form-control"
            field.widget.attrs.setdefault("class", css)


def _check_level_program(cleaned):
    level, program = cleaned.get("level"), cleaned.get("program")
    if program and level and program.level_id != level.id:
        raise ValidationError({"program": "This program does not belong to the selected level."})
    if program and not level:
        cleaned["level"] = program.level
    return cleaned


def _unique_email(email, exclude_pk=None):
    email = (email or "").strip().lower()
    qs = User.objects.filter(email__iexact=email)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    if qs.exists():
        raise ValidationError("An account with this e-mail already exists.")
    return email


class SignupForm(StyledFormMixin, UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    level = forms.ModelChoiceField(Level.objects.none(), required=False,
                                   empty_label="Select your class / level (optional)", label="Class / level")
    program = forms.ModelChoiceField(Program.objects.none(), required=False,
                                     empty_label="Select your program (optional)")

    field_order = ["first_name", "last_name", "username", "email", "level", "program", "password1", "password2"]

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "last_name", "username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["level"].queryset = Level.objects.all()
        self.fields["program"].queryset = Program.objects.select_related("level")
        self.fields["first_name"].widget.attrs["autocomplete"] = "given-name"
        self.fields["last_name"].widget.attrs["autocomplete"] = "family-name"
        self.fields["username"].widget.attrs["autocomplete"] = "username"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"
        self._style()

    def clean_email(self):
        return _unique_email(self.cleaned_data.get("email"))

    def clean(self):
        cleaned = super().clean()
        return _check_level_program(cleaned)

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=True)
        Profile.objects.update_or_create(
            user=user,
            defaults={"level": self.cleaned_data.get("level"), "program": self.cleaned_data.get("program")},
        )
        return user


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.CharField(label="Username or e-mail",
                               widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}))
    remember_me = forms.BooleanField(required=False, initial=True, label="Keep me logged in")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].widget.attrs["autocomplete"] = "current-password"
        self._style()

    def clean(self):
        username = self.cleaned_data.get("username") or ""
        if username and throttle.is_locked(self.request, username):
            raise ValidationError(
                "Too many failed attempts. Please wait a few minutes and try again.", code="locked")
        try:
            cleaned = super().clean()
        except ValidationError:
            if username:
                throttle.register_failure(self.request, username)
            raise
        throttle.reset(self.request, username)
        return cleaned


class UserUpdateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["email"].required = True
        self._style()

    def clean_email(self):
        return _unique_email(self.cleaned_data.get("email"), exclude_pk=self.instance.pk)


class ProfileUpdateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("phone", "level", "program", "bio")
        widgets = {"bio": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["level"].empty_label = "Select your class / level"
        self.fields["program"].empty_label = "Select your program"
        self._style()

    def clean(self):
        return _check_level_program(super().clean())


class ResetForm(PasswordResetForm):
    """Django skips people without a password; Google-only users must be able to set one with this form too."""

    def get_users(self, email):
        return (u for u in User.objects.filter(email__iexact=email, is_active=True))
