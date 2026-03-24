from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from catalog.models import Course
from syllabi.models import Syllabus
from workflow.models import SyllabusStatusLog

from ai_checker.services import _apply_lenient_guardrail, _build_representative_excerpt
from ai_checker.services import _build_formal_markdown_result
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


class AiCheckFormalRulesTests(SimpleTestCase):
    def test_formal_rules_ignore_table_literature_header_and_parse_plain_week_ranges(self):
        source_text = (
            "1. Краткое описание курса\n"
            "Практический курс по запуску цифрового продукта.\n"
            "Цель курса\n"
            "Сформировать навыки разработки и проверки MVP.\n"
            "Ожидаемые результаты:\n"
            "РО1 - Формулировать JTBD.\n"
            "Методы обучения:\n"
            "Лекции и практика.\n"
            "2. Тематический план по неделям\n"
            "Неделя Тема / модуль Задания Результат обучения Литература Структура оценок\n"
            "1-2 Старт, проблема, JTBD, Value Proposition\n"
            "3-4\n"
            "Применение Lean-методологии в бизнес-моделях\n"
            "5-7 CustDev: потребности клиентов и рынка\n"
            "8 Рубежный контроль 1\n"
            "9\n"
            "Создание клиентоориентированного продукта\n"
            "10-12 Итеративные методы разработки и процессов\n"
            "4. Список литературы\n"
            "Обязательная литература\n"
            "1. Эрик Рис. Бизнес с нуля. 2022.\n"
            "2. Стив Бланк. Стартап. Настольная книга основателя. 2020.\n"
            "Дополнительная литература\n"
            "1. Y Combinator Startup School - How to Plan an MVP - YouTube\n"
            "5. Политика академической честности и использование ИИ\n"
            "Соблюдать требования академической честности.\n"
            "Политика курса\n"
            "Посещаемость и дедлайны обязательны.\n"
            "Философия преподавания и обучения\n"
            "Обучение через практику.\n"
            "Инклюзивное академическое сообщество\n"
            "Курс открыт для всех студентов.\n"
        )

        result = _build_formal_markdown_result(source_text, expected_weeks=12)

        self.assertTrue(result["approved"])
        self.assertNotIn("Структура оценок", result["feedback"])
        self.assertNotIn("недели не распознаны", result["feedback"])


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

        self.assertIn("Summary", syllabus.ai_feedback)


class AiCheckViewTests(TestCase):
    def test_run_check_requires_post_and_logs_queue_transition(self):
        user_model = get_user_model()
        teacher = user_model.objects.create_user(
            username="ai_queue_teacher",
            password="pass1234",
            role="teacher",
        )
        course = Course.objects.create(owner=teacher, code="AI-102", available_languages="ru")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.DRAFT,
        )

        self.client.force_login(teacher)

        get_response = self.client.get(reverse("ai_check_run", args=[syllabus.pk]))
        self.assertEqual(get_response.status_code, 405)

        post_response = self.client.post(reverse("ai_check_run", args=[syllabus.pk]))
        self.assertEqual(post_response.status_code, 302)

        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.AI_CHECK)
        self.assertTrue(
            SyllabusStatusLog.objects.filter(
                syllabus=syllabus,
                from_status=Syllabus.Status.DRAFT,
                to_status=Syllabus.Status.AI_CHECK,
                changed_by=teacher,
            ).exists()
        )
