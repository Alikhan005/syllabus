PRIVATE_COURSE_CODE = "Личная дисциплина"
PRIVATE_COURSE_TITLE = "Название указано автором вручную"


def can_show_manual_course(user, syllabus) -> bool:
    if not getattr(getattr(syllabus, "course", None), "is_manual", False):
        return True
    return bool(user and getattr(user, "is_authenticated", False) and user == syllabus.creator)


def course_code_for_user(syllabus, user=None) -> str:
    course = getattr(syllabus, "course", None)
    if not course:
        return ""
    if not can_show_manual_course(user, syllabus):
        return PRIVATE_COURSE_CODE
    return course.code


def course_title_for_user(syllabus, user=None) -> str:
    course = getattr(syllabus, "course", None)
    if not course:
        return ""
    if not can_show_manual_course(user, syllabus):
        return PRIVATE_COURSE_TITLE
    return course.display_title or course.code
