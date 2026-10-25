from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Assignment, Attempt, Choice, Question, Quiz, Submission


class OwnContentMixin:
    """Teachers only see/edit what they created; superusers see everything."""

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(created_by=request.user)

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 3
    fields = ("order", "text", "explanation")
    show_change_link = True  # open the question to add its answer choices


class ChoiceFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        live = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        if not live:
            return
        if len(live) < 2:
            raise ValidationError("Add at least 2 choices.")
        if sum(1 for f in live if f.cleaned_data.get("is_correct")) != 1:
            raise ValidationError("Tick exactly ONE choice as the correct answer.")


class ChoiceInline(admin.TabularInline):
    model = Choice
    formset = ChoiceFormSet
    extra = 4


@admin.register(Quiz)
class QuizAdmin(OwnContentMixin, admin.ModelAdmin):
    list_display = ("title", "subject", "question_count", "pass_percent", "is_published", "created_at")
    list_filter = ("is_published", "subject__level")
    search_fields = ("title", "subject__name")
    autocomplete_fields = ("subject",)
    inlines = [QuestionInline]

    @admin.display(description="Questions")
    def question_count(self, obj):
        return obj.questions.count()


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "quiz", "order")
    list_filter = ("quiz",)
    search_fields = ("text",)
    inlines = [ChoiceInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("quiz")
        return qs if request.user.is_superuser else qs.filter(quiz__created_by=request.user)


@admin.register(Assignment)
class AssignmentAdmin(OwnContentMixin, admin.ModelAdmin):
    list_display = ("title", "subject", "due_at", "max_marks", "is_published")
    list_filter = ("is_published", "subject__level")
    search_fields = ("title", "subject__name")
    autocomplete_fields = ("subject",)


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "quiz", "score", "total", "percent", "passed", "created_at")
    list_filter = ("passed", "quiz")
    search_fields = ("user__username", "quiz__title")
    list_select_related = ("user", "quiz")


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("student", "assignment", "submitted_at", "marks", "graded_by")
    list_filter = ("assignment",)
    search_fields = ("student__username", "assignment__title")
    list_select_related = ("student", "assignment")
