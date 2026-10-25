import re
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.verification import verified_required
from core.models import Chapter, Level, Resource, Subject

from . import ai
from .forms import CommentForm, ContactForm, PostForm, TutorForm
from .models import BlogPost, Comment, ContactMessage, Opportunity, Post, School, TutorMessage

PAGE_SIZE = 15
POSTS_PER_HOUR = 10
COMMENTS_PER_HOUR = 30


def _qs_without_page(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


def _paginate(request, qs, size=PAGE_SIZE):
    return Paginator(qs, size).get_page(request.GET.get("page"))


# ---------------------------------------------------------------- schools
def schools(request):
    q = request.GET.get("q", "").strip()[:100]
    kind = request.GET.get("type", "")
    qs = School.objects.filter(is_published=True)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(city__icontains=q) | Q(address__icontains=q))
    if kind in dict(School.KIND_CHOICES):
        qs = qs.filter(kind=kind)
    return render(request, "portal/schools.html", {
        "page_obj": _paginate(request, qs), "q": q, "kind": kind, "kinds": School.KIND_CHOICES,
        "qs": _qs_without_page(request),
    })


# ---------------------------------------------------------------- tools
def tools(request):
    return render(request, "portal/tools.html")


# ---------------------------------------------------------------- blogs
def blog_list(request):
    qs = BlogPost.objects.filter(is_published=True, published_at__lte=timezone.now())
    return render(request, "portal/blog_list.html", {"page_obj": _paginate(request, qs, 9),
                                                      "qs": _qs_without_page(request)})


def blog_detail(request, slug):
    post = get_object_or_404(BlogPost, slug=slug, is_published=True, published_at__lte=timezone.now())
    return render(request, "portal/blog_detail.html", {"post": post})


# ---------------------------------------------------------------- scholarships / careers
def _opportunities(request, kind, title, icon, blurb):
    q = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "open")
    level = Level.objects.filter(slug=request.GET.get("level", "")).first()
    qs = Opportunity.objects.filter(kind=kind, is_published=True).select_related("level")
    today = timezone.localdate()
    if status == "open":
        qs = qs.filter(Q(deadline__isnull=True) | Q(deadline__gte=today))
    elif status == "closed":
        qs = qs.filter(deadline__lt=today)
    if level:
        qs = qs.filter(Q(level=level) | Q(level__isnull=True))
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(organization__icontains=q) | Q(description__icontains=q)
                       | Q(location__icontains=q))
    return render(request, "portal/opportunities.html", {
        "page_obj": _paginate(request, qs), "q": q, "status": status, "sel_level": level,
        "levels": Level.objects.all(), "title": title, "icon": icon, "blurb": blurb, "kind": kind,
        "qs": _qs_without_page(request),
    })


def scholarships(request):
    return _opportunities(request, Opportunity.SCHOLARSHIP, "Scholarships", "🎁",
                          "Scholarships and financial aid for Nepali students.")


def careers(request):
    return _opportunities(request, Opportunity.CAREER, "Careers", "💼",
                          "Jobs, internships and career opportunities.")


# ---------------------------------------------------------------- community
def community(request):
    q = request.GET.get("q", "").strip()[:100]
    level = Level.objects.filter(slug=request.GET.get("level", "")).first()
    qs = Post.objects.filter(is_hidden=False).select_related("author", "level", "subject").annotate(
        n_comments=Count("comments", filter=Q(comments__is_hidden=False)))
    qs = qs.order_by("-created_at")
    if level:
        qs = qs.filter(level=level)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(body__icontains=q))
    return render(request, "portal/community_list.html", {
        "page_obj": _paginate(request, qs), "q": q, "sel_level": level, "levels": Level.objects.all(),
        "qs": _qs_without_page(request),
    })


def _recent(model, user, hours=1):
    return model.objects.filter(author=user, created_at__gte=timezone.now() - timedelta(hours=hours)).count()


@login_required
@verified_required
def post_new(request):
    form = PostForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _recent(Post, request.user) >= POSTS_PER_HOUR:
            form.add_error(None, "You are posting too fast. Please wait a little and try again.")
        else:
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            return redirect(post)
    return render(request, "portal/post_form.html", {"form": form})


def post_detail(request, pk):
    post = get_object_or_404(Post.objects.select_related("author", "level", "subject"), pk=pk)
    if post.is_hidden and not request.user.is_staff:
        raise Http404
    form = CommentForm()
    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        form = CommentForm(request.POST)
        if form.is_valid():
            if _recent(Comment, request.user) >= COMMENTS_PER_HOUR:
                form.add_error(None, "You are replying too fast. Please wait a little and try again.")
            else:
                comment = form.save(commit=False)
                comment.post, comment.author = post, request.user
                comment.save()
                return redirect(f"{post.get_absolute_url()}#c{comment.pk}")
    comments = post.comments.select_related("author")
    if not request.user.is_staff:
        comments = comments.filter(is_hidden=False)
    return render(request, "portal/post_detail.html", {"post": post, "comments": comments, "form": form})


@login_required
@require_POST
def post_delete(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if post.author_id != request.user.id and not request.user.is_staff:
        raise Http404
    post.delete()
    messages.success(request, "Post deleted.")
    return redirect("portal:community")


@login_required
@require_POST
def comment_delete(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    if comment.author_id != request.user.id and not request.user.is_staff:
        raise Http404
    post = comment.post
    comment.delete()
    return redirect(post)


# ---------------------------------------------------------------- AI tutor
def _related_material(question):
    """Fallback when no AI key is configured: point the student to matching subjects / chapters / uploads."""
    words = [w for w in re.findall(r"\w{3,}", question.lower())][:6]
    if not words:
        return {}
    def any_of(field):
        q = Q()
        for w in words:
            q |= Q(**{f"{field}__icontains": w})
        return q
    return {
        "subjects": Subject.objects.filter(any_of("name")).select_related("level", "program")[:5],
        "chapters": Chapter.objects.filter(any_of("title")).select_related("subject__level")[:6],
        "resources": Resource.objects.filter(any_of("title"), is_published=True).select_related("subject")[:6],
    }


@login_required
@verified_required
def tutor(request):
    form = TutorForm(request.POST or None)
    today = timezone.localdate()
    used_today = TutorMessage.objects.filter(user=request.user, created_at__date=today).count()
    limit = settings.AI_TUTOR_DAILY_LIMIT
    related = None
    if request.method == "POST" and form.is_valid():
        question, subject = form.cleaned_data["question"], form.cleaned_data["subject"]
        if not ai.ai_enabled():
            related = _related_material(question)
        elif used_today >= limit:
            form.add_error(None, f"Daily limit reached ({limit} questions). Come back tomorrow!")
        else:
            history = [(m.question, m.answer) for m in TutorMessage.objects.filter(user=request.user).order_by("-created_at")[:4]][::-1]
            context = f"{subject.name} ({subject.level.name})" if subject else ""
            try:
                answer = ai.ask_tutor(question, history, context)
            except ai.AIError as exc:
                form.add_error(None, str(exc))
            else:
                TutorMessage.objects.create(user=request.user, subject=subject, question=question, answer=answer)
                return redirect("portal:tutor")
    history = list(TutorMessage.objects.filter(user=request.user).order_by("-created_at")[:10])[::-1]
    return render(request, "portal/tutor.html", {
        "form": form, "history": history, "ai_enabled": ai.ai_enabled(), "related": related,
        "remaining": max(limit - used_today, 0), "limit": limit,
    })


@login_required
@require_POST
def tutor_clear(request):
    TutorMessage.objects.filter(user=request.user).delete()
    return redirect("portal:tutor")


# ---------------------------------------------------------------- more + contact
def more(request):
    initial = {}
    if request.user.is_authenticated:
        initial = {"name": request.user.get_full_name() or request.user.username, "email": request.user.email}
    form = ContactForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        since = timezone.now() - timedelta(hours=1)
        sent = ContactMessage.objects.filter(created_at__gte=since, email__iexact=form.cleaned_data["email"]).count()
        if request.user.is_authenticated:
            sent = max(sent, ContactMessage.objects.filter(created_at__gte=since, user=request.user).count())
        if sent >= 5:
            form.add_error(None, "Too many messages sent recently. Please try again later.")
        else:
            msg = form.save(commit=False)
            if request.user.is_authenticated:
                msg.user = request.user
            msg.save()
            messages.success(request, "Thanks! Your message has been sent to the Gyansagar team.")
            return redirect("portal:more")
    return render(request, "portal/more.html", {"form": form})
