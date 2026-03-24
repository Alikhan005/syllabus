from .models import Syllabus


def shared_syllabi_queryset(user):
    qs = Syllabus.objects.filter(
        is_shared=True,
        status=Syllabus.Status.APPROVED,
    ).select_related("course", "creator")
    if getattr(user, "is_superuser", False):
        return qs
    if getattr(user, "is_admin_like", False):
        return qs
    if not getattr(user, "can_view_shared_courses", False):
        return qs.none()
    return qs


def can_view_syllabus(user, syllabus: Syllabus) -> bool:
    if user == syllabus.creator:
        return True
    if user.is_superuser or getattr(user, "is_admin_like", False):
        return True
    if (
        syllabus.is_shared
        and syllabus.status == Syllabus.Status.APPROVED
        and getattr(user, "can_view_shared_courses", False)
    ):
        return True
    if user.role in ["dean", "umu", "admin"]:
        return True
    return False
