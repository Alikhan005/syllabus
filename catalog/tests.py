from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.forms import CourseForm
from catalog.models import Course, Topic, TopicLiterature, TopicQuestion


User = get_user_model()


class CatalogViewTests(TestCase):
    def _create_user(self, username: str, role: str = "teacher"):
        return User.objects.create_user(username=username, password="pass1234", role=role)

    def _course_payload(self, **overrides):
        payload = {
            "code": "CS101",
            "languages": ["ru", "en"],
            "title_ru": "Тестовый курс",
            "title_en": "Test course",
            "description_ru": "Описание курса",
            "description_en": "Course description",
            "is_shared": "on",
        }
        payload.update(overrides)
        return payload

    def _topic_payload(self, **overrides):
        payload = {
            "order_index": "1",
            "title_ru": "Тема 1",
            "title_en": "Topic 1",
            "default_hours": "2",
            "week_type": "lecture",
            "is_active": "on",
            "lit-TOTAL_FORMS": "1",
            "lit-INITIAL_FORMS": "0",
            "lit-MIN_NUM_FORMS": "0",
            "lit-MAX_NUM_FORMS": "1000",
            "lit-0-title": "Основной учебник",
            "lit-0-author": "Автор",
            "lit-0-year": "2024",
            "lit-0-lit_type": "main",
            "q-TOTAL_FORMS": "1",
            "q-INITIAL_FORMS": "0",
            "q-MIN_NUM_FORMS": "0",
            "q-MAX_NUM_FORMS": "1000",
            "q-0-question_ru": "Что нужно изучить?",
            "q-0-question_en": "What should be studied?",
        }
        payload.update(overrides)
        return payload

    def test_course_create_saves_selected_languages(self):
        teacher = self._create_user("catalog_teacher_create")
        self.client.force_login(teacher)

        response = self.client.post(reverse("course_create"), self._course_payload())

        course = Course.objects.get(code="CS101")
        self.assertRedirects(response, reverse("course_detail", args=[course.pk]))
        self.assertEqual(course.owner, teacher)
        self.assertEqual(course.get_available_languages_list(), ["ru", "en"])
        self.assertTrue(course.is_shared)

    def test_private_course_detail_denies_other_teacher(self):
        owner = self._create_user("catalog_teacher_owner")
        viewer = self._create_user("catalog_teacher_viewer")
        course = Course.objects.create(
            owner=owner,
            code="CS102",
            title_ru="Закрытый курс",
            available_languages="ru",
            is_shared=False,
        )

        self.client.force_login(viewer)
        response = self.client.get(reverse("course_detail", args=[course.pk]))

        self.assertEqual(response.status_code, 403)

    def test_private_course_detail_denies_umu(self):
        owner = self._create_user("catalog_teacher_private_owner")
        umu = self._create_user("catalog_umu_viewer", "umu")
        course = Course.objects.create(
            owner=owner,
            code="CS102U",
            title_ru="Приватный курс",
            available_languages="ru",
            is_shared=False,
        )

        self.client.force_login(umu)
        response = self.client.get(reverse("course_detail", args=[course.pk]))

        self.assertEqual(response.status_code, 403)

    def test_shared_course_detail_hides_management_actions_for_other_teacher(self):
        owner = self._create_user("catalog_teacher_shared_owner")
        viewer = self._create_user("catalog_teacher_shared_viewer")
        course = Course.objects.create(
            owner=owner,
            code="CS102S",
            title_ru="Общий курс",
            available_languages="ru",
            is_shared=True,
        )
        Topic.objects.create(
            course=course,
            order_index=1,
            title_ru="Тема 1",
            default_hours=2,
        )

        self.client.force_login(viewer)
        response = self.client.get(reverse("course_detail", args=[course.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("course_edit", args=[course.pk]))
        self.assertNotContains(response, reverse("topic_create", args=[course.pk]))
        self.assertContains(response, "Это общий курс в режиме просмотра")
        self.assertContains(response, "Взять как основу")

    def test_shared_course_without_topics_shows_view_mode_message_for_other_teacher(self):
        owner = self._create_user("catalog_teacher_view_only_owner")
        viewer = self._create_user("catalog_teacher_view_only_viewer")
        course = Course.objects.create(
            owner=owner,
            code="CS102V",
            title_ru="Пустой общий курс",
            available_languages="ru",
            is_shared=True,
        )

        self.client.force_login(viewer)
        response = self.client.get(reverse("course_detail", args=[course.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Режим просмотра")
        self.assertContains(response, "В этом общем курсе пока нет тем")
        self.assertNotContains(response, "Добавьте первую тему курса")

    def test_shared_course_edit_returns_403_for_other_teacher(self):
        owner = self._create_user("catalog_teacher_edit_owner")
        viewer = self._create_user("catalog_teacher_edit_viewer")
        course = Course.objects.create(
            owner=owner,
            code="CS102E",
            title_ru="Общий курс для проверки",
            available_languages="ru",
            is_shared=True,
        )

        self.client.force_login(viewer)
        response = self.client.get(reverse("course_edit", args=[course.pk]))

        self.assertEqual(response.status_code, 403)

    def test_shared_course_topic_create_returns_403_for_other_teacher(self):
        owner = self._create_user("catalog_teacher_topic_owner")
        viewer = self._create_user("catalog_teacher_topic_viewer")
        course = Course.objects.create(
            owner=owner,
            code="CS102T",
            title_ru="Общий курс для темы",
            available_languages="ru",
            is_shared=True,
        )

        self.client.force_login(viewer)
        response = self.client.get(reverse("topic_create", args=[course.pk]))

        self.assertEqual(response.status_code, 403)

    def test_course_create_rejects_duplicate_code_for_same_owner(self):
        teacher = self._create_user("catalog_teacher_duplicate")
        Course.objects.create(
            owner=teacher,
            code="CS101",
            title_ru="Существующий курс",
            available_languages="ru",
        )
        self.client.force_login(teacher)

        response = self.client.post(reverse("course_create"), self._course_payload(code="CS101"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Курс с таким кодом уже существует")
        self.assertEqual(Course.objects.filter(owner=teacher, code="CS101").count(), 1)

    def test_course_form_allows_same_code_for_different_owner(self):
        owner = self._create_user("catalog_teacher_original")
        another_owner = self._create_user("catalog_teacher_other")
        Course.objects.create(
            owner=owner,
            code="CS101",
            title_ru="Курс первого преподавателя",
            available_languages="ru",
        )

        form = CourseForm(data=self._course_payload(code="CS101"), user=another_owner)

        self.assertTrue(form.is_valid())

    def test_topic_create_saves_formsets(self):
        teacher = self._create_user("catalog_teacher_topic")
        course = Course.objects.create(
            owner=teacher,
            code="CS103",
            title_ru="Курс с темами",
            available_languages="ru,en",
        )
        self.client.force_login(teacher)

        response = self.client.post(reverse("topic_create", args=[course.pk]), self._topic_payload())

        topic = Topic.objects.get(course=course, order_index=1)
        self.assertRedirects(response, reverse("course_detail", args=[course.pk]))
        self.assertEqual(topic.title_ru, "Тема 1")
        self.assertEqual(TopicLiterature.objects.filter(topic=topic).count(), 1)
        self.assertEqual(TopicQuestion.objects.filter(topic=topic).count(), 1)

    def test_shared_course_can_be_forked_with_nested_content(self):
        owner = self._create_user("catalog_teacher_source")
        fork_user = self._create_user("catalog_teacher_fork")
        source = Course.objects.create(
            owner=owner,
            code="CS104",
            title_ru="Общий курс",
            available_languages="ru,en",
            is_shared=True,
        )
        topic = Topic.objects.create(
            course=source,
            order_index=1,
            title_ru="Тема для копирования",
            default_hours=2,
        )
        TopicLiterature.objects.create(
            topic=topic,
            title="Книга для копирования",
            author="Автор",
            year="2024",
            lit_type="main",
        )
        TopicQuestion.objects.create(
            topic=topic,
            question_ru="Контрольный вопрос",
            question_en="Control question",
        )

        self.client.force_login(fork_user)
        response = self.client.post(reverse("course_fork", args=[source.pk]))

        forked = Course.objects.get(owner=fork_user, code="CS104_copy")
        self.assertRedirects(response, reverse("course_detail", args=[forked.pk]))
        self.assertFalse(forked.is_shared)
        self.assertEqual(forked.topics.count(), 1)
        self.assertEqual(forked.topics.first().literature.count(), 1)
        self.assertEqual(forked.topics.first().questions.count(), 1)

    def test_courses_list_hides_duplicate_codes_and_keeps_course_with_content(self):
        teacher = self._create_user("catalog_teacher_list")
        hidden_duplicate = Course.objects.create(
            owner=teacher,
            code="CS105",
            title_ru="Пустой дубль",
            available_languages="ru",
        )
        visible_course = Course.objects.create(
            owner=teacher,
            code="CS105",
            title_ru="Основной курс",
            available_languages="ru",
        )
        Topic.objects.create(
            course=visible_course,
            order_index=1,
            title_ru="Тема 1",
            default_hours=2,
        )

        self.client.force_login(teacher)
        response = self.client.get(reverse("courses_list"))

        self.assertEqual(response.status_code, 200)
        courses = list(response.context["courses"])
        self.assertEqual([course.pk for course in courses], [visible_course.pk])
