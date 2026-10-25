from django import forms

from .models import ResourceReport


class ReportForm(forms.ModelForm):
    class Meta:
        model = ResourceReport
        fields = ("reason", "note")
        widgets = {"note": forms.TextInput(attrs={"placeholder": "Tell us more (optional)"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
