import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import transaction

from core.notifications import create_notifications_for_status_log
from syllabi.display import course_code_for_user, course_title_for_user
from syllabi.models import Syllabus

from .models import SyllabusAuditLog, SyllabusStatusLog

logger = logging.getLogger(__name__)
User = get_user_model()
_ALLOWED_STATUSES = {choice[0] for choice in Syllabus.Status.choices}
_REVIEW_STATUSES = {Syllabus.Status.REVIEW_DEAN, Syllabus.Status.REVIEW_UMU}
_AI_QUEUE_ALLOWED_STATUSES = {
    Syllabus.Status.DRAFT,
    Syllabus.Status.CORRECTION,
    Syllabus.Status.AI_CHECK,
}


def _is_admin_like(user) -> bool:
    return bool(
        user.is_superuser
        or user.is_staff
        or getattr(user, "role", "") == "admin"
        or getattr(user, "is_admin_like", False)
    )


def _reset_ai_claim_fields(syllabus: Syllabus, update_fields: list[str]) -> None:
    if getattr(syllabus, "ai_claimed_at", None) is not None:
        syllabus.ai_claimed_at = None
        update_fields.append("ai_claimed_at")
    if getattr(syllabus, "ai_claimed_by", ""):
        syllabus.ai_claimed_by = ""
        update_fields.append("ai_claimed_by")


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
    """Возвращает человекочитаемое название статуса, если это возможно."""
    try:
        return Syllabus.Status(status).label
    except Exception:
        return status


def _collect_role_emails(role_key: str) -> list[str]:
    """Собирает email активных пользователей по роли, например dean или umu."""
    qs = User.objects.filter(is_active=True, role=role_key).exclude(email="")
    emails = list(qs.values_list("email", flat=True).distinct())

    if not emails:
        logger.warning("No active users with role '%s' were found for notifications.", role_key)

    return emails


def _safe_send_mail(subject: str, message: str, recipients: list[str]) -> None:
    """Отправляет email так, чтобы сбой уведомлений не ломал workflow."""
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
    """Отправляет уведомления по ролям при смене статуса."""
    try:
        subject = ""
        message = ""
        recipients: list[str] = []

        if new_status == Syllabus.Status.REVIEW_DEAN:
            recipients = _collect_role_emails("dean")
            subject = f"Требуется согласование декана: {course_code_for_user(syllabus)}"
            message = (
                "Новый силлабус отправлен на ваше согласование.\n"
                f"Курс: {course_title_for_user(syllabus)}\n"
                f"Автор: {syllabus.creator.get_full_name() or syllabus.creator.username}"
            )

        elif new_status == Syllabus.Status.REVIEW_UMU:
            recipients = _collect_role_emails("umu")
            subject = f"Требуется финальная проверка УМУ: {course_code_for_user(syllabus)}"
            message = (
                "Декан согласовал силлабус. Требуется финальная проверка УМУ.\n"
                f"Курс: {course_title_for_user(syllabus)}"
            )

        elif new_status == Syllabus.Status.APPROVED:
            if syllabus.creator.email:
                recipients = [syllabus.creator.email]
                subject = f"Силлабус утвержден: {course_code_for_user(syllabus, syllabus.creator)}"
                message = f"Ваш силлабус по курсу {course_code_for_user(syllabus, syllabus.creator)} официально утвержден."

        elif new_status == Syllabus.Status.CORRECTION:
            if syllabus.creator.email:
                recipients = [syllabus.creator.email]
                subject = f"Силлабус возвращен на доработку: {course_code_for_user(syllabus, syllabus.creator)}"
                message = (
                    "Ваш силлабус возвращен на доработку.\n\n"
                    f"Комментарий:\n{comment}"
                )

        elif new_status == Syllabus.Status.REJECTED:
            if syllabus.creator.email:
                recipients = [syllabus.creator.email]
                subject = f"Силлабус отклонен: {course_code_for_user(syllabus, syllabus.creator)}"
                message = (
                    "Ваш силлабус отклонен и переведен в архивный статус.\n\n"
                    f"Комментарий:\n{comment or 'Без дополнительного комментария.'}"
                )

        if recipients:
            _safe_send_mail(subject, message, recipients)

    except Exception as exc:
        logger.error("Notification block error: %s", exc)


def change_status(user, syllabus: Syllabus, new_status: str, comment: str = ""):
    """
    Главная функция перехода между статусами.
    1. Проверяет права.
    2. Обновляет статус.
    3. Записывает status/audit логи.
    4. Отправляет уведомления.
    """
    old_status = Syllabus.normalize_status(syllabus.status)
    new_status = Syllabus.normalize_status(str(new_status))
    comment = (comment or "").strip()

    if new_status not in _ALLOWED_STATUSES:
        raise ValueError("Недопустимый целевой статус.")

    # Нормализуем старые значения статусов, которые еще могут быть в БД.
    if syllabus.status != old_status:
        syllabus.status = old_status

    is_admin = _is_admin_like(user)
    user_role = getattr(user, "role", "")
    is_dean = is_admin or user_role == "dean"
    is_umu = is_admin or user_role == "umu"
    is_creator = user == syllabus.creator

    if new_status == old_status:
        return syllabus

    if new_status == Syllabus.Status.REVIEW_DEAN:
        if not (is_creator or is_admin):
            raise PermissionDenied("Только автор может отправить силлабус на согласование декану.")
        if not (syllabus.school or "").strip():
            raise ValueError("Выберите школу перед отправкой декану.")

        allowed_prev = [
            Syllabus.Status.DRAFT,
            Syllabus.Status.CORRECTION,
            Syllabus.Status.AI_CHECK,
            Syllabus.Status.READY_DEAN,
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
        raise PermissionDenied("Ручной переход в этот статус запрещен.")

    with transaction.atomic():
        update_fields = ["status"]
        if new_status != Syllabus.Status.AI_CHECK:
            _reset_ai_claim_fields(syllabus, update_fields)
        syllabus.status = new_status
        syllabus.save(update_fields=update_fields)

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


def queue_for_ai_check(user, syllabus: Syllabus, comment: str = "") -> tuple[Syllabus, bool]:
    """
    Ставит силлабус в очередь AI через workflow-слой.
    Возвращает (syllabus, queued_now), где queued_now=False значит, что он уже был в очереди.
    """
    old_status = Syllabus.normalize_status(syllabus.status)
    comment = (comment or "").strip()

    if syllabus.status != old_status:
        syllabus.status = old_status

    if not (user == syllabus.creator or _is_admin_like(user)):
        raise PermissionDenied("Только автор или администратор может отправить силлабус на AI-проверку.")

    if old_status not in _AI_QUEUE_ALLOWED_STATUSES:
        raise PermissionDenied("Текущий статус не позволяет отправить силлабус на AI-проверку.")

    update_fields: list[str] = []
    if syllabus.ai_feedback:
        syllabus.ai_feedback = ""
        update_fields.append("ai_feedback")
    _reset_ai_claim_fields(syllabus, update_fields)

    if old_status == Syllabus.Status.AI_CHECK:
        if update_fields:
            syllabus.save(update_fields=update_fields)
        return syllabus, False

    with transaction.atomic():
        syllabus.status = Syllabus.Status.AI_CHECK
        syllabus.save(update_fields=["status", *update_fields])

        status_log = SyllabusStatusLog.objects.create(
            syllabus=syllabus,
            from_status=old_status,
            to_status=Syllabus.Status.AI_CHECK,
            changed_by=user,
            comment=comment,
        )

        SyllabusAuditLog.objects.create(
            syllabus=syllabus,
            actor=user,
            action=SyllabusAuditLog.Action.STATUS_CHANGED,
            metadata={"from": old_status, "to": Syllabus.Status.AI_CHECK, "source": "ai_queue"},
            message=comment or "Отправлен в очередь AI-проверки",
        )

    try:
        create_notifications_for_status_log(status_log)
    except Exception as exc:
        logger.error("Notification record error: %s", exc)

    _notify_on_status_change(syllabus, Syllabus.Status.AI_CHECK, comment)
    return syllabus, True


def change_status_system(
    syllabus: Syllabus,
    new_status: str,
    comment: str = "",
    ai_feedback: str | None = None,
) -> Syllabus:
    """
    Внутренний переход статуса для фоновых worker-процессов.
    Обходит проверки ролей, но сохраняет status/audit логи и уведомления консистентными.
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
        if new_status != Syllabus.Status.AI_CHECK:
            _reset_ai_claim_fields(syllabus, update_fields)
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
