from django.conf import settings
from django.db import models


class Announcement(models.Model):
    title = models.CharField(max_length=160)
    body = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class NotificationState(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_state",
    )
    last_seen_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"NotificationState<{self.user_id}>"


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    syllabus = models.ForeignKey(
        "syllabi.Syllabus",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    status_log = models.ForeignKey(
        "workflow.SyllabusStatusLog",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    actor_label = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "status_log"],
                name="unique_notification_per_recipient_status_log",
            ),
        ]

    def __str__(self) -> str:
        return f"Notification<{self.recipient_id}:{self.syllabus_id}:{self.status_log_id}>"
