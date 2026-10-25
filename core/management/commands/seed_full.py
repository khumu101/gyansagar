"""Fuller demo data: every class (Nursery to Class 12), more programs, and BSc CSIT semester-wise subjects.

Safe to run many times; never deletes anything. Run AFTER (or instead of) seed_demo:
    python manage.py seed_full
Names/chapters are demo content - edit or replace them from the admin panel.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from core.models import Chapter, Level, Program, Subject

CLASSES = [  # (name, subtitle, icon)
    ("Nursery", "3+ Years", "🧸"), ("LKG", "4+ Years", "🍎"), ("UKG", "5+ Years", "🔤"),
    ("Class One", "Grade 1", "1️⃣"), ("Class Two", "Grade 2", "2️⃣"), ("Class Three", "Grade 3", "3️⃣"),
    ("Class Four", "Grade 4", "4️⃣"), ("Class Five", "Grade 5", "5️⃣"), ("Class Six", "Grade 6", "6️⃣"),
    ("Class Seven", "Grade 7", "7️⃣"), ("Class Eight", "Grade 8", "8️⃣"), ("Class Nine", "Grade 9", "9️⃣"),
    ("Class Ten", "Grade 10 (SEE)", "🔟"), ("Class 11", "Grade 11", "🅰️"), ("Class 12", "Grade 12", "🅱️"),
    ("Diploma", "After SEE", "📘"),
]

EARLY = ["English", "Nepali", "Mathematics", "General Knowledge", "Drawing and Art"]
PRIMARY = ["English", "Nepali", "Mathematics", "Science", "Social Studies", "Computer Science"]
BASIC = ["English", "Nepali", "Mathematics", "Science and Technology", "Social Studies", "Computer Science"]
SECONDARY = BASIC + ["Optional Mathematics"]
PLUS_TWO = ["English", "Nepali", "Physics", "Chemistry", "Biology", "Mathematics", "Computer Science", "Accountancy"]


def subjects_for(name):
    if name in ("Nursery", "LKG", "UKG"):
        return EARLY
    if name in ("Class One", "Class Two", "Class Three"):
        return PRIMARY
    if name in ("Class Four", "Class Five", "Class Six", "Class Seven", "Class Eight"):
        return BASIC
    if name in ("Class Nine", "Class Ten"):
        return SECONDARY
    if name in ("Class 11", "Class 12"):
        return PLUS_TWO
    return []


EXTRA_PROGRAMS = [  # (level slug, name, duration, icon)
    ("bachelor", "BBS", "4 Years", "📊"),
    ("bachelor", "BIT", "4 Years", "🌐"),
    ("master", "MSc CSIT", "2 Years", "💻"),
    ("master", "MBA", "2 Years", "💼"),
    ("master", "M.Ed", "2 Years", "📗"),
]

CSIT = {
    1: ["Introduction to Information Technology", "C Programming", "Digital Logic", "Mathematics I", "Physics"],
    2: ["Discrete Structure", "Object Oriented Programming", "Microprocessor", "Mathematics II", "Statistics I"],
    3: ["Data Structure and Algorithms", "Numerical Method", "Computer Architecture", "Computer Graphics", "Statistics II"],
    4: ["Theory of Computation", "Computer Networks", "Operating Systems", "Database Management System",
        "Artificial Intelligence"],
    5: ["Design and Analysis of Algorithms", "System Analysis and Design", "Cryptography", "Simulation and Modeling",
        "Web Technology"],
    6: ["Software Engineering", "Compiler Design and Construction", "E-Governance", "NET Centric Computing",
        "Technical Writing"],
    7: ["Advanced Java Programming", "Data Warehousing and Data Mining", "Principles of Management", "Project Work"],
    8: ["Advanced Database", "Internship"],
}

CSIT_CHAPTERS = {
    "Data Structure and Algorithms": [
        ("Introduction to Data Structures", "ADTs, algorithm analysis and Big-O notation."),
        ("The Stack", "Stack operations, expression evaluation and conversion."),
        ("Queues", "Linear, circular and priority queues."),
        ("Lists", "Linked lists: singly, doubly and circular."),
        ("Recursion", "Recursive thinking, Tower of Hanoi, backtracking."),
        ("Trees", "Binary trees, BST, AVL, heaps and traversals."),
        ("Sorting", "Bubble, selection, insertion, merge, quick and heap sort."),
        ("Searching", "Linear/binary search and hashing."),
        ("Graphs", "Representation, BFS, DFS, shortest paths and spanning trees."),
    ],
    "Database Management System": [
        ("Introduction", "Database approach, architecture and data independence."),
        ("Data Models and ER Modeling", "Entities, relationships and ER diagrams."),
        ("Relational Data Model", "Keys, integrity constraints and relational algebra."),
        ("SQL", "DDL, DML, joins, views and subqueries."),
        ("Normalization", "Functional dependencies and normal forms."),
        ("Transaction and Concurrency", "ACID, schedules, locking and recovery."),
    ],
    "Object Oriented Programming": [
        ("Introduction to OOP", "Concepts of objects, classes and C++ basics."),
        ("Classes and Objects", "Members, access specifiers, static members."),
        ("Constructors and Destructors", "Types of constructors and object lifetime."),
        ("Operator Overloading", "Overloading unary and binary operators."),
        ("Inheritance", "Single, multiple and multilevel inheritance."),
        ("Polymorphism", "Virtual functions and abstract classes."),
        ("Templates and Exception Handling", "Generic programming and try/catch."),
        ("Streams and File Handling", "Console and file I/O."),
    ],
    "Operating Systems": [
        ("Introduction", "OS roles, types and system calls."),
        ("Process Management", "Processes, threads and CPU scheduling."),
        ("Process Synchronization", "Critical section, semaphores and monitors."),
        ("Deadlock", "Detection, avoidance and prevention."),
        ("Memory Management", "Paging, segmentation and virtual memory."),
        ("File Systems and Disk Management", "File access, directories and disk scheduling."),
    ],
    "Computer Networks": [
        ("Introduction", "Network types, topologies and reference models."),
        ("Physical Layer", "Transmission media and switching."),
        ("Data Link Layer", "Framing, error control and MAC protocols."),
        ("Network Layer", "IP addressing, subnetting and routing."),
        ("Transport Layer", "TCP, UDP and congestion control."),
        ("Application Layer", "DNS, HTTP, e-mail and FTP."),
    ],
}


class Command(BaseCommand):
    help = "Load all classes (Nursery-12), extra programs and BSc CSIT semester-wise subjects (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        # --- Levels -------------------------------------------------------
        for order, (name, subtitle, icon) in enumerate(CLASSES):
            level, created = Level.objects.get_or_create(
                slug=slugify(name),
                defaults=dict(name=name, subtitle=subtitle, icon=icon, category=Level.SCHOOL, order=order),
            )
            if not created and level.order != order:  # keep the chip row in Nursery -> 12 order
                level.order = order
                level.save(update_fields=["order"])
        for i, (name, subtitle, icon) in enumerate([("Bachelor", "Undergraduate", "🎓"),
                                                    ("Master", "Postgraduate", "🎖️"),
                                                    ("PhD", "Doctorate", "🏆")]):
            Level.objects.get_or_create(
                slug=slugify(name),
                defaults=dict(name=name, subtitle=subtitle, icon=icon, category=Level.DEGREE, order=100 + i))

        # --- Programs -----------------------------------------------------
        for level_slug, name, duration, icon in EXTRA_PROGRAMS:
            level = Level.objects.get(slug=level_slug)
            Program.objects.get_or_create(
                slug=slugify(name), defaults=dict(level=level, name=name, duration=duration, icon=icon,
                                                  order=Program.objects.filter(level=level).count()))

        # --- School subjects ---------------------------------------------
        made = 0
        for name, _, _ in CLASSES:
            level = Level.objects.get(slug=slugify(name))
            for sub in subjects_for(name):
                _, created = Subject.objects.get_or_create(
                    level=level, program=None, name=sub,
                    defaults=dict(description=f"{sub} for {name}: notes, books, videos and practice questions."))
                made += created

        # --- BSc CSIT -----------------------------------------------------
        bachelor = Level.objects.get(slug="bachelor")
        csit, _ = Program.objects.get_or_create(
            slug="bsc-csit", defaults=dict(level=bachelor, name="BSc CSIT", duration="4 Years", icon="💻", order=0))
        for semester, names in CSIT.items():
            for sub in names:
                subject, created = Subject.objects.get_or_create(
                    level=bachelor, program=csit, name=sub,
                    defaults=dict(semester=semester,
                                  description=f"{sub} - BSc CSIT, Semester {semester}."))
                if not created and subject.semester is None:
                    subject.semester = semester
                    subject.save(update_fields=["semester"])
                made += created
                chapters = CSIT_CHAPTERS.get(sub)
                if chapters and not subject.chapters.exists():
                    for i, (title, desc) in enumerate(chapters, start=1):
                        Chapter.objects.create(subject=subject, order=i, title=title, description=desc,
                                               topics_count=4 + i % 4, activities_count=2 + i % 3)

        self.stdout.write(self.style.SUCCESS(
            f"Done. {Level.objects.count()} levels, {Program.objects.count()} programs, "
            f"{Subject.objects.count()} subjects ({made} new)."))
