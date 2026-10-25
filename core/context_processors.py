from django.urls import reverse

from accounts import google, verification

from .models import Level

# (icon, label, url name, url args, pill)
SIDEBAR = [
    ("🏠", "Home", "core:home", [], ""),
    ("🎯", "Courses", "core:courses", [], ""),
    ("📝", "Notes", "core:browse", ["notes"], ""),
    ("📄", "Old Questions", "core:browse", ["old-questions"], ""),
    ("📚", "Books", "core:browse", ["books"], ""),
    ("▶️", "Videos", "core:browse", ["videos"], ""),
    ("🎥", "Live Classes", "core:browse", ["live-classes"], ""),
    ("❓", "Quizzes", "core:browse", ["quizzes"], ""),
    ("🧠", "Practice Tests", "learning:quizzes", [], "New"),
    ("📤", "Assignments", "learning:assignments", [], ""),
    ("🎮", "Games", "core:browse", ["games"], ""),
    ("🤖", "AI Tutor", "portal:tutor", [], "New"),
    ("📑", "Syllabus", "core:syllabus", [], ""),
    ("🏫", "Schools", "portal:schools", [], ""),
    ("🛠️", "Study Tools", "portal:tools", [], ""),
    ("👥", "Community", "portal:community", [], ""),
    ("📰", "Blogs", "portal:blog_list", [], ""),
    ("🎁", "Scholarships", "portal:scholarships", [], ""),
    ("💼", "Careers", "portal:careers", [], ""),
    ("➕", "More", "portal:more", [], ""),
]


def navigation(request):
    """Level chips for the top bar + left sidebar links, available on every page."""
    path = request.path
    links = []
    for icon, label, name, args, pill in SIDEBAR:
        url = reverse(name, args=args)
        active = path == url if url == "/" else path.startswith(url)
        links.append({"icon": icon, "label": label, "url": url, "pill": pill, "active": active})
    user = request.user
    unverified = user.is_authenticated and not verification.is_verified(user) and bool(user.email)
    return {
        "email_unverified": unverified,
        "google_enabled": google.enabled(),
        "school_levels": Level.objects.filter(category=Level.SCHOOL),
        "degree_levels": Level.objects.filter(category=Level.DEGREE),
        "sidebar_links": links,
    }
