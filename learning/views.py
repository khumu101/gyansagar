import logging
import mimetypes
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg as models_avg, Count, Q, Sum as models_sum
from django.http import FileResponse, Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_POST

from datetime import timedelta

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.db.models.functions import TruncDate

from core.models import Level, Resource, ResourceReport, Subject

from .forms import GradeForm, SubmissionForm
from .models import Assignment, Attempt, AttemptAnswer, Choice, Quiz, Submission

logger = logging.getLogger(__name__)


def is_teacher(user):
    if not user.is_authenticated:
        return False
    profile = getattr(user, "profile", None)
    return user.is_superuser or bool(profile and profile.role == "teacher")


def teacher_required(view):
    from functools import wraps

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not is_teacher(request.user):
            return HttpResponseForbidden("Only teachers can open this page.")
        return view(request, *args, **kwargs)
    return wrapper


def _my_level(request):
    profile = getattr(request.user, "profile", None)
    return profile.level if profile and profile.level_id else None


def _filter_by_level(request, qs, prefix):
    """Students see their own class by default; ?all=1 shows everything."""
    level = _my_level(request)
    if level and not request.GET.get("all"):
        return qs.filter(**{f"{prefix}level": level}), level
    return qs, None


# --------------------------------------------------------------------------- student home
@login_required
def home(request):
    attempts = Attempt.objects.filter(user=request.user).select_related("quiz__subject")[:5]
    mine, _ = _filter_by_level(request, Assignment.objects.filter(is_published=True), "subject__")
    submitted = set(Submission.objects.filter(student=request.user).values_list("assignment_id", flat=True))
    todo = [a for a in mine.select_related("subject")[:30] if a.pk not in submitted and not a.is_past_due][:5]
    stats = Attempt.objects.filter(user=request.user)
    return render(request, "learning/home.html", {
        "attempts": attempts, "todo": todo, "attempt_count": stats.count(),
        "passed_count": stats.filter(passed=True).count(),
        "graded": Submission.objects.filter(student=request.user, marks__isnull=False).select_related("assignment")[:5],
    })


# --------------------------------------------------------------------------- quizzes
def quiz_list(request):
    qs = (Quiz.objects.filter(is_published=True).annotate(n=Count("questions"))
          .filter(n__gt=0).select_related("subject__level", "subject__program").order_by("-created_at"))
    level = None
    if request.user.is_authenticated:
        qs, level = _filter_by_level(request, qs, "subject__")
    q = request.GET.get("q", "").strip()[:80]
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(subject__name__icontains=q))
    page = Paginator(qs, 15).get_page(request.GET.get("page"))
    keep = request.GET.copy()
    keep.pop("page", None)
    return render(request, "learning/quiz_list.html", {"page": page, "q": q, "my_level": level, "qs": keep.urlencode()})


@login_required
def quiz_take(request, pk):
    quiz = get_object_or_404(Quiz.objects.select_related("subject__level"), pk=pk, is_published=True)
    questions = list(quiz.questions.prefetch_related("choices"))
    if not questions:
        raise Http404("This quiz has no questions yet.")
    error = ""
    if request.method == "POST":
        picked = {}
        for question in questions:
            raw = request.POST.get(f"q{question.pk}", "")
            choice = next((c for c in question.choices.all() if str(c.pk) == raw), None)
            picked[question.pk] = choice
        if all(c is None for c in picked.values()):
            error = "Please answer at least one question."
        else:
            with transaction.atomic():
                score = sum(1 for c in picked.values() if c and c.is_correct)
                percent = round(score * 100 / len(questions))
                attempt = Attempt.objects.create(
                    user=request.user, quiz=quiz, score=score, total=len(questions), percent=percent,
                    passed=percent >= quiz.pass_percent)
                AttemptAnswer.objects.bulk_create([
                    AttemptAnswer(attempt=attempt, question=q, choice=picked[q.pk],
                                  is_correct=bool(picked[q.pk] and picked[q.pk].is_correct))
                    for q in questions])
            return redirect(attempt)
    best = Attempt.objects.filter(user=request.user, quiz=quiz).order_by("-percent").first()
    return render(request, "learning/quiz_take.html", {"quiz": quiz, "questions": questions, "error": error, "best": best,
                                                       "hide_sidebar": True})


@login_required
def attempt_detail(request, pk):
    attempt = get_object_or_404(Attempt.objects.select_related("quiz__subject", "user"), pk=pk)
    if attempt.user_id != request.user.pk and not is_teacher(request.user):
        raise Http404
    answers = list(attempt.answers.select_related("question", "choice"))
    correct = {c.question_id: c for c in Choice.objects.filter(question__quiz=attempt.quiz, is_correct=True)}
    for a in answers:
        a.right_choice = correct.get(a.question_id)
    return render(request, "learning/attempt_detail.html", {"attempt": attempt, "answers": answers, "hide_sidebar": True})


# --------------------------------------------------------------------------- assignments (student side)
def assignment_list(request):
    qs = Assignment.objects.filter(is_published=True).select_related("subject__level")
    level = None
    if request.user.is_authenticated:
        qs, level = _filter_by_level(request, qs, "subject__")
    page = Paginator(qs, 15).get_page(request.GET.get("page"))
    mine = {}
    if request.user.is_authenticated:
        mine = {s.assignment_id: s for s in Submission.objects.filter(student=request.user, assignment__in=list(page))}
    for a in page:
        a.my_submission = mine.get(a.pk)
    return render(request, "learning/assignment_list.html", {"page": page, "my_level": level})


@login_required
def assignment_detail(request, pk):
    assignment = get_object_or_404(Assignment.objects.select_related("subject__level"), pk=pk, is_published=True)
    submission = Submission.objects.filter(assignment=assignment, student=request.user).first()
    locked = bool(submission and submission.is_graded)
    form = SubmissionForm(request.POST or None, request.FILES or None, instance=submission)
    if request.method == "POST" and not locked and form.is_valid():
        sub = form.save(commit=False)
        sub.assignment, sub.student, sub.submitted_at = assignment, request.user, timezone.now()
        sub.save()
        messages.success(request, "Submitted! Your teacher will grade it soon.")
        return redirect(assignment)
    return render(request, "learning/assignment_detail.html", {
        "assignment": assignment, "submission": submission, "form": form, "locked": locked, "hide_sidebar": True})


def _send_submission_file(submission):
    f = submission.file
    if not f or not f.storage.exists(f.name):
        raise Http404("File missing.")
    method = settings.RESOURCE_SERVE_METHOD
    if method == "redirect":
        return redirect(f.url)
    if method == "nginx":
        response = HttpResponse()
        response["X-Accel-Redirect"] = settings.RESOURCE_ACCEL_PREFIX + quote(f.name)
        response["Content-Type"] = mimetypes.guess_type(submission.filename)[0] or "application/octet-stream"
        response["Content-Disposition"] = content_disposition_header(True, submission.filename)
        response["Cache-Control"] = "private, max-age=0"
        return response
    return FileResponse(f.open("rb"), as_attachment=True, filename=submission.filename)


@login_required
def submission_file(request, pk):
    """Only the student who handed it in, and teachers, may download a submission."""
    submission = get_object_or_404(Submission.objects.select_related("assignment"), pk=pk)
    if submission.student_id != request.user.pk and not (is_teacher(request.user) and _may_grade(request.user, submission.assignment)):
        raise Http404
    return _send_submission_file(submission)


# --------------------------------------------------------------------------- teacher side
def _may_grade(user, assignment):
    return user.is_superuser or assignment.created_by_id == user.pk


@login_required
@teacher_required
def grading_list(request):
    qs = Assignment.objects.select_related("subject__level").annotate(
        total=Count("submissions"), pending=Count("submissions", filter=Q(submissions__marks__isnull=True)))
    if not request.user.is_superuser:
        qs = qs.filter(created_by=request.user)
    return render(request, "learning/grading_list.html", {"assignments": qs.order_by("-created_at")})


@login_required
@teacher_required
def grade_assignment(request, pk):
    assignment = get_object_or_404(Assignment.objects.select_related("subject"), pk=pk)
    if not _may_grade(request.user, assignment):
        raise Http404
    submissions = assignment.submissions.select_related("student").order_by("marks", "submitted_at")
    return render(request, "learning/grade_assignment.html", {"assignment": assignment, "submissions": submissions})


@login_required
@teacher_required
def grade_submission(request, pk):
    submission = get_object_or_404(Submission.objects.select_related("assignment", "student"), pk=pk)
    if not _may_grade(request.user, submission.assignment):
        raise Http404
    form = GradeForm(request.POST or None, instance=submission)
    if request.method == "POST" and form.is_valid():
        graded = form.save(commit=False)
        graded.graded_by, graded.graded_at = request.user, timezone.now()
        graded.save()
        messages.success(request, f"Saved marks for {submission.student.get_username()}.")
        return redirect("learning:grade_assignment", pk=submission.assignment_id)
    return render(request, "learning/grade_submission.html", {"submission": submission, "form": form, "hide_sidebar": True})


# --------------------------------------------------------------------------- staff analytics
@staff_member_required
def dashboard(request):
    """Numbers for the people running the site (staff only)."""
    User = get_user_model()
    now = timezone.now()
    since = now - timedelta(days=14)
    per_day = dict(User.objects.filter(date_joined__gte=since).annotate(d=TruncDate("date_joined"))
                   .values_list("d").annotate(n=Count("id")).order_by("d"))
    days = [(since + timedelta(days=i + 1)).date() for i in range(14)]
    series = [(d, per_day.get(d, 0)) for d in days]
    top = max([n for _, n in series] + [1])
    attempts = Attempt.objects.all()
    avg = attempts.aggregate(a=models_avg("percent"))["a"]
    context = {
        "users_total": User.objects.count(),
        "users_7d": User.objects.filter(date_joined__gte=now - timedelta(days=7)).count(),
        "users_unverified": User.objects.filter(profile__email_verified=False).count(),
        "resources_total": Resource.objects.filter(is_published=True).count(),
        "resources_hidden": Resource.objects.filter(is_published=False).count(),
        "downloads_total": sum(Resource.objects.values_list("download_count", flat=True)),
        "subjects_total": Subject.objects.count(),
        "attempts_total": attempts.count(),
        "attempts_avg": round(avg) if avg is not None else None,
        "pass_rate": round(attempts.filter(passed=True).count() * 100 / attempts.count()) if attempts.exists() else None,
        "pending_grading": Submission.objects.filter(marks__isnull=True).count(),
        "open_reports": ResourceReport.objects.filter(resolved=False).count(),
        "top_resources": Resource.objects.select_related("subject").order_by("-download_count")[:10],
        "top_subjects": Subject.objects.select_related("level").annotate(
            dl=models_sum("resources__download_count")).order_by("-dl")[:8],
        "series": [(d, n, round(n * 100 / top)) for d, n in series],
        "hide_sidebar": True,
    }
    return render(request, "learning/dashboard.html", context)
