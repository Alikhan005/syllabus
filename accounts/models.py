from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


USERNAME_REGEX = "^[0-9A-Za-z@.+_\\-\u0401\u0451\u0410-\u042F\u0430-\u044F]+\\Z"
username_validator = RegexValidator(
    regex=USERNAME_REGEX,
    message=_(
        "Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters."
    ),
    code="invalid",
)


class User(AbstractUser):
    username = models.CharField(
        _("username"),
        max_length=150,
        unique=True,
        help_text=_("Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."),
        validators=[username_validator],
        error_messages={"unique": _("A user with that username already exists.")},
    )

    class Role(models.TextChoices):
        TEACHER = "teacher", "Преподаватель"
        PROGRAM_LEADER = "program_leader", "Руководитель программы"
        DEAN = "dean", "Деканат"
        UMU = "umu", "УМУ"
        ADMIN = "admin", "Админ"

    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.TEACHER,
    )

    faculty = models.CharField(max_length=255, blank=True)
    department = models.CharField(max_length=255, blank=True)
    can_teach = models.BooleanField(
        _("Can edit/manage syllabus content"),
        default=False,
        help_text=_(
            "Whether this account is allowed to edit syllabus and related course "
            "content as a non-admin/editor role."
        ),
    )
    
    # Поле email_verified удалено, так как подтверждение отключено.

    @property
    def is_admin_like(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_teacher_like(self) -> bool:
        if self.is_admin_like:
            return True
        if self.role in {self.Role.TEACHER, self.Role.PROGRAM_LEADER}:
            return True
        if self.role == self.Role.DEAN:
            return self.can_teach
        return False

    @property
    def can_edit_content(self) -> bool:
        return self.is_teacher_like or self.is_admin_like

    @property
    def can_view_courses(self) -> bool:
        return self.is_teacher_like or self.is_admin_like

    @property
    def can_view_shared_courses(self) -> bool:
        if self.is_teacher_like:
            return True
        return self.role in {self.Role.DEAN, self.Role.UMU} or self.is_admin_like

    @property
    def can_manage_announcements(self) -> bool:
        """
        Determine who is allowed to publish announcements.
        Dean, UMI and admin roles are allowed.
        """
        if self.is_admin_like:
            return True
        return self.role in {self.Role.DEAN, self.Role.UMU}

    @property
    def can_manage_all_announcements(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser

    def can_delete_announcement(self, announcement) -> bool:
        if not self.can_manage_announcements:
            return False
        if self.can_manage_all_announcements:
            return True
        return getattr(announcement, "created_by_id", None) == self.id

    def __str__(self):
        return self.get_full_name() or self.username

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="unique_user_email_ci",
                condition=~Q(email=""),
            ),
        ]
