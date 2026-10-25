from django import forms

from core.models import Level, Subject

from .models import Comment, ContactMessage, Post


class _Styled:
    def _style(self):
        for f in self.fields.values():
            f.widget.attrs.setdefault("class", "form-control")


class PostForm(_Styled, forms.ModelForm):
    class Meta:
        model = Post
        fields = ("title", "level", "subject", "body")
        widgets = {"body": forms.Textarea(attrs={"rows": 6, "maxlength": 3000})}
        labels = {"body": "Your question / discussion"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["level"].queryset = Level.objects.all()
        self.fields["level"].empty_label = "Class / level (optional)"
        self.fields["subject"].queryset = Subject.objects.select_related("level", "program")
        self.fields["subject"].empty_label = "Subject (optional)"
        self.fields["subject"].label_from_instance = lambda s: f"{s.level.name} · {s.name}"
        self._style()


class CommentForm(_Styled, forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("body",)
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "maxlength": 1500, "placeholder": "Write a reply…"})}
        labels = {"body": ""}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class ContactForm(_Styled, forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ("name", "email", "subject", "message")
        widgets = {"message": forms.Textarea(attrs={"rows": 5, "maxlength": 3000})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class TutorForm(_Styled, forms.Form):
    question = forms.CharField(max_length=1000, label="Ask your question",
                               widget=forms.Textarea(attrs={"rows": 3, "maxlength": 1000,
                                                            "placeholder": "e.g. Explain Newton's second law with an example"}))
    subject = forms.ModelChoiceField(Subject.objects.none(), required=False, empty_label="Subject (optional — helps the tutor)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subject"].queryset = Subject.objects.select_related("level", "program")
        self.fields["subject"].label_from_instance = lambda s: f"{s.level.name} · {s.name}"
        self._style()

    def clean_question(self):
        q = self.cleaned_data["question"].strip()
        if len(q) < 3:
            raise forms.ValidationError("Please write a longer question.")
        return q
