from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import Level, Program, Subject, Chapter, Resource, ResourceReport


class ChapterInline(admin.TabularInline):
    model = Chapter
    extra = 1


@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ("name", "subtitle", "category", "order")
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ("order",)
    search_fields = ("name",)


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "duration", "order")
    prepopulated_fields = {"slug": ("name",)}
    list_filter = ("level",)
    search_fields = ("name",)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "level", "program", "semester", "code", "chapters_count", "books_count", "videos_count")
    prepopulated_fields = {"slug": ("name",)}
    list_filter = ("level", "program")
    search_fields = ("name", "code", "description")
    readonly_fields = ("books_count", "videos_count")
    inlines = [ChapterInline]


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "order", "topics_count", "activities_count")
    list_filter = ("subject",)
    search_fields = ("title", "subject__name")


class DataSelect(forms.Select):
    """<select> whose options carry data-* attributes so a little JS can filter them (see resource_cascade.js)."""

    def __init__(self, *args, data_attrs=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_attrs = data_attrs or {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        obj = getattr(value, "instance", None)
        if obj is not None:
            for attr, getter in self.data_attrs.items():
                option["attrs"][f"data-{attr}"] = getter(obj) or ""
        return option


class SubjectChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"Sem {obj.semester} · {obj.name}" if obj.semester else obj.name


class ChapterChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"Ch.{obj.order} {obj.title}"


class ResourceAdminForm(forms.ModelForm):
    """Upload form: Class -> Faculty/Program -> Subject -> Chapter (each list filters the next one)."""

    level = forms.ModelChoiceField(
        Level.objects.all(), required=False, label="Class / level",
        help_text="Step 1 — which class is this for? (Only used to filter the lists below.)")
    program = forms.ModelChoiceField(
        Program.objects.select_related("level"), required=False, label="Faculty / program",
        widget=DataSelect(data_attrs={"level": lambda o: o.level_id}),
        help_text="Step 2 — for degrees (BSc CSIT, BBS ...). Leave empty for school classes.")
    subject = SubjectChoiceField(
        Subject.objects.select_related("level", "program"), label="Subject",
        widget=DataSelect(data_attrs={"level": lambda o: o.level_id, "program": lambda o: o.program_id}),
        help_text="Step 3 — which subject is this material for?")
    chapter = ChapterChoiceField(
        Chapter.objects.select_related("subject"), required=False, label="Chapter",
        widget=DataSelect(data_attrs={"subject": lambda o: o.subject_id}),
        help_text="Step 4 (optional) — pick the chapter, or leave empty for the whole subject.")

    class Meta:
        model = Resource
        fields = "__all__"

    class Media:
        js = ("js/resource_cascade.js",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.subject_id:
            self.initial.setdefault("level", self.instance.subject.level_id)
            self.initial.setdefault("program", self.instance.subject.program_id)

    def clean(self):
        cleaned = super().clean()
        subject, level, program = cleaned.get("subject"), cleaned.get("level"), cleaned.get("program")
        if subject and level and subject.level_id != level.id:
            self.add_error("level", f"'{subject.name}' belongs to {subject.level.name}, not {level.name}.")
        if subject and program and subject.program_id != program.id:
            self.add_error("program", f"'{subject.name}' is not part of {program.name}.")
        return cleaned


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    """Upload notes / books / videos / old questions here; they show up on the subject page automatically."""

    list_display = ("title", "kind", "class_name", "faculty", "subject", "chapter", "is_published",
                    "download_count", "uploaded_by", "created_at")
    list_filter = ("kind", "is_published", "subject__level", "subject__program")
    list_select_related = ("subject__level", "subject__program", "chapter", "uploaded_by")
    search_fields = ("title", "description", "subject__name")
    form = ResourceAdminForm
    readonly_fields = ("download_count", "uploaded_by", "created_at", "updated_at")
    date_hierarchy = "created_at"
    actions = ["make_published", "make_unpublished"]
    fieldsets = (
        ("Where does it belong?", {"fields": ("level", "program", "subject", "chapter")}),
        ("What is it?", {"fields": ("kind", "title", "description")}),
        ("Content (file OR link OR typed text)", {"fields": ("file", "external_url", "content")}),
        ("Extra info", {"fields": ("year", "scheduled_at", "is_published")}),
        ("Stats", {"fields": ("download_count", "uploaded_by", "created_at", "updated_at")}),
    )

    @admin.display(description="Class", ordering="subject__level__order")
    def class_name(self, obj):
        return obj.subject.level.name

    @admin.display(description="Faculty / program", ordering="subject__program__name")
    def faculty(self, obj):
        return obj.subject.program.name if obj.subject.program_id else "-"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)

    def _set_published(self, request, queryset, value):
        subjects = list(Subject.objects.filter(resources__in=queryset).distinct())
        updated = queryset.update(is_published=value)
        for subject in subjects:  # queryset.update() skips signals, so refresh counts here
            subject.refresh_counts()
        self.message_user(request, f"{updated} resource(s) {'published' if value else 'hidden'}.")

    @admin.action(description="Publish selected resources")
    def make_published(self, request, queryset):
        self._set_published(request, queryset, True)

    @admin.action(description="Hide (unpublish) selected resources")
    def make_unpublished(self, request, queryset):
        self._set_published(request, queryset, False)


@admin.register(ResourceReport)
class ResourceReportAdmin(admin.ModelAdmin):
    list_display = ("resource", "reason", "user", "note", "resolved", "created_at")
    list_filter = ("resolved", "reason")
    search_fields = ("resource__title", "user__username", "note")
    list_select_related = ("resource", "user")
    actions = ["mark_resolved", "hide_resources", "restore_resources"]

    @admin.action(description="Mark selected reports as resolved (file stays as it is)")
    def mark_resolved(self, request, queryset):
        self.message_user(request, f"{queryset.update(resolved=True)} report(s) resolved.")

    @admin.action(description="Hide the reported files from students and resolve")
    def hide_resources(self, request, queryset):
        for resource in Resource.objects.filter(reports__in=queryset).distinct():
            resource.is_published = False
            resource.save(update_fields=["is_published", "updated_at"])
        self.message_user(request, f"{queryset.update(resolved=True)} report(s) resolved, files hidden.")

    @admin.action(description="File is fine: show it again and resolve")
    def restore_resources(self, request, queryset):
        for resource in Resource.objects.filter(reports__in=queryset).distinct():
            resource.is_published = True
            resource.save(update_fields=["is_published", "updated_at"])
        self.message_user(request, f"{queryset.update(resolved=True)} report(s) resolved, files visible.")
