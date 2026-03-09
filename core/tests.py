from pathlib import Path

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

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
