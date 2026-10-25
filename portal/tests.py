import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Chapter, Level, Subject

from . import ai
from .models import BlogPost, Comment, ContactMessage, Opportunity, Post, School, TutorMessage

User = get_user_model()


class PortalBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.level = Level.objects.create(name="Class Ten", subtitle="Grade 10", icon="x")
        cls.subject = Subject.objects.create(level=cls.level, name="Science")
        cls.user = User.objects.create_user("stu", "stu@example.com", "pw-123456")
        cls.other = User.objects.create_user("oth", "oth@example.com", "pw-123456")
        cls.staff = User.objects.create_user("adm", "adm@example.com", "pw-123456", is_staff=True)


class StaticPagesTests(PortalBase):
    def test_all_portal_pages_render_empty(self):
        self.client.force_login(self.user)
        for name in ("schools", "tools", "blog_list", "scholarships", "careers", "community", "post_new", "tutor", "more"):
            self.assertEqual(self.client.get(reverse(f"portal:{name}")).status_code, 200, name)

    def test_tools_page_has_all_tools(self):
        r = self.client.get(reverse("portal:tools"))
        for text in ("Pomodoro", "GPA Calculator", "Exam Countdown", "Percentage"):
            self.assertContains(r, text)

    def test_schools_search_and_filter(self):
        School.objects.create(name="Sagarmatha School", city="Kathmandu", kind="private")
        School.objects.create(name="Janata School", city="Pokhara", kind="public")
        School.objects.create(name="Hidden", city="Kathmandu", is_published=False)
        r = self.client.get(reverse("portal:schools"), {"q": "kathmandu"})
        self.assertEqual([s.name for s in r.context["page_obj"]], ["Sagarmatha School"])
        r = self.client.get(reverse("portal:schools"), {"type": "public"})
        self.assertEqual([s.name for s in r.context["page_obj"]], ["Janata School"])

    def test_blog_list_detail_and_unpublished(self):
        p = BlogPost.objects.create(title="Study tips", body="Line one\n\nLine two <script>alert(1)</script>")
        hidden = BlogPost.objects.create(title="Draft", body="x", is_published=False)
        self.assertEqual(p.slug, "study-tips")
        self.assertContains(self.client.get(reverse("portal:blog_list")), "Study tips")
        self.assertNotContains(self.client.get(reverse("portal:blog_list")), "Draft")
        r = self.client.get(p.get_absolute_url())
        self.assertContains(r, "Line two")
        self.assertNotContains(r, "<script>alert(1)</script>")  # escaped
        self.assertEqual(self.client.get(hidden.get_absolute_url()).status_code, 404)

    def test_opportunities_open_closed_and_kind_split(self):
        today = timezone.localdate()
        Opportunity.objects.create(kind="scholarship", title="Open one", organization="X", deadline=today)
        Opportunity.objects.create(kind="scholarship", title="Old one", organization="X",
                                   deadline=today - timezone.timedelta(days=3))
        Opportunity.objects.create(kind="career", title="A job", organization="Y")
        r = self.client.get(reverse("portal:scholarships"))
        self.assertEqual([o.title for o in r.context["page_obj"]], ["Open one"])
        r = self.client.get(reverse("portal:scholarships"), {"status": "closed"})
        self.assertEqual([o.title for o in r.context["page_obj"]], ["Old one"])
        r = self.client.get(reverse("portal:careers"))
        self.assertEqual([o.title for o in r.context["page_obj"]], ["A job"])

    def test_apply_url_must_be_http(self):
        from django.core.exceptions import ValidationError
        o = Opportunity(kind="career", title="t", organization="o", apply_url="javascript:alert(1)")
        with self.assertRaises(ValidationError):
            o.full_clean()

    def test_seed_portal_idempotent(self):
        call_command("seed_portal", verbosity=0)
        call_command("seed_portal", verbosity=0)
        self.assertEqual(BlogPost.objects.count(), 3)


class CommunityTests(PortalBase):
    def test_posting_requires_login(self):
        r = self.client.get(reverse("portal:post_new"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("accounts:login"), r["Location"])

    def test_create_post_and_reply(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("portal:post_new"), {"title": "Help with force", "body": "What is F=ma?",
                                                          "level": self.level.pk, "subject": self.subject.pk})
        post = Post.objects.get()
        self.assertRedirects(r, post.get_absolute_url())
        self.client.force_login(self.other)
        r = self.client.post(post.get_absolute_url(), {"body": "Force = mass x acceleration"})
        self.assertEqual(r.status_code, 302)
        self.assertContains(self.client.get(post.get_absolute_url()), "mass x acceleration")
        self.assertContains(self.client.get(reverse("portal:community")), "Help with force")

    def test_guest_can_read_but_reply_redirects_to_login(self):
        post = Post.objects.create(author=self.user, title="Q", body="b")
        self.assertEqual(self.client.get(post.get_absolute_url()).status_code, 200)
        r = self.client.post(post.get_absolute_url(), {"body": "hi"})
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("accounts:login"), r["Location"])
        self.assertEqual(Comment.objects.count(), 0)

    def test_html_in_posts_is_escaped(self):
        post = Post.objects.create(author=self.user, title="<b>t</b>", body="<script>x</script>")
        r = self.client.get(post.get_absolute_url())
        self.assertNotContains(r, "<script>x</script>")

    def test_only_owner_or_staff_can_delete(self):
        post = Post.objects.create(author=self.user, title="Q", body="b")
        url = reverse("portal:post_delete", args=[post.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url).status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 405)  # POST only
        self.client.force_login(self.user)
        self.client.post(url)
        self.assertFalse(Post.objects.exists())

    def test_staff_can_delete_comment_and_hidden_post_404(self):
        post = Post.objects.create(author=self.user, title="Q", body="b")
        c = Comment.objects.create(post=post, author=self.user, body="x")
        self.client.force_login(self.staff)
        self.client.post(reverse("portal:comment_delete", args=[c.pk]))
        self.assertFalse(Comment.objects.exists())
        post.is_hidden = True
        post.save()
        self.client.logout()
        self.assertEqual(self.client.get(post.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse("portal:community")), "Q</h3>")

    def test_post_rate_limit(self):
        self.client.force_login(self.user)
        for i in range(10):
            Post.objects.create(author=self.user, title=f"p{i}", body="b")
        r = self.client.post(reverse("portal:post_new"), {"title": "one more", "body": "b"})
        self.assertContains(r, "too fast")
        self.assertEqual(Post.objects.filter(title="one more").count(), 0)


class TutorTests(PortalBase):
    def test_requires_login(self):
        self.assertEqual(self.client.get(reverse("portal:tutor")).status_code, 302)

    def test_without_key_suggests_related_material(self):
        Chapter.objects.create(subject=self.subject, order=1, title="Newton laws of motion")
        self.client.force_login(self.user)
        r = self.client.post(reverse("portal:tutor"), {"question": "Explain Newton laws"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Newton laws of motion")
        self.assertContains(r, "ANTHROPIC_API_KEY")
        self.assertEqual(TutorMessage.objects.count(), 0)

    @override_settings(ANTHROPIC_API_KEY="test-key")
    def test_with_key_saves_answer_and_sends_history(self):
        self.client.force_login(self.user)
        with mock.patch("portal.ai.ask_tutor", return_value="F = ma, so ...") as m:
            r = self.client.post(reverse("portal:tutor"), {"question": "What is F=ma?", "subject": self.subject.pk})
            self.assertRedirects(r, reverse("portal:tutor"))
            self.client.post(reverse("portal:tutor"), {"question": "Give an example"})
        self.assertEqual(TutorMessage.objects.count(), 2)
        self.assertEqual(m.call_args_list[0].args[2], "Science (Class Ten)")
        self.assertEqual(m.call_args_list[1].args[1], [("What is F=ma?", "F = ma, so ...")])
        self.assertContains(self.client.get(reverse("portal:tutor")), "F = ma, so ...")

    @override_settings(ANTHROPIC_API_KEY="test-key", AI_TUTOR_DAILY_LIMIT=1)
    def test_daily_limit(self):
        self.client.force_login(self.user)
        with mock.patch("portal.ai.ask_tutor", return_value="ok"):
            self.client.post(reverse("portal:tutor"), {"question": "first question"})
            r = self.client.post(reverse("portal:tutor"), {"question": "second question"})
        self.assertContains(r, "Daily limit reached")
        self.assertEqual(TutorMessage.objects.count(), 1)

    @override_settings(ANTHROPIC_API_KEY="test-key")
    def test_ai_error_is_shown_and_not_saved(self):
        self.client.force_login(self.user)
        with mock.patch("portal.ai.ask_tutor", side_effect=ai.AIError("AI is busy")):
            r = self.client.post(reverse("portal:tutor"), {"question": "anything here"})
        self.assertContains(r, "AI is busy")
        self.assertEqual(TutorMessage.objects.count(), 0)

    @override_settings(ANTHROPIC_API_KEY="test-key", AI_TUTOR_MODEL="m1")
    def test_api_request_format(self):
        class Resp:
            def read(self): return json.dumps({"content": [{"type": "text", "text": "Answer!"}]}).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with mock.patch("urllib.request.urlopen", return_value=Resp()) as m:
            text = ai.ask_tutor("Q2", [("Q1", "A1")], "Science (Class Ten)")
        self.assertEqual(text, "Answer!")
        req = m.call_args.args[0]
        body = json.loads(req.data)
        self.assertEqual(body["model"], "m1")
        self.assertEqual([x["role"] for x in body["messages"]], ["user", "assistant", "user"])
        self.assertIn("Science (Class Ten)", body["system"])
        self.assertEqual(req.get_header("X-api-key"), "test-key")

    @override_settings(ANTHROPIC_API_KEY="test-key")
    def test_http_failure_gives_friendly_error(self):
        import urllib.error
        err = urllib.error.HTTPError("u", 401, "bad", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(ai.AIError) as cm:
                ai.ask_tutor("q", [], "")
        self.assertNotIn("test-key", str(cm.exception))

    def test_clear_history(self):
        TutorMessage.objects.create(user=self.user, question="q", answer="a")
        self.client.force_login(self.user)
        self.client.post(reverse("portal:tutor_clear"))
        self.assertEqual(TutorMessage.objects.count(), 0)


class MoreTests(PortalBase):
    def test_contact_form_saves_and_rate_limits(self):
        data = {"name": "A", "email": "a@example.com", "subject": "Hi", "message": "Hello team"}
        r = self.client.post(reverse("portal:more"), data)
        self.assertRedirects(r, reverse("portal:more"))
        self.assertEqual(ContactMessage.objects.count(), 1)
        for _ in range(4):
            self.client.post(reverse("portal:more"), data)
        r = self.client.post(reverse("portal:more"), data)
        self.assertContains(r, "Too many messages")
        self.assertEqual(ContactMessage.objects.count(), 5)

    def test_more_lists_every_section(self):
        r = self.client.get(reverse("portal:more"))
        for label in ("Courses", "Notes", "Community", "Scholarships"):
            self.assertContains(r, label)
