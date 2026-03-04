from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from catalog.models import Course
from syllabi.models import Syllabus

from ai_checker.services import _apply_lenient_guardrail, _build_representative_excerpt
from ai_checker.services import _detect_non_syllabus_document
from ai_checker.services import _quick_structure_decision
from ai_checker.services import run_ai_check


class AiCheckGuardrailTests(SimpleTestCase):
    def test_representative_excerpt_keeps_tail_block(self):
        text = "BEGIN " + ("x" * 4200) + " MID_MARKER " + ("y" * 4200) + " LITERATURE_END_MARKER"
        excerpt = _build_representative_excerpt(text)

        self.assertIn("BEGIN", excerpt)
        self.assertIn("LITERATURE_END_MARKER", excerpt)

    def test_lenient_guardrail_auto_approves_structured_syllabus(self):
        weeks = "\n".join([f"Неделя {idx}: Тема {idx}" for idx in range(1, 12)])
        source_text = (
            "Цель курса: сформировать навыки.\n"
            f"{weeks}\n"
            "Основная литература: Современный учебник, 2022."
        )
        result = {"approved": False, "feedback": "<p>Есть рекомендации по детализации.</p>"}

        patched = _apply_lenient_guardrail(result, source_text)

        self.assertTrue(patched["approved"])
        self.assertIn("рекомендации", patched["feedback"])

    def test_lenient_guardrail_keeps_hard_failure(self):
        weeks = "\n".join([f"Неделя {idx}: Тема {idx}" for idx in range(1, 12)])
        source_text = (
            "Цель курса: сформировать навыки.\n"
            f"{weeks}\n"
            "Основная литература: Современный учебник, 2022."
        )
        result = {"approved": False, "feedback": "<p>Файл пустой.</p>"}

        patched = _apply_lenient_guardrail(result, source_text)

        self.assertFalse(patched["approved"])


class AiCheckDocumentTypeTests(SimpleTestCase):
    def test_detect_non_syllabus_document(self):
        text = (
            "INVOICE #2026-001\n"
            "Purchase order and bank statement attached.\n"
            "Quotation for office equipment.\n"
            * 40
        )

        is_non_syllabus, cues = _detect_non_syllabus_document(text)

        self.assertTrue(is_non_syllabus)
        self.assertTrue(cues)

    def test_do_not_mark_valid_syllabus_as_non_syllabus(self):
        weeks = "\n".join([f"Week {idx}: Topic {idx}" for idx in range(1, 12)])
        text = (
            "Course syllabus\n"
            "Course goal: build practical skills.\n"
            "Learning outcomes: apply core concepts.\n"
            f"{weeks}\n"
            "References: Main textbook, 2024."
        )

        is_non_syllabus, cues = _detect_non_syllabus_document(text)

        self.assertFalse(is_non_syllabus)
        self.assertEqual(cues, [])


class AiCheckFastRulesTests(SimpleTestCase):
    def test_fast_rules_auto_approve_full_structure(self):
        weeks = "\n".join([f"Week {idx}: Topic {idx}" for idx in range(1, 12)])
        intro = " ".join(["This syllabus introduces core concepts."] * 15)
        source_text = (
            f"{intro}\nCourse goal: build practical skills.\n"
            f"{weeks}\n"
            "References: Main textbook, 2024."
        )

        result = _quick_structure_decision(source_text)

        self.assertIsNotNone(result)
        self.assertTrue(result["approved"])
        self.assertEqual(result["model_name"], "rules-fast-v1")

    def test_fast_rules_returns_none_for_ambiguous_structure(self):
        weeks = "\n".join([f"Week {idx}: Topic {idx}" for idx in range(1, 12)])
        intro = " ".join(["This syllabus introduces core concepts."] * 15)
        source_text = (
            f"{intro}\nCourse goal: build practical skills.\n"
            f"{weeks}\n"
        )

        result = _quick_structure_decision(source_text)

        self.assertIsNone(result)

    def test_fast_rules_reject_when_core_sections_missing(self):
        source_text = (
            "This file has generic notes only.\n"
            "No syllabus structure is provided.\n"
            * 40
        )

        result = _quick_structure_decision(source_text)

        self.assertIsNotNone(result)
        self.assertFalse(result["approved"])
        self.assertEqual(result["raw_response"], "fast-rules:missing-core-sections")


class AiCheckPersistenceTests(TestCase):
    def test_run_ai_check_persists_feedback_on_syllabus(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="ai_feedback_user",
            password="pass1234",
            role="teacher",
        )
        course = Course.objects.create(owner=user, code="AI-101", available_languages="ru")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=user,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.DRAFT,
            course_description="",
        )

        run_ai_check(syllabus)
        syllabus.refresh_from_db()

        self.assertIn("Ошибка", syllabus.ai_feedback)
