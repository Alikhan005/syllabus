from pathlib import Path

from django import forms
from django.db.models import Q
from catalog.models import Course
from catalog.services import dedupe_courses_queryset
from .models import Syllabus


ALLOWED_SYLLABUS_UPLOAD_EXTENSIONS = {".pdf", ".doc", ".docx"}


def is_allowed_syllabus_file_name(filename: str) -> bool:
    suffix = Path(filename or "").suffix.lower()
    return suffix in ALLOWED_SYLLABUS_UPLOAD_EXTENSIONS


class SyllabusForm(forms.ModelForm):
    """
    Основная форма для создания/загрузки силлабуса.
    Используется и для Конструктора (без файла), и для Импорта (с файлом).
    """
    # Явно указываем required=False, чтобы Конструктор мог работать без загрузки файла
    pdf_file = forms.FileField(
        required=False, 
        widget=forms.FileInput(
            attrs={
                "class": "editor-file-input",
                "accept": ".pdf,.docx,.doc",
                "style": "display: none;",
            }
        ),
        label="Файл силлабуса (PDF или Word)",
        help_text="Загрузите готовый файл. Система автоматически отправит его на проверку ИИ."
    )
    manual_course_name = forms.CharField(
        required=False,
        max_length=255,
        label="Название дисциплины вручную",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Введите название дисциплины",
            }
        ),
        help_text="Это личное название будет видно вам. Другим пользователям система покажет, что дисциплина указана автором вручную.",
    )

    class Meta:
        model = Syllabus
        fields = [
            "course",
            "manual_course_name",
            "semester",
            "academic_year",
            "main_language",
            "pdf_file",
        ]
        widgets = {
            "course": forms.Select(attrs={"class": "form-control"}),
            "semester": forms.TextInput(attrs={"class": "form-control", "placeholder": "Например: Осень 2026"}),
            "academic_year": forms.TextInput(attrs={"class": "form-control", "placeholder": "2025-2026"}),
            "main_language": forms.Select(attrs={"class": "form-select"}),
        }
        labels = {
            "course": "Дисциплина",
            "semester": "Семестр",
            "academic_year": "Учебный год",
            "main_language": "Язык силлабуса",
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.user = user
        self.course_canonical_map = {}
        self.show_course_owner = False
        
        # Мы убрали принудительное self.fields['pdf_file'].required = True
        # Теперь валидация (нужен файл или нет) управляется логикой во views.py
        
        if user:
            # Фильтрация курсов: Админ видит всё, Препод — только свои
            if getattr(user, "role", None) == "admin" or user.is_superuser:
                base_queryset = Course.objects.filter(Q(is_manual=False) | Q(owner=user))
                self.show_course_owner = True
            else:
                base_queryset = user.courses.all()

            deduped_queryset, canonical_map = dedupe_courses_queryset(base_queryset)
            self.fields["course"].queryset = deduped_queryset
            self.course_canonical_map = canonical_map
        
        self.fields["course"].required = False
        self.fields["course"].empty_label = "Выберите дисциплину из списка"
        self.fields["course"].help_text = "Можно выбрать дисциплину из списка или ввести название вручную ниже."
        self.fields["course"].label_from_instance = self._course_label_from_instance

    def _course_label_from_instance(self, course: Course) -> str:
        label = course.code
        title = course.display_title
        if title and title.strip().casefold() != course.code.strip().casefold():
            label = f"{label} - {title}"
        if self.show_course_owner:
            label = f"{label} ({course.owner})"
        return label


    def clean_manual_course_name(self):
        return " ".join((self.cleaned_data.get("manual_course_name") or "").split())


    def clean(self):
        cleaned_data = super().clean()
        course = cleaned_data.get("course")
        manual_course_name = cleaned_data.get("manual_course_name")

        if not course and not manual_course_name:
            self.add_error("course", "Выберите дисциплину из списка или введите название вручную.")

        return cleaned_data


    def clean_pdf_file(self):
        uploaded = self.cleaned_data.get("pdf_file")
        if not uploaded:
            return uploaded
        if not is_allowed_syllabus_file_name(uploaded.name):
            raise forms.ValidationError("Допустимы только файлы PDF и Word (.pdf, .doc, .docx).")
        return uploaded


    def resolve_course(self, user=None) -> Course:
        manual_course_name = self.cleaned_data.get("manual_course_name")
        if manual_course_name:
            return self._get_or_create_manual_course(user or self.user, manual_course_name)
        return self.cleaned_data["course"]


    def _get_or_create_manual_course(self, user, title: str) -> Course:
        existing = Course.objects.filter(owner=user, title_ru__iexact=title, is_manual=True).order_by("id").first()
        if existing:
            return existing

        existing = Course.objects.filter(owner=user, code__iexact=title, is_manual=True).order_by("id").first()
        if existing:
            if not existing.title_ru:
                existing.title_ru = title
                existing.save(update_fields=["title_ru"])
            return existing

        return Course.objects.create(
            owner=user,
            code=self._build_manual_course_code(user, title),
            title_ru=title,
            available_languages=self.cleaned_data.get("main_language") or "ru",
            is_shared=False,
            is_manual=True,
        )


    def _build_manual_course_code(self, user, title: str) -> str:
        max_length = Course._meta.get_field("code").max_length
        base = title[:max_length].strip() or "Дисциплина"
        candidate = base
        index = 2

        while Course.objects.filter(owner=user, code__iexact=candidate).exists():
            suffix = f" {index}"
            prefix_length = max_length - len(suffix)
            candidate = f"{base[:prefix_length].rstrip()}{suffix}" if prefix_length > 0 else str(index)
            index += 1

        return candidate


class SyllabusDetailsForm(forms.ModelForm):
    """
    Форма для редактирования деталей.
    Нужна, если преподаватель захочет поправить метаданные после загрузки.
    """
    class Meta:
        model = Syllabus
        fields = [
            "credits_ects",
            "total_hours",
            "contact_hours",
            "self_study_hours",
            "prerequisites",
            "delivery_format",
            "level",
            "program_name",
            "instructor_name",
            "instructor_contacts",
            "class_schedule",
            "course_description",
            "course_goal",
            "learning_outcomes",
            "teaching_methods",
            "teaching_philosophy",
            "course_policy",
            "academic_integrity_policy",
            "inclusive_policy",
            "assessment_policy",
            "grading_scale",
            "appendix",
            "main_literature",
            "additional_literature",
        ]
        labels = {
            "credits_ects": "Кредиты (ECTS)",
            "total_hours": "Всего часов",
            "contact_hours": "Аудиторные часы",
            "self_study_hours": "Самостоятельная работа (СРОП, СРО)",
            "prerequisites": "Пререквизиты",
            "delivery_format": "Формат обучения",
            "level": "Уровень обучения",
            "program_name": "Образовательная программа",
            "instructor_name": "Преподаватель",
            "instructor_contacts": "Контакты преподавателя",
            "class_schedule": "Время и место проведения занятий",
            "course_description": "Краткое описание курса",
            "course_goal": "Цель курса",
            "learning_outcomes": "Ожидаемые результаты",
            "teaching_methods": "Методы обучения",
            "teaching_philosophy": "Философия преподавания и обучения",
            "course_policy": "Политика курса",
            "academic_integrity_policy": "Академическая честность и использование ИИ",
            "inclusive_policy": "Инклюзивное академическое сообщество",
            "assessment_policy": "Политика оценивания",
            "grading_scale": "Балльно-рейтинговая шкала",
            "appendix": "Приложения и рубрикаторы",
            "main_literature": "Обязательная литература",
            "additional_literature": "Дополнительная литература",
        }
        widgets = {
            "prerequisites": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "instructor_contacts": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "class_schedule": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "course_description": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "course_goal": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "learning_outcomes": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "teaching_methods": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "teaching_philosophy": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "course_policy": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "academic_integrity_policy": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "inclusive_policy": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "assessment_policy": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "grading_scale": forms.Textarea(attrs={"rows": 6, "class": "form-control"}),
            "appendix": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "main_literature": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "additional_literature": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        }
