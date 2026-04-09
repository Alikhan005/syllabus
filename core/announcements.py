import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

from .models import Announcement


logger = logging.getLogger(__name__)
User = get_user_model()


def announcement_author_role_label(user) -> str:
    if not user:
        return "Системное уведомление"

    if getattr(user, "is_superuser", False) or getattr(user, "role", "") == User.Role.ADMIN:
        return "Администратор"

    role_labels = {
        User.Role.DEAN: "Деканат",
        User.Role.UMU: "УМУ",
        User.Role.TEACHER: "Преподаватель",
    }
    return role_labels.get(getattr(user, "role", ""), user.get_role_display())


def announcement_email_recipients() -> list[str]:
    seen: set[str] = set()
    recipients: list[str] = []

    queryset = (
        User.objects.filter(
            is_active=True,
            role__in=[User.Role.TEACHER],
        )
        .exclude(email="")
        .values_list("email", flat=True)
    )

    for email in queryset:
        normalized = (email or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        recipients.append(email.strip())

    return recipients


def _announcement_author_name(announcement: Announcement) -> str:
    if not announcement.created_by:
        return "Система"
    return announcement.created_by.get_full_name() or announcement.created_by.username


def _announcement_author_role_label(announcement: Announcement) -> str:
    return announcement_author_role_label(announcement.created_by)


def _announcement_author_label(announcement: Announcement) -> str:
    role_label = _announcement_author_role_label(announcement)
    author_name = _announcement_author_name(announcement)

    if role_label and author_name:
        return f"{role_label} — {author_name}"
    return author_name or role_label


def _announcement_dashboard_url(request=None) -> str:
    path = reverse("dashboard")
    if request is not None:
        return request.build_absolute_uri(path)

    allowed_hosts = getattr(settings, "ALLOWED_HOSTS", [])
    public_host = next(
        (
            host
            for host in allowed_hosts
            if host and host not in {"*", "localhost", "127.0.0.1", "[::1]"} and "*" not in host
        ),
        "",
    )
    if public_host:
        scheme = "https" if getattr(settings, "SECURE_SSL_REDIRECT", False) else "http"
        return f"{scheme}://{public_host}{path}"
    return ""


def send_announcement_email(announcement: Announcement, request=None) -> int:
    recipients = announcement_email_recipients()
    if not recipients:
        return 0

    context = {
        "announcement": announcement,
        "author": _announcement_author_label(announcement),
        "author_name": _announcement_author_name(announcement),
        "author_role": _announcement_author_role_label(announcement),
        "dashboard_url": _announcement_dashboard_url(request),
    }

    text_body = render_to_string("emails/announcement_email.txt", context).strip()
    html_body = render_to_string("emails/announcement_email.html", context)

    email = EmailMultiAlternatives(
        subject=f"Новое объявление: {announcement.title}",
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"),
        to=[getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")],
        bcc=recipients,
    )
    email.attach_alternative(html_body, "text/html")
    email.send(fail_silently=False)
    logger.info("Announcement email sent to %s recipients", len(recipients))
    return len(recipients)
