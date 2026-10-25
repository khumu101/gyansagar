import logging
import mimetypes
from itertools import groupby
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, F, Prefetch, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import content_disposition_header
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_safe

from accounts import throttle

logger = logging.getLogger(__name__)

from .forms import ReportForm
from .models import Level, Program, Subject, Chapter, Resource, ResourceReport

POPULAR_CATEGORIES = [
    {"icon": "📝", "name": "Notes & Books", "subtitle": "Study Materials"},
    {"icon": "📄", "name": "Old Questions", "subtitle": "Past Year Papers"},
    {"icon": "▶️", "name": "Videos", "subtitle": "Watch & Learn"},
    {"icon": "🎥", "name": "Live Classes", "subtitle": "Join Live Sessions"},
    {"icon": "❓", "name": "Quizzes", "subtitle": "Test Your Knowledge"},
    {"icon": "🎮", "name": "Games", "subtitle": "Learn by Playing"},
    {"icon": "🤖", "name": "AI Tutor", "subtitle": "Learn with AI"},
]

WHY_GYANSAGAR = [
    {"icon": "📦", "title": "All in One Platform", "desc": "Everything you need in one place"},
    {"icon": "✅", "title": "Quality Content", "desc": "Curated by experts and teachers"},
    {"icon": "⏱️", "title": "Learn at Your Pace", "desc": "Study anytime, anywhere"},
    {"icon": "📈", "title": "Track Progress", "desc": "Monitor your learning and grow"},
    {"icon": "🏆", "title": "Trusted by Learners", "desc": "Joined by thousands of happy students"},
    {"icon": "🔒", "title": "Secure & Safe", "desc": "Your data is always protected"},
]

SUBJECT_TABS = [
    ("overview", "Overview", "📋"),
    ("syllabus", "Syllabus", "📖"),
    ("notes", "Notes", "📝"),
    ("books", "Books", "📚"),
    ("question-banks", "Question Banks", "❓"),
    ("videos", "Videos", "▶️"),
    ("live-classes", "Live Classes", "🎥"),
    ("games", "Games", "🎮"),
    ("quizzes", "Quizzes", "❓"),
    ("worksheets", "Worksheets", "🗒️"),
    ("activities", "Activities", "🧩"),
]

# Tabs that list uploaded Resources (overview + syllabus use the chapter list instead).
RESOURCE_TABS = {key: label for key, label, _ in SUBJECT_TABS if key not in ("overview", "syllabus")}
# Files that are safe to show in the browser; everything else is downloaded.
INLINE_EXTENSIONS = {"PDF", "PNG", "JPG", "JPEG", "GIF", "WEBP", "MP4", "WEBM", "MP3", "OGG", "WAV", "M4A", "TXT"}
TEXT_PREVIEW_LIMIT = 300 * 1024  # bytes of a .txt file shown on the page


# Sidebar / category sections -> (resource kind, title, icon, blurb)
SECTIONS = {
    "notes": (Resource.NOTES, "Notes", "📝", "Chapter-wise notes uploaded by teachers."),
    "old-questions": (Resource.QUESTION_BANKS, "Old Questions", "📄", "Past exam papers and question banks."),
    "books": (Resource.BOOKS, "Books", "📚", "Digital library of textbooks and reference books."),
    "videos": (Resource.VIDEOS, "Videos", "▶️", "Video lectures and tutorials."),
    "live-classes": (Resource.LIVE_CLASSES, "Live Classes", "🎥", "Upcoming and recent live sessions."),
    "quizzes": (Resource.QUIZZES, "Quizzes", "❓", "Test your knowledge."),
    "games": (Resource.GAMES, "Games", "🎮", "Learn by playing."),
    "worksheets": (Resource.WORKSHEETS, "Worksheets", "🗒️", "Printable practice worksheets."),
    "activities": (Resource.ACTIVITIES, "Activities", "🧩", "Hands-on learning activities."),
}
CATEGORY_LINKS = {  # home "Popular Categories" name -> url name + args
    "Notes & Books": ("core:browse", ["notes"]),
    "Old Questions": ("core:browse", ["old-questions"]),
    "Videos": ("core:browse", ["videos"]),
    "Live Classes": ("core:browse", ["live-classes"]),
    "Quizzes": ("core:browse", ["quizzes"]),
    "Games": ("core:browse", ["games"]),
    "AI Tutor": ("portal:tutor", []),
}
KIND_LABELS = dict(Resource.KIND_CHOICES)
SUBJECT_OVERVIEW_KINDS = [Resource.NOTES, Resource.BOOKS, Resource.QUESTION_BANKS, Resource.WORKSHEETS]
MATERIAL_LIMIT = 300


def _kind_chips(base_qs, request):
    present = set(base_qs.values_list("kind", flat=True).distinct())
    active = request.GET.get("kind", "")
    if active not in present:
        active = ""
    chips = [{"key": "", "label": "All"}] + [
        {"key": k, "label": label} for k, label in Resource.KIND_CHOICES if k in present]
    return chips, active


def _materials_context(request, base_qs):
    """Resources of a class / program grouped Subject-wise (shown inside the class page)."""
    chips, active = _kind_chips(base_qs, request)
    qs = base_qs.filter(kind=active) if active else base_qs
    qs = qs.select_related("subject__level", "subject__program", "chapter").order_by(
        "subject__program__order", "subject__semester", "subject__name", "subject_id", "kind",
        "chapter__order", "-created_at")
    rows = list(qs[:MATERIAL_LIMIT + 1])
    truncated = len(rows) > MATERIAL_LIMIT
    groups = []
    for _, items in groupby(rows[:MATERIAL_LIMIT], key=lambda r: r.subject_id):
        items = list(items)
        groups.append({"subject": items[0].subject, "program": items[0].subject.program, "items": items})
    return {"material_groups": groups, "material_truncated": truncated, "kind_chips": chips, "active_kind": active}


def home(request):
    school_levels = Level.objects.filter(category=Level.SCHOOL)
    degree_levels = Level.objects.filter(category=Level.DEGREE)
    featured_programs = Program.objects.select_related("level").order_by("order")[:6]
    context = {
        "school_levels": school_levels,
        "degree_levels": degree_levels,
        "featured_programs": featured_programs,
        "categories": [dict(c, url=reverse(CATEGORY_LINKS[c["name"]][0], args=CATEGORY_LINKS[c["name"]][1]))
                       if c["name"] in CATEGORY_LINKS else c for c in POPULAR_CATEGORIES],
        "why_points": WHY_GYANSAGAR,
    }
    return render(request, "core/home.html", context)


def level_detail(request, slug):
    level = get_object_or_404(Level, slug=slug)
    programs = level.programs.all()
    subjects = level.subjects.filter(program__isnull=True)
    context = {
        "level": level,
        "programs": programs,
        "subjects": subjects,
        "school_levels": Level.objects.filter(category=Level.SCHOOL),
        "degree_levels": Level.objects.filter(category=Level.DEGREE),
        "hide_sidebar": True,
    }
    context.update(_materials_context(request, Resource.objects.filter(subject__level=level, is_published=True)))
    return render(request, "core/level_detail.html", context)


def program_detail(request, slug):
    program = get_object_or_404(Program.objects.select_related("level"), slug=slug)
    subjects = program.subjects.all()
    context = {
        "program": program,
        "level": program.level,
        "subjects": subjects,
        "school_levels": Level.objects.filter(category=Level.SCHOOL),
        "degree_levels": Level.objects.filter(category=Level.DEGREE),
        "hide_sidebar": True,
    }
    context.update(_materials_context(request, Resource.objects.filter(subject__program=program, is_published=True)))
    return render(request, "core/program_detail.html", context)


def subject_detail(request, slug):
    subject = get_object_or_404(Subject.objects.select_related("level", "program"), slug=slug)
    chapters = subject.chapters.all()
    active_tab = request.GET.get("tab", "overview")
    if active_tab not in {key for key, _, _ in SUBJECT_TABS}:
        active_tab = "overview"
    context = {
        "subject": subject,
        "chapters": chapters,
        "tabs": SUBJECT_TABS,
        "active_tab": active_tab,
        "school_levels": Level.objects.filter(category=Level.SCHOOL),
        "degree_levels": Level.objects.filter(category=Level.DEGREE),
        "hide_sidebar": True,
    }
    if active_tab in RESOURCE_TABS:
        resources = subject.resources.filter(kind=active_tab, is_published=True).select_related("chapter")
        chapter_id = request.GET.get("chapter", "")
        if chapter_id.isdigit():
            context["chapter_filter"] = chapters.filter(pk=int(chapter_id)).first()
            if context["chapter_filter"]:
                resources = resources.filter(chapter=context["chapter_filter"])
        if active_tab == Resource.LIVE_CLASSES:
            resources = resources.order_by("scheduled_at")
        context["resources"] = resources
        context["tab_label"] = RESOURCE_TABS[active_tab]
        return render(request, "core/subject_resources.html", context)
    published = list(subject.resources.filter(is_published=True, kind__in=SUBJECT_OVERVIEW_KINDS)
                     .select_related("chapter").order_by("chapter__order", "-created_at"))
    context["subject_sections"] = [
        {"kind": k, "label": KIND_LABELS[k], "icon": Resource.ICONS[k],
         "items": [r for r in published if r.kind == k][:50], "total": sum(1 for r in published if r.kind == k)}
        for k in SUBJECT_OVERVIEW_KINDS
    ]
    return render(request, "core/subject_detail.html", context)


def subject_syllabus(request, slug):
    """Plain-text syllabus download for a subject."""
    subject = get_object_or_404(Subject.objects.select_related("level", "program"), slug=slug)
    lines = [f"{subject.level.name} - {subject.name}"]
    if subject.program:
        lines.append(f"Program: {subject.program.name}" + (f" | Semester {subject.semester}" if subject.semester else ""))
    if subject.description:
        lines.append(subject.description)
    lines += ["", "SYLLABUS", "=" * 40]
    for ch in subject.chapters.all():
        lines.append(f"{ch.order}. {ch.title}  ({ch.topics_count} topics, {ch.activities_count} activities)")
        if ch.description:
            lines.append(f"   {ch.description}")
    if not subject.chapters.exists():
        lines.append("No chapters added yet.")
    response = HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{subject.slug}-syllabus.txt"'
    return response


@login_required
@xframe_options_sameorigin  # our own viewer page embeds this URL in an <iframe>
def resource_open(request, pk):
    """Serve an uploaded file (or redirect to its link). Only logged-in users; files are never public URLs."""
    qs = Resource.objects.all() if request.user.is_staff else Resource.objects.filter(is_published=True)
    resource = get_object_or_404(qs, pk=pk)
    if resource.file:
        inline = resource.extension in INLINE_EXTENSIONS and not request.GET.get("dl")
        method = settings.RESOURCE_SERVE_METHOD
        if method in ("nginx", "redirect"):
            if not resource.file.storage.exists(resource.file.name):
                raise Http404("This file is missing on the server.")
            Resource.objects.filter(pk=pk).update(download_count=F("download_count") + 1)
            if method == "redirect":  # S3 / R2 / MinIO: short-lived signed URL
                return redirect(resource.file.url)
            response = HttpResponse()  # nginx replaces this empty body with the real file (supports video seeking)
            response["X-Accel-Redirect"] = settings.RESOURCE_ACCEL_PREFIX + quote(resource.file.name)
            response["Content-Type"] = mimetypes.guess_type(resource.filename)[0] or "application/octet-stream"
            response["Content-Disposition"] = content_disposition_header(not inline, resource.filename)
            response["Cache-Control"] = "private, max-age=0"
            return response
        try:
            handle = resource.file.open("rb")
        except (FileNotFoundError, ValueError):
            raise Http404("This file is missing on the server.")
        Resource.objects.filter(pk=pk).update(download_count=F("download_count") + 1)
        return FileResponse(handle, as_attachment=not inline, filename=resource.filename)
    if not resource.external_url:  # text typed into the admin: show it on the viewer page
        return redirect(resource.get_view_url())
    Resource.objects.filter(pk=pk).update(download_count=F("download_count") + 1)
    return redirect(resource.external_url)


@login_required
def resource_view(request, pk):
    """Preview page: PDFs, images, video, audio and text are shown here; the Download button is separate."""
    qs = Resource.objects.all() if request.user.is_staff else Resource.objects.filter(is_published=True)
    resource = get_object_or_404(qs.select_related("subject__level", "subject__program", "chapter"), pk=pk)
    kind = resource.preview_kind
    if not kind:
        return redirect(resource.get_open_url())
    text = ""
    if kind == "text":
        if resource.file:
            try:
                with resource.file.open("rb") as handle:
                    raw = handle.read(TEXT_PREVIEW_LIMIT + 1)
            except (FileNotFoundError, ValueError):
                raise Http404("This file is missing on the server.")
            text = raw[:TEXT_PREVIEW_LIMIT].decode("utf-8", errors="replace")
            truncated = len(raw) > TEXT_PREVIEW_LIMIT
            Resource.objects.filter(pk=pk).update(download_count=F("download_count") + 1)
        else:
            text, truncated = resource.content, False
            Resource.objects.filter(pk=pk).update(download_count=F("download_count") + 1)
    else:
        truncated = False
    return render(request, "core/resource_view.html", {
        "resource": resource, "subject": resource.subject, "kind": kind, "text": text, "truncated": truncated,
        "hide_sidebar": True})


@login_required
def resource_report(request, pk):
    resource = get_object_or_404(Resource.objects.select_related("subject__level"), pk=pk, is_published=True)
    form = ReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not throttle.hit(request, "report", 20):
            form.add_error(None, "Too many reports. Please try again later.")
        else:
            report, created = ResourceReport.objects.get_or_create(
                resource=resource, user=request.user, defaults=form.cleaned_data)
            if created:
                open_reports = resource.reports.filter(resolved=False).count()
                if open_reports >= settings.REPORT_AUTOHIDE_THRESHOLD:
                    resource.is_published = False
                    resource.save(update_fields=["is_published", "updated_at"])
                    logger.warning("Resource %s hidden after %s reports", resource.pk, open_reports)
            messages.success(request, "Thank you! Our team will check this file.")
            return redirect(resource.subject)
    return render(request, "core/report_form.html", {"resource": resource, "form": form, "hide_sidebar": True})


def search(request):
    query = request.GET.get("q", "").strip()[:100]
    results = Subject.objects.none()
    resources = Resource.objects.none()
    if query:
        resources = (Resource.objects.filter(is_published=True)
                     .filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(content__icontains=query))
                     .select_related("subject__level", "subject__program", "chapter")[:30])
        results = Subject.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query) | Q(code__icontains=query)
            | Q(program__name__icontains=query) | Q(level__name__icontains=query)
            | Q(chapters__title__icontains=query)
        ).select_related("level", "program").distinct()
    context = {
        "query": query,
        "results": results,
        "resources": resources,
        "school_levels": Level.objects.filter(category=Level.SCHOOL),
        "degree_levels": Level.objects.filter(category=Level.DEGREE),
    }
    return render(request, "core/search_results.html", context)


def _query_without_page(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


def browse(request, section):
    """Sidebar pages (Notes, Old Questions, Books, ...): everything of one kind, filter Class -> Faculty -> Subject."""
    if section not in SECTIONS:
        raise Http404
    kind, title, icon, blurb = SECTIONS[section]
    get = request.GET
    subject = Subject.objects.select_related("level", "program").filter(slug=get.get("subject", "")).first()
    program = subject.program if subject else Program.objects.select_related("level").filter(
        slug=get.get("program", "")).first()
    level = (subject.level if subject else program.level if program else
             Level.objects.filter(slug=get.get("level", "")).first())
    q = get.get("q", "").strip()[:100]

    qs = Resource.objects.filter(kind=kind, is_published=True).select_related(
        "subject__level", "subject__program", "chapter")
    if subject:
        qs = qs.filter(subject=subject)
    elif program:
        qs = qs.filter(subject__program=program)
    elif level:
        qs = qs.filter(subject__level=level)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(subject__name__icontains=q)
                       | Q(chapter__title__icontains=q))
    qs = qs.order_by("scheduled_at") if kind == Resource.LIVE_CLASSES else qs.order_by("-created_at")

    programs = level.programs.all() if level else Program.objects.none()
    if program:
        subject_options = program.subjects.all()
    elif level and not programs:
        subject_options = level.subjects.filter(program__isnull=True)
    else:
        subject_options = Subject.objects.none()

    page_obj = Paginator(qs, 20).get_page(get.get("page"))
    return render(request, "core/browse.html", {
        "section": section, "title": title, "icon": icon, "blurb": blurb,
        "levels": Level.objects.all(), "programs": programs, "subject_options": subject_options,
        "sel_level": level, "sel_program": program, "sel_subject": subject, "q": q,
        "page_obj": page_obj, "qs": _query_without_page(request),
        "query": q,
    })


def courses(request):
    """All classes and programs in one catalogue."""
    programs = Program.objects.annotate(n_subjects=Count("subjects"))
    return render(request, "core/courses.html", {
        "school": Level.objects.filter(category=Level.SCHOOL).annotate(n_subjects=Count("subjects")),
        "degree": Level.objects.filter(category=Level.DEGREE).prefetch_related(Prefetch("programs", programs)),
    })


def syllabus(request):
    """Pick class -> program -> see every subject with its chapter-wise syllabus."""
    program = Program.objects.select_related("level").filter(slug=request.GET.get("program", "")).first()
    level = program.level if program else Level.objects.filter(slug=request.GET.get("level", "")).first()
    subjects, programs = None, None
    if program:
        subjects = program.subjects.prefetch_related("chapters")
    elif level:
        programs = level.programs.all()
        if not programs:
            subjects = level.subjects.filter(program__isnull=True).prefetch_related("chapters")
    return render(request, "core/syllabus.html", {
        "levels": Level.objects.all(), "sel_level": level, "sel_program": program,
        "programs": programs, "subjects": subjects,
    })


@require_safe
@never_cache
def healthz(request):
    """Liveness probe: the process is up. (No database access.)"""
    return JsonResponse({"status": "ok", "version": settings.APP_VERSION})


@require_safe
@never_cache
def readyz(request):
    """Readiness probe: can we reach the database and the cache?"""
    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        logger.exception("readyz: database check failed")
        checks["database"] = "error"
    try:
        cache.set("readyz", "1", 10)
        checks["cache"] = "ok" if cache.get("readyz") == "1" else "error"
    except Exception:
        logger.exception("readyz: cache check failed")
        checks["cache"] = "error"
    ok = all(v == "ok" for v in checks.values())
    return JsonResponse({"status": "ok" if ok else "unavailable", "checks": checks}, status=200 if ok else 503)
