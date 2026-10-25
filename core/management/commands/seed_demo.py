from django.core.management.base import BaseCommand

from core.models import Level, Program, Subject, Chapter

SCHOOL_LEVELS = [
    ("Nursery", "3+ Years", "🧸"),
    ("LKG", "4+ Years", "🍎"),
    ("UKG", "5+ Years", "🔤"),
    ("Class One", "Grade 1", "1️⃣"),
    ("Class Two", "Grade 2", "2️⃣"),
    ("Class Three", "Grade 3", "3️⃣"),
    ("Class 11", "Grade 11", "🅰️"),
    ("Class 12", "Grade 12", "🅱️"),
    ("Diploma", "After SEE", "📘"),
]

DEGREE_LEVELS = [
    ("Bachelor", "Undergraduate", "🎓"),
    ("Master", "Postgraduate", "🎖️"),
    ("PhD", "Doctorate", "🏆"),
]

PROGRAMS = [
    ("BSc CSIT", "Bachelor", "4 Years", "💻"),
    ("B.E. Civil", "Bachelor", "4 Years", "🏛️"),
    ("B.E. Computer", "Bachelor", "4 Years", "🖥️"),
    ("BBA", "Bachelor", "4 Years", "💼"),
    ("B.Ed", "Bachelor", "4 Years", "📗"),
    ("BCA", "Bachelor", "4 Years", "🎓"),
]

NURSERY_CHAPTERS = [
    ("Alphabet (A to Z)", "Learn all letters from A to Z with pictures.", 26, 10),
    ("Vowels and Consonants", "Learn vowels and consonants with examples.", 12, 8),
    ("Words and Pictures", "Learn simple words with pictures.", 18, 12),
    ("Rhyming Words", "Fun with rhyming words and sounds.", 10, 6),
    ("Sentences", "Learn simple sentences.", 14, 8),
]

CSIT_CHAPTERS = [
    ("Introduction to C", "Basics of C, compilers and your first program.", 6, 4),
    ("Variables and Data Types", "Declaring variables, constants and data types.", 8, 6),
    ("Operators and Expressions", "Arithmetic, relational and logical operators.", 7, 5),
    ("Control Structures", "if-else, switch and loops.", 9, 7),
    ("Functions", "Defining and calling functions, recursion.", 8, 6),
    ("Arrays and Strings", "Working with arrays, strings and pointers.", 10, 8),
]


class Command(BaseCommand):
    help = "Seeds demo Levels, Programs, Subjects and Chapters for Gyansagar."

    def handle(self, *args, **options):
        for i, (name, subtitle, icon) in enumerate(SCHOOL_LEVELS):
            Level.objects.update_or_create(
                slug=self._slug(name),
                defaults=dict(name=name, subtitle=subtitle, icon=icon, category=Level.SCHOOL, order=i),
            )
        for i, (name, subtitle, icon) in enumerate(DEGREE_LEVELS):
            Level.objects.update_or_create(
                slug=self._slug(name),
                defaults=dict(name=name, subtitle=subtitle, icon=icon, category=Level.DEGREE, order=100 + i),
            )

        bachelor = Level.objects.get(slug="bachelor")
        for i, (name, level_name, duration, icon) in enumerate(PROGRAMS):
            Program.objects.update_or_create(
                slug=self._slug(name),
                defaults=dict(name=name, level=bachelor, duration=duration, icon=icon, order=i),
            )

        nursery = Level.objects.get(slug="nursery")
        english, _ = Subject.objects.update_or_create(
            slug="nursery-english",
            defaults=dict(
                level=nursery, name="English", description="Start your learning journey with fun and interactive English lessons.",
                books_count=50, videos_count=35,
            ),
        )
        Chapter.objects.filter(subject=english).delete()
        for i, (title, desc, topics, activities) in enumerate(NURSERY_CHAPTERS, start=1):
            Chapter.objects.create(subject=english, order=i, title=title, description=desc,
                                    topics_count=topics, activities_count=activities)

        csit = Program.objects.get(slug="bsc-csit")
        c_prog, _ = Subject.objects.update_or_create(
            slug="bsc-csit-c-programming",
            defaults=dict(
                level=bachelor, program=csit, name="C Programming",
                description="Learn programming fundamentals with C — from syntax to pointers.",
                books_count=12, videos_count=40,
            ),
        )
        Chapter.objects.filter(subject=c_prog).delete()
        for i, (title, desc, topics, activities) in enumerate(CSIT_CHAPTERS, start=1):
            Chapter.objects.create(subject=c_prog, order=i, title=title, description=desc,
                                    topics_count=topics, activities_count=activities)

        self.stdout.write(self.style.SUCCESS("Demo data seeded."))

    @staticmethod
    def _slug(name):
        return name.lower().replace(" ", "-").replace(".", "")
