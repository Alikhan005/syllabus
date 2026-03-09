import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import transaction

from core.notifications import create_notifications_for_status_log
from syllabi.models import Syllabus

from .models import SyllabusAuditLog, SyllabusStatusLog

logger = logging.getLogger(__name__)
User = get_user_model()
_ALLOWED_STATUSES = {choice[0] for choice in Syllabus.Status.choices}
_REVIEW_STATUSES = {Syllabus.Status.REVIEW_DEAN, Syllabus.Status.REVIEW_UMU}


def _reviewer_label(user) -> str:
    role = getattr(user, "role", "")
    if role == "umu":
        return "УМУ"
    if role == "dean":
        return "Деканат"
    if role == "admin":
        return "Администратор"
    return user.get_full_name() or getattr(user, "username", "") or "Проверяющий"


def _status_label(status: str) -> str:
    """Return a human-readable status label when possible."""
    try:
        return Syllabus.Status(status).label
    except Exception:
        return status


def _collect_role_emails(role_key: str) -> list[str]:
    """Collect active user emails by role key (e.g. dean, umu)."""
    qs = User.objects.filter(is_active=True, role=role_key).exclude(email="")
    emails = list(qs.values_list("email", flat=True))

    if not emails:
        logger.warning("No active users with role '%s' were found for notifications.", role_key)

    return emails


def _safe_send_mail(subject: str, message: str, recipients: list[str]) -> None:
    """Send email without breaking workflow on notification failures."""
    if not recipients:
        return

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@almau.edu.kz")

    try:
        send_mail(
            subject=subject,
            message=message + "\n\n--\nAlmaU Syllabus System",
            from_email=from_email,
            recipient_list=recipients,
            fail_silently=True,
        )
        logger.info("Notification '%s' sent to: %s", subject, recipients)
    except Exception as exc:
        logger.error("Email notification error: %s", exc)


def _notify_on_status_change(syllabus: Syllabus, new_status: str, comment: str = "") -> None:
    """Send role-based notifications for status transitions."""
    try:
        subject = ""
        message = ""
        recipients: list[str] = []

        if new_status == Syllabus.Status.REVIEW_DEAN:
            recipients = _collect_role_emails("dean")
            subject = f"Требуется согласование декана: {syllabus.course.code}"
            message = (
                "Новый силлабус отправлен на ваше согласование.\n"
                f"Курс: {syllabus.course.display_title}\n"
                f"Автор: {syllabus.creator.get_full_name() or syllabus.creator.username}"
            )

        elif new_status == Syllabus.Status.REVIEW_UMU:
            recipients = _collect_role_emails("umu")
            subject = f"Требуется финальная проверка УМУ: {syllabus.course.code}"
            message = (
                "Декан согласовал силлабус. Требуется финальная проверка УМУ.\n"
                f"Курс: {syllabus.course.display_title}"
            )

        elif new_status == Syllabus.Status.APPROVED:
            if syllabus.creator.email:
                recipients = [syllabus.creator.email]
                subject = f"Силлабус утверждён: {syllabus.course.code}"
                message = f"Ваш силлабус по курсу {syllabus.course.code} официально утверждён."

        elif new_status == Syllabus.Status.CORRECTION:
            if syllabus.creator.email:
                recipients = [syllabus.creator.email]
                subject = f"Силлабус возвращён на доработку: {syllabus.course.code}"
                message = (
                    "Ваш силлабус возвращён на доработку.\n\n"
                    f"Комментарий:\n{comment}"
                )

        if recipients:
            _safe_send_mail(subject, message, recipients)

    except Exception as exc:
        logger.error("Notification block error: %s", exc)


def change_status(user, syllabus: Syllabus, new_status: str, comment: str = ""):
    """
    Main status transition function.
    1. Validates permissions.
    2. Updates status.
    3. Writes status/audit logs.
    4. Sends notifications.
    """
    old_status = Syllabus.normalize_status(syllabus.status)
    new_status = Syllabus.normalize_status(str(new_status))
    comment = (comment or "").strip()

    if new_status not in _ALLOWED_STATUSES:
        raise ValueError("Недопустимый целевой статус.")

    # Normalize legacy status values that may still exist in DB.
    if syllabus.status != old_status:
        syllabus.status = old_status

    is_admin = bool(
        user.is_superuser
        or user.is_staff
        or getattr(user, "role", "") == "admin"
        or getattr(user, "is_admin_like", False)
    )
    user_role = getattr(user, "role", "")
    is_dean = is_admin or user_role == "dean"
    is_umu = is_admin or user_role == "umu"
    is_creator = user == syllabus.creator

    if new_status == old_status:
        return syllabus

    if new_status == Syllabus.Status.REVIEW_DEAN:
        if not (is_creator or is_admin):
            raise PermissionDenied("Только автор может отправить силлабус на согласование декану.")

        allowed_prev = [
            Syllabus.Status.DRAFT,
            Syllabus.Status.CORRECTION,
            Syllabus.Status.AI_CHECK,
            Syllabus.Status.REVIEW_DEAN,
        ]
        if old_status not in allowed_prev and not is_admin:
            raise PermissionDenied("Текущий статус не позволяет отправить силлабус декану.")

    elif new_status == Syllabus.Status.REVIEW_UMU:
        if not is_dean:
            raise PermissionDenied("Только декан может передать силлабус в УМУ.")
        if is_creator and not is_admin:
            raise PermissionDenied("Автор не может согласовать собственный силлабус на этапе декана.")
        if old_status != Syllabus.Status.REVIEW_DEAN and not is_admin:
            raise PermissionDenied("Силлабус должен быть в статусе согласования деканом.")

    elif new_status == Syllabus.Status.APPROVED:
        if not is_umu:
            raise PermissionDenied("Только УМУ может финально утвердить силлабус.")
        if is_creator and not is_admin:
            raise PermissionDenied("Автор не может финально утвердить собственный силлабус.")
        if old_status != Syllabus.Status.REVIEW_UMU and not is_admin:
            raise PermissionDenied("Силлабус должен быть в статусе согласования УМУ.")

    elif new_status == Syllabus.Status.CORRECTION:
        if not (is_dean or is_umu):
            raise PermissionDenied("Только декан или УМУ могут вернуть силлабус на доработку.")
        if old_status not in _REVIEW_STATUSES and not is_admin:
            raise PermissionDenied("Силлабус должен быть на согласовании у декана или УМУ.")
        if not comment:
            raise ValueError("При возврате на доработку нужен комментарий.")

    elif new_status == Syllabus.Status.REJECTED:
        if not (is_dean or is_umu):
            raise PermissionDenied("Только декан или УМУ могут отклонить силлабус.")
        if old_status not in _REVIEW_STATUSES and not is_admin:
            raise PermissionDenied("Силлабус должен быть на согласовании у декана или УМУ.")
        if not comment:
            raise ValueError("При отклонении нужен комментарий.")
    else:
        raise PermissionDenied("Ручной переход в этот статус запрещён.")

    with transaction.atomic():
        syllabus.status = new_status
        syllabus.save(update_fields=["status"])

        status_log = SyllabusStatusLog.objects.create(
            syllabus=syllabus,
            from_status=old_status,
            to_status=new_status,
            changed_by=user,
            comment=comment,
        )

        SyllabusAuditLog.objects.create(
            syllabus=syllabus,
            actor=user,
            action=SyllabusAuditLog.Action.STATUS_CHANGED,
            metadata={"from": old_status, "to": new_status},
            message=(
                f"Status changed: {_status_label(old_status)} -> {_status_label(new_status)}"
                if new_status != Syllabus.Status.CORRECTION
                else f"Returned for correction by {_reviewer_label(user)}"
            ),
        )

    try:
        create_notifications_for_status_log(status_log)
    except Exception as exc:
        logger.error("Notification record error: %s", exc)

    _notify_on_status_change(syllabus, new_status, comment)

    return syllabus


def change_status_system(
    syllabus: Syllabus,
    new_status: str,
    comment: str = "",
    ai_feedback: str | None = None,
) -> Syllabus:
    """
    Internal status transition for background workers.
    Bypasses role checks but keeps status/audit logs and notifications consistent.
    """
    old_status = Syllabus.normalize_status(syllabus.status)
    new_status = Syllabus.normalize_status(str(new_status))
    comment = (comment or "").strip()

    if new_status not in _ALLOWED_STATUSES:
        raise ValueError("Недопустимый целевой статус.")

    if syllabus.status != old_status:
        syllabus.status = old_status

    update_fields: list[str] = []
    if ai_feedback is not None:
        syllabus.ai_feedback = ai_feedback
        update_fields.append("ai_feedback")

    if new_status == old_status:
        if update_fields:
            syllabus.save(update_fields=update_fields)
        return syllabus

    with transaction.atomic():
        syllabus.status = new_status
        update_fields = ["status", *update_fields]
        syllabus.save(update_fields=update_fields)

        status_log = SyllabusStatusLog.objects.create(
            syllabus=syllabus,
            from_status=old_status,
            to_status=new_status,
            changed_by=None,
            comment=comment,
        )

        SyllabusAuditLog.objects.create(
            syllabus=syllabus,
            actor=None,
            action=SyllabusAuditLog.Action.STATUS_CHANGED,
            metadata={"from": old_status, "to": new_status, "source": "system"},
            message=(
                comment
                or f"System status changed: {_status_label(old_status)} -> {_status_label(new_status)}"
            ),
        )

    try:
        create_notifications_for_status_log(status_log)
    except Exception as exc:
        logger.error("Notification record error: %s", exc)

    _notify_on_status_change(syllabus, new_status, comment)
    return syllabus
