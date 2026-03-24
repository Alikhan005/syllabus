from django.contrib.auth import get_user_model
from django.utils import timezone

from core.models import Notification, NotificationState
from syllabi.models import Syllabus

User = get_user_model()


def notification_actor_label(status_log) -> str:
    if status_log.changed_by is None:
        if status_log.from_status == Syllabus.Status.AI_CHECK:
            return "ИИ"
        return "Система"

    actor_role = getattr(status_log.changed_by, "role", "")
    if actor_role == "umu":
        return "УМУ"
    if actor_role == "dean":
        return "Деканат"
    if actor_role == "admin":
        return "Администратор"
    return status_log.changed_by.get_full_name() or status_log.changed_by.username


def notification_title(status_log) -> str:
    course_code = getattr(status_log.syllabus.course, "code", f"ID {status_log.syllabus_id}")

    if status_log.to_status == Syllabus.Status.REVIEW_DEAN:
        status_text = "Отправлен на согласование декану"
    elif status_log.to_status == Syllabus.Status.REVIEW_UMU:
        status_text = "Отправлен на согласование в УМУ"
    elif status_log.to_status == Syllabus.Status.CORRECTION:
        status_text = "Возвращен на доработку"
    elif status_log.to_status == Syllabus.Status.APPROVED:
        status_text = "Силлабус утвержден"
    elif status_log.to_status == Syllabus.Status.REJECTED:
        status_text = "Силлабус отклонен"
    elif status_log.to_status == Syllabus.Status.AI_CHECK:
        status_text = "Отправлен на AI-проверку"
    else:
        status_text = "Статус обновлен"

    return f"{course_code}: {status_text}"


def notification_body(status_log) -> str:
    comment = (status_log.comment or "").strip()
    if comment:
        return comment

    return f"Статус изменен: {status_log.from_status_label} -> {status_log.to_status_label}"


def notification_recipients(status_log) -> list:
    syllabus = status_log.syllabus
    recipients_by_id = {}
    excluded_ids = {status_log.changed_by_id}

    if status_log.to_status == Syllabus.Status.REVIEW_DEAN:
        excluded_ids.add(syllabus.creator_id)
        for user in User.objects.filter(is_active=True, role="dean"):
            if user.pk not in excluded_ids:
                recipients_by_id[user.pk] = user

    elif status_log.to_status == Syllabus.Status.REVIEW_UMU:
        excluded_ids.add(syllabus.creator_id)
        for user in User.objects.filter(is_active=True, role="umu"):
            if user.pk not in excluded_ids:
                recipients_by_id[user.pk] = user

    elif status_log.to_status in [
        Syllabus.Status.CORRECTION,
        Syllabus.Status.APPROVED,
        Syllabus.Status.REJECTED,
    ]:
        creator = syllabus.creator
        if creator and creator.is_active and creator.pk not in excluded_ids:
            recipients_by_id[creator.pk] = creator

    return list(recipients_by_id.values())


def create_notifications_for_status_log(status_log) -> int:
    recipients = notification_recipients(status_log)
    if not recipients:
        return 0

    notifications = [
        Notification(
            recipient=user,
            syllabus=status_log.syllabus,
            status_log=status_log,
            title=notification_title(status_log),
            body=notification_body(status_log),
            actor_label=notification_actor_label(status_log),
            created_at=status_log.changed_at,
        )
        for user in recipients
    ]
    Notification.objects.bulk_create(notifications, ignore_conflicts=True)
    return len(notifications)


def notifications_queryset(user):
    if not getattr(user, "is_authenticated", False):
        return Notification.objects.none()
    return Notification.objects.filter(recipient=user).select_related(
        "syllabus__course",
        "syllabus__creator",
        "status_log",
    )


def build_dashboard_notifications(user, limit: int | None = 6) -> list[dict]:
    queryset = notifications_queryset(user).order_by("-created_at")
    notifications = queryset[:limit] if limit is not None else queryset
    return [_serialize_notification(item) for item in notifications]


def _serialize_notification(item):
    creator = item.syllabus.creator
    return {
        "syllabus_id": item.syllabus_id,
        "title": item.title,
        "body": item.body,
        "actor_label": item.actor_label,
        "creator_name": (creator.get_full_name() or creator.username) if creator else "",
        "changed_at": item.created_at,
        "is_unread": item.read_at is None,
    }


def count_unread_notifications(user) -> int:
    return notifications_queryset(user).filter(read_at__isnull=True).count()


def latest_notification_changed_at(user):
    return (
        notifications_queryset(user)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )


def mark_notifications_read(user) -> int:
    if not getattr(user, "is_authenticated", False):
        return 0

    now = timezone.now()
    updated = notifications_queryset(user).filter(read_at__isnull=True).update(read_at=now)
    NotificationState.objects.update_or_create(
        user=user,
        defaults={"last_seen_at": now},
    )
    return updated
