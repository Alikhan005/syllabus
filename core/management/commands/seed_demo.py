from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from ai_checker.models import AiCheckResult
from catalog.models import Course, Topic, TopicLiterature, TopicQuestion
from core.models import Announcement
from syllabi.models import Syllabus, SyllabusRevision, SyllabusTopic


DEMO_PASSWORD = "Demo12345!"
DEMO_STUDY_WEEKS = 12

USER_SPECS = [
    {
        "username": "admin_demo",
        "email": "admin_demo@almau.local",
        "first_name": "Admin",
        "last_name": "Demo",
        "role": "admin",
        "is_superuser": True,
        "is_staff": True,
        "can_teach": False,
    },
    {
        "username": "teacher_demo",
        "email": "teacher_demo@almau.local",
        "first_name": "Alikhan",
        "last_name": "Saparov",
        "role": "teacher",
        "is_superuser": False,
        "is_staff": False,
        "can_teach": False,
    },
    {
        "username": "dean_demo",
        "email": "dean_demo@almau.local",
        "first_name": "Bolat",
        "last_name": "Nurtay",
        "role": "dean",
        "is_superuser": False,
        "is_staff": False,
        "can_teach": False,
    },
    {
        "username": "umu_demo",
        "email": "umu_demo@almau.local",
        "first_name": "Dana",
        "last_name": "Bekova",
        "role": "umu",
        "is_superuser": False,
        "is_staff": False,
        "can_teach": False,
    },
]

COURSE_SPECS = [
    {
        "key": "cs101",
        "code": "CS101",
        "owner": "teacher_demo",
        "is_shared": False,
        "title_ru": "Основы программирования",
        "title_kz": "Бағдарламалауға кіріспе",
        "title_en": "Introduction to Programming",
        "description_ru": (
            "Курс формирует базовые навыки алгоритмизации, разработки программ, "
            "работы с типами данных, условиями, циклами, функциями и файлами."
        ),
        "description_kz": (
            "Пән алгоритмдеу, бағдарламалау, дерек түрлері, шарттар, циклдер, "
            "функциялар және файлдармен жұмыс бойынша базалық дағдыларды қалыптастырады."
        ),
        "description_en": (
            "The course covers core programming concepts, including data types, "
            "conditions, loops, functions, and file processing."
        ),
    },
    {
        "key": "it102",
        "code": "IT102",
        "owner": "teacher_demo",
        "is_shared": True,
        "title_ru": "Информационные технологии",
        "title_kz": "Ақпараттық технологиялар",
        "title_en": "Information Technologies",
        "description_ru": (
            "Курс формирует понимание цифровой инфраструктуры, сетей, облачных "
            "сервисов, баз данных и основ кибербезопасности."
        ),
        "description_kz": (
            "Пән цифрлық инфрақұрылым, желілер, бұлтты сервистер, дерекқорлар "
            "және киберқауіпсіздік негіздерін түсіндіреді."
        ),
        "description_en": (
            "The course introduces digital infrastructure, networks, cloud "
            "services, databases, and cybersecurity fundamentals."
        ),
    },
    {
        "key": "math101",
        "code": "MATH101",
        "owner": "teacher_demo",
        "is_shared": False,
        "title_ru": "Высшая математика",
        "title_kz": "Жоғары математика",
        "title_en": "Higher Mathematics",
        "description_ru": (
            "Курс охватывает функции, пределы, производные, интегралы, элементы "
            "линейной алгебры и их применение в прикладных задачах."
        ),
        "description_kz": (
            "Пән функциялар, шектер, туындылар, интегралдар, сызықтық алгебра "
            "элементтері және олардың қолданылуын қамтиды."
        ),
        "description_en": (
            "The course covers functions, limits, derivatives, integrals, and "
            "introductory linear algebra with applied examples."
        ),
    },
]

TOPIC_SPECS = {
    "cs101": [
        "Введение в программирование и алгоритмы",
        "Переменные и типы данных",
        "Арифметические и логические операции",
        "Условные конструкции",
        "Циклы и итерации",
        "Функции и параметры",
        "Область видимости и возврат значений",
        "Списки и кортежи",
        "Словари и множества",
        "Строки и обработка текста",
        "Работа с файлами",
        "Обработка ошибок и исключений",
        "Модули и повторное использование кода",
        "Основы объектно-ориентированного программирования",
        "Мини-проект и итоговое повторение",
    ],
    "it102": [
        "Роль информационных технологий в университете и бизнесе",
        "Аппаратное обеспечение компьютера",
        "Операционные системы и файловые структуры",
        "Офисные приложения и совместная работа",
        "Облачные сервисы и хранение данных",
        "Компьютерные сети и интернет",
        "Веб-технологии и браузеры",
        "Основы баз данных",
        "Цифровые коммуникации и корпоративные платформы",
        "Информационная безопасность",
        "Управление доступом и защита данных",
        "Цифровая этика и академическая добросовестность",
        "Аналитика данных и визуализация",
        "Искусственный интеллект в образовательной среде",
        "Цифровая трансформация организаций",
    ],
    "math101": [
        "Функции и их графики",
        "Предел функции",
        "Непрерывность функции",
        "Производная и правила дифференцирования",
        "Производная сложной функции",
        "Применение производной к исследованию функции",
        "Экстремумы и оптимизация",
        "Неопределенный интеграл",
        "Методы интегрирования",
        "Определенный интеграл",
        "Применение интеграла",
        "Матрицы и операции над ними",
        "Определители",
        "Системы линейных уравнений",
        "Векторы и элементы аналитической геометрии",
    ],
}

SYLLABUS_SPECS = [
    {
        "course_key": "cs101",
        "creator": "teacher_demo",
        "semester": "Fall 2025",
        "academic_year": "2025-2026",
        "status": Syllabus.Status.DRAFT,
        "version_number": 1,
        "is_shared": False,
    },
    {
        "course_key": "cs101",
        "creator": "teacher_demo",
        "semester": "Spring 2026",
        "academic_year": "2025-2026",
        "status": Syllabus.Status.AI_CHECK,
        "version_number": 2,
        "is_shared": False,
    },
    {
        "course_key": "it102",
        "creator": "teacher_demo",
        "semester": "Fall 2025",
        "academic_year": "2025-2026",
        "status": Syllabus.Status.REVIEW_DEAN,
        "version_number": 1,
        "is_shared": False,
    },
    {
        "course_key": "math101",
        "creator": "teacher_demo",
        "semester": "Fall 2025",
        "academic_year": "2025-2026",
        "status": Syllabus.Status.REVIEW_UMU,
        "version_number": 1,
        "is_shared": False,
    },
    {
        "course_key": "cs101",
        "creator": "teacher_demo",
        "semester": "Fall 2026",
        "academic_year": "2026-2027",
        "status": Syllabus.Status.APPROVED,
        "version_number": 3,
        "is_shared": True,
    },
]

SYLLABUS_CONTENT = {
    "cs101": {
        "course_goal": (
            "Сформировать у студентов базовые компетенции в области "
            "программирования и алгоритмического мышления."
        ),
        "learning_outcomes": "\n".join(
            [
                "1. Объяснять базовые принципы алгоритмизации и программирования.",
                "2. Использовать переменные, условия, циклы и функции при решении задач.",
                "3. Работать с основными структурами данных.",
                "4. Создавать простые программы для обработки пользовательского ввода и файлов.",
                "5. Анализировать код, находить и исправлять типовые ошибки.",
            ]
        ),
        "teaching_methods": (
            "Лекции, практические занятия, разбор кода, мини-кейсы, "
            "самостоятельные задания и консультации."
        ),
        "teaching_philosophy": (
            "Обучение строится от простого к сложному с акцентом на практику "
            "и регулярную обратную связь."
        ),
        "course_policy": (
            "Студент обязан регулярно посещать занятия, выполнять практические "
            "задания и соблюдать сроки сдачи работ."
        ),
        "academic_integrity_policy": (
            "Плагиат, списывание и использование чужого кода без ссылки "
            "запрещены и рассматриваются как нарушение академической честности."
        ),
        "inclusive_policy": (
            "Курс поддерживает уважительную и инклюзивную среду. При наличии "
            "индивидуальных образовательных потребностей студент может обратиться "
            "к преподавателю за адаптацией формата работы."
        ),
        "assessment_policy": (
            "Текущий контроль включает практические задания, короткие тесты "
            "и рубежные проверки. Итоговая оценка формируется на основе "
            "накопленных баллов и итогового задания."
        ),
        "grading_scale": "\n".join(
            [
                "Практические задания - 30%",
                "Квизы и короткие тесты - 20%",
                "Рубежный контроль - 20%",
                "Итоговый проект или экзамен - 30%",
            ]
        ),
        "main_literature": "\n".join(
            [
                "1. Python Software Foundation. Python Documentation. 2025.",
                "2. Matthes E. Python Crash Course. 3rd edition. 2023.",
                "3. Nelli F. Python Data Analytics. 3rd edition. 2024.",
            ]
        ),
        "additional_literature": "\n".join(
            [
                "1. Real Python Team. Real Python Tutorials Collection. 2025.",
                "2. Jupyter Project. Jupyter Documentation. 2025.",
            ]
        ),
    },
    "it102": {
        "course_goal": (
            "Сформировать системное представление об информационных технологиях "
            "и навыки безопасного использования цифровых инструментов."
        ),
        "learning_outcomes": "\n".join(
            [
                "1. Различать ключевые компоненты ИТ-инфраструктуры.",
                "2. Использовать базовые цифровые инструменты для учебных задач.",
                "3. Объяснять назначение сетей, облачных сервисов и баз данных.",
                "4. Применять базовые принципы информационной безопасности.",
                "5. Анализировать роль цифровой трансформации организаций.",
            ]
        ),
        "teaching_methods": (
            "Лекции, демонстрации, практические задания, кейс-анализ и работа "
            "с цифровыми сервисами."
        ),
        "teaching_philosophy": (
            "Курс ориентирован на прикладное использование технологий и развитие "
            "цифровой ответственности."
        ),
        "course_policy": (
            "Студент обязан участвовать в практических заданиях, соблюдать "
            "цифровую этику и выполнять задания в установленные сроки."
        ),
        "academic_integrity_policy": (
            "Запрещается выдавать чужие цифровые работы за свои, подделывать "
            "результаты и нарушать правила использования информационных ресурсов."
        ),
        "inclusive_policy": (
            "На занятиях обеспечивается уважительная и безопасная среда для "
            "всех обучающихся вне зависимости от стартового уровня."
        ),
        "assessment_policy": (
            "Оценивание строится на основе практических заданий, тестов, "
            "групповых активностей и итоговой презентации."
        ),
        "grading_scale": "\n".join(
            [
                "Практические задания - 35%",
                "Квизы - 15%",
                "Рубежный контроль - 20%",
                "Итоговая презентация или экзамен - 30%",
            ]
        ),
        "main_literature": "\n".join(
            [
                "1. NIST. Cybersecurity Framework 2.0. 2024.",
                "2. Microsoft Learn. Security, Compliance, and Identity Fundamentals. 2024.",
                "3. PostgreSQL Global Development Group. PostgreSQL Documentation. 2025.",
            ]
        ),
        "additional_literature": "\n".join(
            [
                "1. Cisco Networking Academy Materials. 2025.",
                "2. Google Workspace Learning Center. 2025.",
            ]
        ),
    },
    "math101": {
        "course_goal": (
            "Сформировать фундаментальные знания и навыки применения "
            "математического аппарата в прикладных задачах."
        ),
        "learning_outcomes": "\n".join(
            [
                "1. Вычислять пределы и производные стандартных функций.",
                "2. Применять производную для исследования функций.",
                "3. Вычислять неопределенные и определенные интегралы.",
                "4. Решать базовые задачи линейной алгебры.",
                "5. Использовать математические методы в прикладных задачах.",
            ]
        ),
        "teaching_methods": (
            "Лекции, практические занятия, решение задач, самостоятельная "
            "работа и консультации."
        ),
        "teaching_philosophy": (
            "Курс строится на системности, логической последовательности и "
            "регулярной практике решения задач."
        ),
        "course_policy": (
            "Студент обязан регулярно посещать занятия, решать практические "
            "задания и участвовать в рубежных проверках."
        ),
        "academic_integrity_policy": (
            "Списывание и использование готовых решений без понимания метода "
            "решения считаются нарушением академической честности."
        ),
        "inclusive_policy": (
            "Преподаватель обеспечивает уважительное взаимодействие и "
            "возможность уточнения сложных тем в рамках консультаций."
        ),
        "assessment_policy": (
            "Оценка складывается из домашних заданий, практической активности, "
            "рубежных контролей и итоговой аттестации."
        ),
        "grading_scale": "\n".join(
            [
                "Домашние задания - 20%",
                "Практическая активность - 20%",
                "Рубежный контроль - 30%",
                "Итоговый экзамен - 30%",
            ]
        ),
        "main_literature": "\n".join(
            [
                "1. Open Mathematics Resources for Calculus. 2024.",
                "2. Stewart J. Calculus Updated Course Materials. 2024.",
                "3. Lay D., Lay S., McDonald J. Linear Algebra and Its Applications. 2023.",
            ]
        ),
        "additional_literature": "\n".join(
            [
                "1. Khan Academy Calculus Materials. 2025.",
                "2. MIT OpenCourseWare Mathematics Resources. 2025.",
            ]
        ),
    },
}


class Command(BaseCommand):
    help = "Seed clean demo data for diploma defense."

    def handle(self, *args, **options):
        original_email_backend = settings.EMAIL_BACKEND
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        try:
            users = _ensure_users()
            courses = _ensure_courses(users)
            _ensure_topics(courses)
            syllabi = _ensure_syllabi(courses, users)
            _ensure_ai_checks(syllabi)
            _ensure_announcements(users)
        finally:
            settings.EMAIL_BACKEND = original_email_backend

        self.stdout.write(self.style.SUCCESS("Demo defense data is ready."))
        self.stdout.write(self.style.SUCCESS(f"Demo password for all accounts: {DEMO_PASSWORD}"))


def _ensure_users():
    User = get_user_model()
    users = {}
    for spec in USER_SPECS:
        user = User.objects.filter(username=spec["username"]).first()
        if not user:
            user = User(username=spec["username"])
        user.email = spec["email"]
        user.first_name = spec["first_name"]
        user.last_name = spec["last_name"]
        user.role = spec["role"]
        user.is_active = True
        user.is_superuser = spec["is_superuser"]
        user.is_staff = spec["is_staff"]
        if hasattr(user, "can_teach"):
            user.can_teach = spec["can_teach"]
        if hasattr(user, "email_verified"):
            user.email_verified = True
        user.set_password(DEMO_PASSWORD)
        user.save()
        users[spec["username"]] = user
    return users


def _ensure_courses(users):
    courses = {}
    for spec in COURSE_SPECS:
        owner = users[spec["owner"]]
        course = Course.objects.filter(owner=owner, code=spec["code"]).first()
        if not course:
            course = Course(owner=owner, code=spec["code"])
        course.title_ru = spec["title_ru"]
        course.title_kz = spec["title_kz"]
        course.title_en = spec["title_en"]
        course.description_ru = spec["description_ru"]
        course.description_kz = spec["description_kz"]
        course.description_en = spec["description_en"]
        course.available_languages = "ru,kz,en"
        course.is_shared = spec["is_shared"]
        course.save()
        courses[spec["key"]] = course
    return courses


def _ensure_topics(courses):
    for course_key, titles_ru in TOPIC_SPECS.items():
        course = courses[course_key]
        Topic.objects.filter(course=course, order_index__gt=DEMO_STUDY_WEEKS).delete()
        for index, title_ru in enumerate(titles_ru[:DEMO_STUDY_WEEKS], start=1):
            topic = Topic.objects.filter(course=course, order_index=index).first()
            if not topic:
                topic = Topic(course=course, order_index=index)
            topic.title_ru = title_ru
            topic.title_kz = title_ru
            topic.title_en = title_ru
            topic.description_ru = f"Тема раскрывает содержание раздела: {title_ru}."
            topic.description_kz = f"Тақырып бөлім мазмұнын ашады: {title_ru}."
            topic.description_en = f"The topic covers the section: {title_ru}."
            topic.default_hours = 3
            topic.week_type = Topic.WeekType.PRACTICE if index % 5 == 0 else Topic.WeekType.LECTURE
            topic.is_active = True
            topic.save()
            _ensure_topic_metadata(topic, course)


def _ensure_topic_metadata(topic, course):
    TopicLiterature.objects.get_or_create(
        topic=topic,
        lit_type=TopicLiterature.LitType.MAIN,
        defaults={
            "title": f"{course.title_en} Core Readings",
            "author": "AlmaU Methodology Team",
            "year": "2024",
        },
    )
    TopicLiterature.objects.get_or_create(
        topic=topic,
        lit_type=TopicLiterature.LitType.ADDITIONAL,
        defaults={
            "title": f"Supplementary materials for {topic.title_en}",
            "author": "Various authors",
            "year": "2025",
        },
    )
    TopicQuestion.objects.get_or_create(
        topic=topic,
        question_ru=f"Какие ключевые идеи раскрывает тема «{topic.title_ru}»?",
        defaults={
            "question_kz": f"«{topic.title_kz}» тақырыбы қандай негізгі идеяларды қамтиды?",
            "question_en": f"What key ideas does the topic '{topic.title_en}' cover?",
        },
    )
    TopicQuestion.objects.get_or_create(
        topic=topic,
        question_ru=f"Как тема «{topic.title_ru}» применяется на практике?",
        defaults={
            "question_kz": f"«{topic.title_kz}» тақырыбы практикада қалай қолданылады?",
            "question_en": f"How is the topic '{topic.title_en}' applied in practice?",
        },
    )


def _ensure_syllabi(courses, users):
    syllabi = []
    for spec in SYLLABUS_SPECS:
        course = courses[spec["course_key"]]
        creator = users[spec["creator"]]
        content = SYLLABUS_CONTENT[spec["course_key"]]
        syllabus = Syllabus.objects.filter(
            course=course,
            creator=creator,
            semester=spec["semester"],
            academic_year=spec["academic_year"],
        ).first()
        if not syllabus:
            syllabus = Syllabus(
                course=course,
                creator=creator,
                semester=spec["semester"],
                academic_year=spec["academic_year"],
            )
        syllabus.status = spec["status"]
        syllabus.total_weeks = DEMO_STUDY_WEEKS
        syllabus.main_language = "ru"
        syllabus.is_shared = spec["is_shared"]
        syllabus.version_number = spec["version_number"]
        syllabus.ai_feedback = ""
        syllabus.credits_ects = "6"
        syllabus.total_hours = 180
        syllabus.contact_hours = 45
        syllabus.self_study_hours = 135
        syllabus.prerequisites = "Базовая цифровая грамотность и навыки самостоятельной работы."
        syllabus.delivery_format = "blended"
        syllabus.level = "bachelor"
        syllabus.program_name = "Information Systems"
        syllabus.instructor_name = "Alikhan Saparov"
        syllabus.instructor_contacts = "alikhan.saparov@almau.local"
        syllabus.class_schedule = "Mon 10:00-11:50, Wed 12:00-12:50"
        syllabus.course_description = course.description_ru
        syllabus.course_goal = content["course_goal"]
        syllabus.learning_outcomes = content["learning_outcomes"]
        syllabus.teaching_methods = content["teaching_methods"]
        syllabus.teaching_philosophy = content["teaching_philosophy"]
        syllabus.course_policy = content["course_policy"]
        syllabus.academic_integrity_policy = content["academic_integrity_policy"]
        syllabus.inclusive_policy = content["inclusive_policy"]
        syllabus.assessment_policy = content["assessment_policy"]
        syllabus.grading_scale = content["grading_scale"]
        syllabus.appendix = "Приложения не требуются."
        syllabus.main_literature = content["main_literature"]
        syllabus.additional_literature = content["additional_literature"]
        syllabus.save()
        _sync_syllabus_topics(syllabus)
        _ensure_revision(syllabus, creator)
        syllabi.append(syllabus)
    return syllabi


def _sync_syllabus_topics(syllabus):
    topics = list(syllabus.course.topics.order_by("order_index")[: syllabus.total_weeks or DEMO_STUDY_WEEKS])
    SyllabusTopic.objects.filter(syllabus=syllabus).exclude(topic__in=topics).delete()
    for week_number, topic in enumerate(topics, start=1):
        item, _ = SyllabusTopic.objects.get_or_create(
            syllabus=syllabus,
            topic=topic,
        )
        item.week_number = week_number
        item.is_included = True
        item.custom_title = ""
        item.custom_hours = topic.default_hours
        item.week_label = str(week_number)
        item.tasks = "Домашнее задание, мини-кейс и краткое обсуждение результатов."
        item.learning_outcomes = "Применять знания темы на практике и аргументировать решение."
        item.literature_notes = ""
        item.assessment = "Краткий отчет, решение задачи или мини-презентация."
        item.save()


def _ensure_revision(syllabus, creator):
    if SyllabusRevision.objects.filter(
        syllabus=syllabus,
        version_number=syllabus.version_number,
    ).exists():
        return
    SyllabusRevision.objects.create(
        syllabus=syllabus,
        changed_by=creator,
        note="Demo version for diploma defense.",
        version_number=syllabus.version_number,
    )


def _ensure_ai_checks(syllabi):
    for syllabus in syllabi:
        if syllabus.status not in {
            Syllabus.Status.AI_CHECK,
            Syllabus.Status.REVIEW_DEAN,
            Syllabus.Status.REVIEW_UMU,
            Syllabus.Status.APPROVED,
        }:
            continue
        if AiCheckResult.objects.filter(syllabus=syllabus).exists():
            continue
        summary = (
            "Силлабус соответствует стандартам."
            if syllabus.status in {Syllabus.Status.REVIEW_UMU, Syllabus.Status.APPROVED}
            else "Структура заполнена корректно. Критических замечаний не обнаружено."
        )
        AiCheckResult.objects.create(
            syllabus=syllabus,
            created_at=timezone.now(),
            model_name="rules-only",
            summary=summary,
            raw_result={"demo": True, "status": syllabus.status},
        )


def _ensure_announcements(users):
    announcements = [
        {
            "title": "График согласования силлабусов",
            "body": (
                "Деканат принимает документы на согласование до 15 сентября. "
                "После проверки силлабусы передаются в УМУ для финального согласования."
            ),
            "created_by": users["dean_demo"],
        },
        {
            "title": "Требования к структуре силлабуса",
            "body": (
                "Проверьте заполнение целей, результатов обучения, политики курса, "
                "литературы и распределения тем по всем 12 неделям."
            ),
            "created_by": users["umu_demo"],
        },
    ]
    for item in announcements:
        Announcement.objects.get_or_create(
            title=item["title"],
            defaults=item,
        )
