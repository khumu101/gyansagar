from django import forms
from django.core.exceptions import ValidationError

from .models import Submission


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("text", "file")
        widgets = {"text": forms.Textarea(attrs={"rows": 5, "placeholder": "Type your answer here (optional if you attach a file)"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("text") and not cleaned.get("file") and not (self.instance.pk and self.instance.file):
            raise ValidationError("Write an answer or attach a file.")
        return cleaned


class GradeForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ("marks", "feedback")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["marks"].required = True
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_marks(self):
        marks = self.cleaned_data["marks"]
        maximum = self.instance.assignment.max_marks
        if marks < 0 or marks > maximum:
            raise ValidationError(f"Marks must be between 0 and {maximum}.")
        return marks
