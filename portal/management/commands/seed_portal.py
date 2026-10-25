"""Starter blog posts so the Blogs page is not empty. Safe to re-run. Schools / scholarships / careers are
real-world facts, so they are NOT invented here - add them from the admin panel."""
from django.core.management.base import BaseCommand

from portal.models import BlogPost

POSTS = [
    ("Welcome to Gyansagar",
     "Gyansagar is your ocean of knowledge - from Nursery to PhD.\n\n"
     "Pick your class or program, open a subject, and you will find notes, books, videos and old questions "
     "uploaded by teachers. Create a free account to download material, join the community and ask the AI Tutor.\n\n"
     "Found something missing? Tell us from the More page."),
    ("5 simple habits for exam preparation",
     "1. Start early and study a little every day instead of cramming.\n\n"
     "2. Use old questions: solve at least the last few years of papers under a timer.\n\n"
     "3. Study in short focused blocks (try the Pomodoro timer in Study Tools) and take real breaks.\n\n"
     "4. Teach a topic to a friend - if you can explain it, you understand it.\n\n"
     "5. Sleep well before the exam. A rested brain remembers more than a tired one."),
    ("How to make good notes",
     "Good notes are short, structured and yours.\n\n"
     "Write headings for each chapter, list key definitions and formulas, and add one worked example per idea. "
     "After class, rewrite messy notes within 24 hours - this alone doubles how much you remember.\n\n"
     "Upload-worthy notes are clear, correct and organised chapter-wise. Teachers can share them on Gyansagar."),
]


class Command(BaseCommand):
    help = "Create a few starter blog posts (idempotent)."

    def handle(self, *args, **options):
        made = 0
        for title, body in POSTS:
            _, created = BlogPost.objects.get_or_create(
                title=title, defaults={"body": body, "excerpt": body.split("\n\n")[0][:300]})
            made += created
        self.stdout.write(self.style.SUCCESS(f"Blog posts ready ({made} new)."))
