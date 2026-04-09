from django.db.models import Count

from catalog.models import Course


DEFAULT_COURSES = [
    {
        "code": "CS101",
        "title_ru": "Основы программирования",
        "available_languages": "ru",
    },
    {
        "code": "IT102",
        "title_ru": "Информационные технологии",
        "available_languages": "ru",
    },
    {
        "code": "MATH101",
        "title_ru": "Высшая математика",
        "available_languages": "ru",
    },
    {
        "code": "STAT201",
        "title_ru": "Статистика",
        "available_languages": "ru",
    },
    {
        "code": "ECON101",
        "title_ru": "Экономика",
        "available_languages": "ru",
    },
    {
        "code": "FIN201",
        "title_ru": "Финансы",
        "available_languages": "ru",
    },
    {
        "code": "MKT201",
        "title_ru": "Маркетинг",
        "available_languages": "ru",
    },
    {
        "code": "MGMT101",
        "title_ru": "Менеджмент",
        "available_languages": "ru",
    },
    {
        "code": "LAW101",
        "title_ru": "Основы права",
        "available_languages": "ru",
    },
    {
        "code": "ENG101",
        "title_ru": "Английский язык (профильный)",
        "available_languages": "ru",
    },
]


def ensure_default_courses(user) -> list[Course]:
    if not user:
        return []
    if Course.objects.filter(owner=user).exists():
        return []

    created = []
    for item in DEFAULT_COURSES:
        created.append(
            Course.objects.create(
                owner=user,
                is_shared=False,
                **item,
            )
        )
    return created


def _normalized_course_code(code: str) -> str:
    return (code or "").strip().casefold()


def dedupe_courses_queryset(queryset):
    annotated = queryset.select_related("owner").annotate(
        topic_count=Count("topics", distinct=True),
        syllabus_count=Count("syllabi", distinct=True),
    ).order_by("owner_id", "code", "-syllabus_count", "-topic_count", "-id")

    canonical_ids = []
    canonical_map = {}
    seen = {}

    for course in annotated:
        key = (course.owner_id, _normalized_course_code(course.code))
        canonical_id = seen.get(key)
        if canonical_id is None:
            canonical_id = course.id
            seen[key] = canonical_id
            canonical_ids.append(course.id)
        canonical_map[course.id] = canonical_id

    deduped_queryset = (
        Course.objects.filter(pk__in=canonical_ids)
        .select_related("owner")
        .order_by("code", "id")
    )
    return deduped_queryset, canonical_map
