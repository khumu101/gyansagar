import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import verification
from core.models import Level, Program, Resource, ResourceReport, Subject
from learning.models import Assignment, Attempt, Choice, Question, Quiz, Submission

User = get_user_model()


def make_user(name, role="student", **extra):
    user = User.objects.create_user(name, f"{name}@example.com", "abc123", **extra)
    user.profile.role = role
    user.profile.save()
    return user


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.level = Level.objects.create(name="Class 10", subtitle="SEE", icon="🏫")
        cls.other_level = Level.objects.create(name="Class 5", subtitle="Basic", icon="🏫")
        cls.subject = Subject.objects.create(level=cls.level, name="Science")
        cls.other_subject = Subject.objects.create(level=cls.other_level, name="Nepali")

    def setUp(self):
        cache.clear()


# ----------------------------------------------------------------------------- e-mail verification
class VerificationTests(Base):
    def signup(self, client=None, name="newbie"):
        return (client or self.client).post("/accounts/signup/", {
            "first_name": "N", "username": name, "email": f"{name}@example.com",
            "password1": "abc123", "password2": "abc123"})

    def test_signup_sends_link_and_user_starts_unverified(self):
        self.signup()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/accounts/verify/", mail.outbox[0].body)
        self.assertFalse(User.objects.get(username="newbie").profile.email_verified)

    def test_link_verifies(self):
        self.signup()
        link = [w for w in mail.outbox[0].body.split() if "/accounts/verify/" in w][0]
        path = link[link.index("/accounts/"):]
        self.client.get(path)
        self.assertTrue(User.objects.get(username="newbie").profile.email_verified)

    def test_garbage_and_expired_links_rejected(self):
        user = make_user("bob")
        self.assertEqual(self.client.get("/accounts/verify/garbage/").status_code, 302)
        self.assertFalse(User.objects.get(pk=user.pk).profile.email_verified)
        token = verification.make_token(user)
        with override_settings(EMAIL_VERIFY_MAX_AGE_HOURS=0):
            self.client.get(f"/accounts/verify/{token}/")
        self.assertFalse(User.objects.get(pk=user.pk).profile.email_verified)

    def test_link_dies_when_email_changes(self):
        user = make_user("bob")
        token = verification.make_token(user)
        user.email = "other@example.com"
        user.save()
        self.client.get(f"/accounts/verify/{token}/")
        self.assertFalse(User.objects.get(pk=user.pk).profile.email_verified)

    def test_banner_and_resend(self):
        make_user("bob")
        self.client.login(username="bob", password="abc123")
        self.assertContains(self.client.get("/"), "Please verify your e-mail")
        self.client.post(reverse("accounts:resend_verification"))
        self.assertEqual(len(mail.outbox), 1)

    def test_changing_email_resets_verification(self):
        user = make_user("bob")
        user.profile.email_verified = True
        user.profile.save()
        self.client.login(username="bob", password="abc123")
        self.client.post("/accounts/profile/", {"first_name": "B", "last_name": "", "email": "new@example.com",
                                                "phone": "", "level": "", "program": "", "bio": ""})
        self.assertFalse(User.objects.get(pk=user.pk).profile.email_verified)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(REQUIRE_VERIFIED_EMAIL=True)
    def test_gate_blocks_community_post_until_verified(self):
        user = make_user("bob")
        self.client.login(username="bob", password="abc123")
        self.assertEqual(self.client.get(reverse("portal:post_new")).status_code, 302)
        user.profile.email_verified = True
        user.profile.save()
        self.assertEqual(self.client.get(reverse("portal:post_new")).status_code, 200)

    def test_gate_off_by_default_and_superuser_always_ok(self):
        make_user("bob")
        self.client.login(username="bob", password="abc123")
        self.assertEqual(self.client.get(reverse("portal:post_new")).status_code, 200)
        admin = User.objects.create_superuser("root", "r@example.com", "abc123")
        self.assertTrue(verification.is_verified(admin))


# ----------------------------------------------------------------------------- reports
class ReportTests(Base):
    def setUp(self):
        super().setUp()
        self.res = Resource.objects.create(subject=self.subject, title="Notes", external_url="https://example.com/x")

    def test_login_required(self):
        self.assertEqual(self.client.get(reverse("core:resource_report", args=[self.res.pk])).status_code, 302)

    def test_report_once_per_user_and_autohide(self):
        with override_settings(REPORT_AUTOHIDE_THRESHOLD=2):
            for i in range(2):
                c = Client()
                make_user(f"u{i}")
                c.login(username=f"u{i}", password="abc123")
                c.post(reverse("core:resource_report", args=[self.res.pk]), {"reason": "wrong", "note": ""})
                c.post(reverse("core:resource_report", args=[self.res.pk]), {"reason": "wrong", "note": ""})  # duplicate
                self.res.refresh_from_db()
                self.assertEqual(self.res.is_published, i == 0)
        self.assertEqual(ResourceReport.objects.count(), 2)

    def test_admin_can_restore(self):
        make_user("u1")
        self.client.login(username="u1", password="abc123")
        self.client.post(reverse("core:resource_report", args=[self.res.pk]), {"reason": "broken", "note": ""})
        admin = Client()
        User.objects.create_superuser("root", "r@example.com", "abc123")
        admin.login(username="root", password="abc123")
        Resource.objects.filter(pk=self.res.pk).update(is_published=False)
        admin.post(reverse("admin:core_resourcereport_changelist"), {
            "action": "restore_resources", "_selected_action": [ResourceReport.objects.get().pk]})
        self.res.refresh_from_db()
        self.assertTrue(self.res.is_published)
        self.assertTrue(ResourceReport.objects.get().resolved)

    def test_search_finds_resource_titles(self):
        r = self.client.get("/search/", {"q": "Notes"})
        self.assertContains(r, "Notes")
        self.assertContains(r, "Notes &amp; materials")


# ----------------------------------------------------------------------------- quizzes
class QuizTests(Base):
    def setUp(self):
        super().setUp()
        self.quiz = Quiz.objects.create(subject=self.subject, title="Unit 1", is_published=True, pass_percent=50)
        self.q1 = Question.objects.create(quiz=self.quiz, text="2+2?", order=1, explanation="Because arithmetic")
        self.q2 = Question.objects.create(quiz=self.quiz, text="Sky colour?", order=2)
        self.q1a, self.q1b = (Choice.objects.create(question=self.q1, text=t, is_correct=c) for t, c in (("4", True), ("5", False)))
        self.q2a, self.q2b = (Choice.objects.create(question=self.q2, text=t, is_correct=c) for t, c in (("Blue", True), ("Red", False)))
        self.user = make_user("stu")
        self.client.login(username="stu", password="abc123")

    def test_correct_answers_not_in_page(self):
        html = self.client.get(self.quiz.get_absolute_url()).content.decode()
        self.assertIn("2+2?", html)
        self.assertNotIn("Because arithmetic", html)  # explanation only after submitting

    def test_grading_server_side(self):
        r = self.client.post(self.quiz.get_absolute_url(), {f"q{self.q1.pk}": self.q1a.pk, f"q{self.q2.pk}": self.q2b.pk})
        attempt = Attempt.objects.get()
        self.assertRedirects(r, attempt.get_absolute_url())
        self.assertEqual((attempt.score, attempt.total, attempt.percent, attempt.passed), (1, 2, 50, True))
        page = self.client.get(attempt.get_absolute_url())
        self.assertContains(page, "Correct answer")
        self.assertContains(page, "Blue")

    def test_forged_choice_from_other_question_ignored(self):
        self.client.post(self.quiz.get_absolute_url(), {f"q{self.q1.pk}": self.q2a.pk, f"q{self.q2.pk}": self.q2a.pk})
        self.assertEqual(Attempt.objects.get().score, 1)  # only q2 counted

    def test_empty_submission_rejected(self):
        r = self.client.post(self.quiz.get_absolute_url(), {})
        self.assertContains(r, "answer at least one")
        self.assertEqual(Attempt.objects.count(), 0)

    def test_login_required_and_unpublished_hidden(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.quiz.get_absolute_url()).status_code, 302)
        self.client.login(username="stu", password="abc123")
        Quiz.objects.update(is_published=False)
        self.assertEqual(self.client.get(self.quiz.get_absolute_url()).status_code, 404)

    def test_others_cannot_view_my_attempt_but_teacher_can(self):
        self.client.post(self.quiz.get_absolute_url(), {f"q{self.q1.pk}": self.q1a.pk})
        url = Attempt.objects.get().get_absolute_url()
        make_user("other")
        c = Client(); c.login(username="other", password="abc123")
        self.assertEqual(c.get(url).status_code, 404)
        make_user("tea", role="teacher")
        c.login(username="tea", password="abc123")
        self.assertEqual(c.get(url).status_code, 200)

    def test_list_filters_by_my_class(self):
        Quiz.objects.create(subject=self.other_subject, title="Nepali quiz", is_published=True)
        q = Question.objects.create(quiz=Quiz.objects.get(title="Nepali quiz"), text="x")
        Choice.objects.create(question=q, text="a", is_correct=True)
        self.user.profile.level = self.level
        self.user.profile.save()
        page = self.client.get(reverse("learning:quizzes"))
        self.assertContains(page, "Unit 1")
        self.assertNotContains(page, "Nepali quiz")
        self.assertContains(self.client.get(reverse("learning:quizzes"), {"all": 1}), "Nepali quiz")

    def test_home_dashboard(self):
        self.client.post(self.quiz.get_absolute_url(), {f"q{self.q1.pk}": self.q1a.pk, f"q{self.q2.pk}": self.q2a.pk})
        self.assertContains(self.client.get(reverse("learning:home")), "Unit 1")


class QuizAdminTests(Base):
    def test_choice_validation_in_admin(self):
        User.objects.create_superuser("root", "r@example.com", "abc123")
        self.client.login(username="root", password="abc123")
        quiz = Quiz.objects.create(subject=self.subject, title="T")
        question = Question.objects.create(quiz=quiz, text="Q?")
        url = reverse("admin:learning_question_change", args=[question.pk])
        base = {"quiz": quiz.pk, "text": "Q?", "explanation": "", "order": 1,
                "choices-TOTAL_FORMS": 4, "choices-INITIAL_FORMS": 0, "choices-MIN_NUM_FORMS": 0, "choices-MAX_NUM_FORMS": 1000}
        two_correct = dict(base, **{"choices-0-text": "a", "choices-0-is_correct": "on",
                                    "choices-1-text": "b", "choices-1-is_correct": "on"})
        self.assertContains(self.client.post(url, two_correct), "exactly ONE")
        ok = dict(base, **{"choices-0-text": "a", "choices-0-is_correct": "on", "choices-1-text": "b"})
        self.assertEqual(self.client.post(url, ok).status_code, 302)
        self.assertEqual(question.choices.count(), 2)


# ----------------------------------------------------------------------------- assignments
class AssignmentTests(Base):
    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        ov = override_settings(MEDIA_ROOT=self._tmp.name)
        ov.enable()
        self.addCleanup(ov.disable)
        self.teacher = make_user("tea", role="teacher")
        self.other_teacher = make_user("tea2", role="teacher")
        self.stu = make_user("stu")
        self.assignment = Assignment.objects.create(subject=self.subject, title="Essay", max_marks=10, created_by=self.teacher,
                                                    due_at=timezone.now() + timedelta(days=2))
        self.url = self.assignment.get_absolute_url()

    def login(self, name):
        c = Client()
        c.login(username=name, password="abc123")
        return c

    def test_submit_text_and_file_and_resubmit(self):
        c = self.login("stu")
        self.assertEqual(c.post(self.url, {"text": "my answer"}).status_code, 302)
        self.assertEqual(Submission.objects.count(), 1)
        f = SimpleUploadedFile("work.pdf", b"%PDF-1.4", content_type="application/pdf")
        c.post(self.url, {"text": "v2", "file": f})
        sub = Submission.objects.get()  # still one row (re-submit replaces)
        self.assertEqual((sub.text, sub.filename), ("v2", "work.pdf"))

    def test_empty_and_bad_extension_rejected(self):
        c = self.login("stu")
        self.assertContains(c.post(self.url, {"text": ""}), "Write an answer or attach a file")
        bad = SimpleUploadedFile("virus.exe", b"MZ")
        self.assertContains(c.post(self.url, {"text": "x", "file": bad}), "not allowed")
        self.assertEqual(Submission.objects.count(), 0)

    def test_only_owner_teacher_can_download_file(self):
        c = self.login("stu")
        c.post(self.url, {"text": "x", "file": SimpleUploadedFile("work.pdf", b"%PDF-1.4")})
        file_url = reverse("learning:submission_file", args=[Submission.objects.get().pk])
        self.assertEqual(c.get(file_url).status_code, 200)
        self.assertEqual(self.login("tea").get(file_url).status_code, 200)
        self.assertEqual(self.login("tea2").get(file_url).status_code, 404)  # other teacher's assignment
        make_user("snoop")
        self.assertEqual(self.login("snoop").get(file_url).status_code, 404)
        self.assertEqual(Client().get(file_url).status_code, 302)

    def test_grading_flow_and_limits(self):
        self.login("stu").post(self.url, {"text": "x"})
        sub = Submission.objects.get()
        grade_url = reverse("learning:grade_submission", args=[sub.pk])
        t = self.login("tea")
        self.assertContains(t.post(grade_url, {"marks": "11", "feedback": ""}), "between 0 and 10")
        self.assertEqual(t.post(grade_url, {"marks": "8.5", "feedback": "Good"}).status_code, 302)
        sub.refresh_from_db()
        self.assertEqual((float(sub.marks), sub.graded_by_id), (8.5, self.teacher.pk))
        # student can see the grade and can no longer re-submit
        c = self.login("stu")
        self.assertContains(c.get(self.url), "Good")
        c.post(self.url, {"text": "sneaky edit"})
        sub.refresh_from_db()
        self.assertEqual(sub.text, "x")

    def test_students_and_other_teachers_cannot_grade(self):
        self.login("stu").post(self.url, {"text": "x"})
        sub = Submission.objects.get()
        grade_url = reverse("learning:grade_submission", args=[sub.pk])
        self.assertEqual(self.login("stu").get(grade_url).status_code, 403)
        self.assertEqual(self.login("tea2").get(grade_url).status_code, 404)
        self.assertEqual(self.login("stu").get(reverse("learning:grading")).status_code, 403)
        self.assertContains(self.login("tea").get(reverse("learning:grading")), "Essay")

    def test_late_flag(self):
        Assignment.objects.update(due_at=timezone.now() - timedelta(hours=1))
        self.login("stu").post(self.url, {"text": "x"})
        self.assertTrue(Submission.objects.get().is_late)

    def test_teachers_group_has_learning_permissions(self):
        from django.contrib.auth.models import Group
        names = set(Group.objects.get(name="Teachers").permissions.values_list("codename", flat=True))
        self.assertTrue({"add_quiz", "change_assignment", "add_choice"} <= names)
        self.assertNotIn("change_submission", names)


# ----------------------------------------------------------------------------- dashboard
class DashboardTests(Base):
    def test_staff_only(self):
        self.assertEqual(self.client.get(reverse("learning:dashboard")).status_code, 302)
        make_user("stu")
        self.client.login(username="stu", password="abc123")
        self.assertEqual(self.client.get(reverse("learning:dashboard")).status_code, 302)

    def test_numbers_render(self):
        User.objects.create_superuser("root", "r@example.com", "abc123")
        Resource.objects.create(subject=self.subject, title="Popular", external_url="https://example.com", )
        Resource.objects.update(download_count=7)
        self.client.login(username="root", password="abc123")
        r = self.client.get(reverse("learning:dashboard"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Popular")
        self.assertContains(r, "Site statistics")
