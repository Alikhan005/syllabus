from pathlib import Path

from django.contrib.auth import get_user_model
from django.conf import settings
from django.core import mail
from django.test import SimpleTestCase, TestCase
from django.test import override_settings
from django.urls import reverse

from core.announcements import announcement_author_role_label
from catalog.models import Course
from syllabi.models import Syllabus
from workflow.services import change_status


User = get_user_model()
MOJIBAKE_MARKERS = ("РџР", "РЎР", "Р“Р", "СЃР", "С‚Р")


class SecuritySettingsTests(SimpleTestCase):
    def test_secure_proxy_ssl_header_is_configured_for_reverse_proxies(self):
        self.assertEqual(
            settings.SECURE_PROXY_SSL_HEADER,
            ("HTTP_X_FORWARDED_PROTO", "https"),
        )


class DiagnosticsAccessTests(TestCase):
    def test_healthz_is_public(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)

    def test_diagnostics_requires_privileged_user(self):
        response = self.client.get(reverse("diagnostics"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_diagnostics(self):
        admin_user = User.objects.create_user(
            username="diag_admin",
            password="pass1234",
            role="admin",
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("diagnostics"))
        self.assertNotEqual(response.status_code, 403)


class DashboardEncodingTests(TestCase):
    def test_dean_dashboard_contains_normal_russian_text(self):
        dean_user = User.objects.create_user(
            username="dean_utf8",
            password="pass1234",
            role="dean",
        )
        self.client.force_login(dean_user)

        response = self.client.get(reverse("dashboard"))
        content = response.content.decode("utf-8", errors="strict")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Панель управления", content)
        self.assertIn("Просматривайте силлабусы на согласовании", content)
        for marker in MOJIBAKE_MARKERS:
            self.assertNotIn(marker, content)

    def test_html_templates_do_not_contain_mojibake_markers(self):
        templates_dir = Path(settings.BASE_DIR) / "templates"
        html_files = sorted(templates_dir.rglob("*.html"))
        self.assertGreater(len(html_files), 0, "No HTML templates found in templates/")

        for html_file in html_files:
            content = html_file.read_text(encoding="utf-8")
            for marker in MOJIBAKE_MARKERS:
                self.assertNotIn(marker, content, f"Found '{marker}' in {html_file}")


class DashboardNotificationsTests(TestCase):
    def test_teacher_sees_only_own_notification(self):
        teacher = User.objects.create_user(
            username="teacher_notice",
            password="pass1234",
            role="teacher",
        )
        other_teacher = User.objects.create_user(
            username="teacher_other_notice",
            password="pass1234",
            role="teacher",
        )
        reviewer = User.objects.create_user(
            username="umu_notice",
            password="pass1234",
            role="umu",
        )
        course = Course.objects.create(owner=teacher, code="CS777", available_languages="ru")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2026",
            academic_year="2026-2027",
            status=Syllabus.Status.REVIEW_UMU,
        )
        change_status(reviewer, syllabus, Syllabus.Status.CORRECTION, "UNIQUE_NOTICE_MARKER")

        self.client.force_login(teacher)
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("sidebar_notifications", response.context)
        notifications = response.context["sidebar_notifications"]
        self.assertTrue(any(item["syllabus_id"] == syllabus.id for item in notifications))
        self.assertTrue(any(item["body"] == "UNIQUE_NOTICE_MARKER" for item in notifications))

        self.client.force_login(other_teacher)
        other_response = self.client.get(reverse("dashboard"))
        other_notifications = other_response.context["sidebar_notifications"]
        self.assertFalse(any(item["body"] == "UNIQUE_NOTICE_MARKER" for item in other_notifications))

    def test_dean_sees_incoming_review_notifications(self):
        teacher = User.objects.create_user(
            username="teacher_dean_notice",
            password="pass1234",
            role="teacher",
        )
        dean = User.objects.create_user(
            username="dean_notice",
            password="pass1234",
            role="dean",
        )
        course = Course.objects.create(owner=teacher, code="MATH555", available_languages="ru")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Spring 2026",
            academic_year="2025-2026",
            status=Syllabus.Status.AI_CHECK,
        )
        change_status(teacher, syllabus, Syllabus.Status.REVIEW_DEAN, "READY_FOR_DEAN")

        self.client.force_login(dean)
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        notifications = response.context["sidebar_notifications"]
        self.assertTrue(any(item["syllabus_id"] == syllabus.id for item in notifications))
        self.assertTrue(any(item["body"] == "READY_FOR_DEAN" for item in notifications))

    def test_mark_notifications_read_resets_unread_counter(self):
        teacher = User.objects.create_user(
            username="teacher_mark_read",
            password="pass1234",
            role="teacher",
        )
        reviewer = User.objects.create_user(
            username="dean_mark_read",
            password="pass1234",
            role="dean",
        )
        course = Course.objects.create(owner=teacher, code="IT888", available_languages="ru")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2026",
            academic_year="2026-2027",
            status=Syllabus.Status.REVIEW_DEAN,
        )
        change_status(reviewer, syllabus, Syllabus.Status.CORRECTION, "FIRST_NOTICE")

        self.client.force_login(teacher)
        before_read = self.client.get(reverse("dashboard"))
        self.assertEqual(before_read.context["sidebar_notifications_count"], 1)

        mark_read_response = self.client.post(reverse("notifications_mark_read"))
        self.assertEqual(mark_read_response.status_code, 200)
        self.assertEqual(mark_read_response.json()["unread_count"], 0)

        after_read = self.client.get(reverse("dashboard"))
        self.assertEqual(after_read.context["sidebar_notifications_count"], 0)

        change_status(teacher, syllabus, Syllabus.Status.REVIEW_DEAN, "RESUBMITTED")
        change_status(reviewer, syllabus, Syllabus.Status.CORRECTION, "SECOND_NOTICE")
        after_new_log = self.client.get(reverse("dashboard"))
        self.assertEqual(after_new_log.context["sidebar_notifications_count"], 1)

    def test_mark_read_is_isolated_per_user(self):
        teacher = User.objects.create_user(
            username="teacher_isolated_notice",
            password="pass1234",
            role="teacher",
        )
        dean_one = User.objects.create_user(
            username="dean_one_notice",
            password="pass1234",
            role="dean",
        )
        dean_two = User.objects.create_user(
            username="dean_two_notice",
            password="pass1234",
            role="dean",
        )
        course = Course.objects.create(owner=teacher, code="CS909", available_languages="ru")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Spring 2027",
            academic_year="2026-2027",
            status=Syllabus.Status.AI_CHECK,
        )
        change_status(teacher, syllabus, Syllabus.Status.REVIEW_DEAN, "READY_FOR_TWO_DEANS")

        self.client.force_login(dean_one)
        dean_one_before = self.client.get(reverse("dashboard"))
        self.assertEqual(dean_one_before.context["sidebar_notifications_count"], 1)
        self.client.post(reverse("notifications_mark_read"))
        dean_one_after = self.client.get(reverse("dashboard"))
        self.assertEqual(dean_one_after.context["sidebar_notifications_count"], 0)

        self.client.force_login(dean_two)
        dean_two_response = self.client.get(reverse("dashboard"))
        self.assertEqual(dean_two_response.context["sidebar_notifications_count"], 1)
        self.assertTrue(
            any(item["body"] == "READY_FOR_TWO_DEANS" for item in dean_two_response.context["sidebar_notifications"])
        )

    def test_mark_notifications_read_requires_authentication(self):
        response = self.client.post(reverse("notifications_mark_read"))
        self.assertEqual(response.status_code, 302)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AnnouncementEmailTests(TestCase):
    def test_dean_announcement_is_emailed_to_teachers_and_program_leaders(self):
        dean = User.objects.create_user(
            username="dean_announce",
            password="pass1234",
            role="dean",
            email="dean@example.com",
        )
        teacher = User.objects.create_user(
            username="teacher_announce",
            password="pass1234",
            role="teacher",
            email="teacher@example.com",
        )
        program_leader = User.objects.create_user(
            username="pl_announce",
            password="pass1234",
            role="program_leader",
            email="pl@example.com",
        )
        User.objects.create_user(
            username="umu_announce",
            password="pass1234",
            role="umu",
            email="umu@example.com",
        )

        self.client.force_login(dean)
        response = self.client.post(
            reverse("announcement_create"),
            {
                "title": "Важное объявление",
                "body": "Проверьте обновленные требования.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

        sent_message = mail.outbox[0]
        self.assertEqual(sent_message.subject, "Новое объявление: Важное объявление")
        self.assertEqual(set(sent_message.bcc), {teacher.email, program_leader.email})
        self.assertNotIn(dean.email, sent_message.bcc)
        self.assertEqual(len(sent_message.alternatives), 1)
        html_body, mime_type = sent_message.alternatives[0]
        self.assertEqual(mime_type, "text/html")
        self.assertIn("Важное объявление", html_body)
        self.assertIn("Открыть в системе", html_body)


    def test_email_mentions_author_role_and_name(self):
        dean = User.objects.create_user(
            username="dean_announce_role",
            password="pass1234",
            role="dean",
            first_name="Айжан",
            last_name="Серикова",
            email="dean-role@example.com",
        )
        User.objects.create_user(
            username="teacher_announce_role",
            password="pass1234",
            role="teacher",
            email="teacher-role@example.com",
        )

        self.client.force_login(dean)
        response = self.client.post(
            reverse("announcement_create"),
            {
                "title": "Проверка роли",
                "body": "Покажите роль автора в письме.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        sent_message = mail.outbox[0]
        html_body, mime_type = sent_message.alternatives[0]

        self.assertEqual(mime_type, "text/html")
        self.assertIn(dean.get_role_display(), html_body)
        self.assertIn(dean.get_role_display(), sent_message.body)
        self.assertIn(dean.get_full_name(), html_body)


class AnnouncementDashboardTests(TestCase):
    def test_dashboard_shows_author_role_for_announcements(self):
        umu = User.objects.create_user(
            username="umu_dashboard_announcement",
            password="pass1234",
            role="umu",
            first_name="Алия",
            last_name="Нурбек",
        )
        teacher = User.objects.create_user(
            username="teacher_dashboard_announcement",
            password="pass1234",
            role="teacher",
        )
        umu.announcements.create(
            title="Новое правило",
            body="Проверьте обновленные сроки.",
        )

        self.client.force_login(teacher)
        response = self.client.get(reverse("dashboard"))
        content = response.content.decode("utf-8", errors="strict")

        self.assertEqual(response.status_code, 200)
        self.assertIn(announcement_author_role_label(umu), content)
        self.assertIn(umu.get_full_name(), content)


class AnnouncementDeleteTests(TestCase):
    def test_author_can_delete_own_announcement(self):
        dean = User.objects.create_user(
            username="dean_delete_own",
            password="pass1234",
            role="dean",
        )
        announcement = dean.announcements.create(
            title="Удаляемое объявление",
            body="Текст объявления",
        )

        self.client.force_login(dean)
        response = self.client.post(reverse("announcement_delete", args=[announcement.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(type(announcement).objects.filter(pk=announcement.pk).exists())

    def test_other_reviewer_cannot_delete_foreign_announcement(self):
        dean = User.objects.create_user(
            username="dean_delete_author",
            password="pass1234",
            role="dean",
        )
        umu = User.objects.create_user(
            username="umu_delete_foreign",
            password="pass1234",
            role="umu",
        )
        announcement = dean.announcements.create(
            title="Чужое объявление",
            body="Текст объявления",
        )

        self.client.force_login(umu)
        response = self.client.post(reverse("announcement_delete", args=[announcement.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(type(announcement).objects.filter(pk=announcement.pk).exists())

    def test_delete_requires_post(self):
        dean = User.objects.create_user(
            username="dean_delete_method",
            password="pass1234",
            role="dean",
        )
        announcement = dean.announcements.create(
            title="Метод удаления",
            body="Текст объявления",
        )

        self.client.force_login(dean)
        response = self.client.get(reverse("announcement_delete", args=[announcement.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(type(announcement).objects.filter(pk=announcement.pk).exists())
