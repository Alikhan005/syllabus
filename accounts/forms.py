from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, UserCreationForm
from django.core.exceptions import ValidationError

from .schools import SCHOOL_CHOICES

User = get_user_model()

DEAN_SCHOOL_CHOICES = SCHOOL_CHOICES


class SignupForm(UserCreationForm):
    dean_school = forms.ChoiceField(
        label="Управление школы",
        required=False,
        choices=(("", "Выберите школу"),) + DEAN_SCHOOL_CHOICES,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.existing_user = None
        allowed_role_values = {
            User.Role.TEACHER,
            User.Role.DEAN,
            User.Role.UMU,
        }
        allowed_roles = [choice for choice in User.Role.choices if choice[0] in allowed_role_values]
        self.fields["role"].choices = allowed_roles
        self.fields["role"].help_text = (
            "Выберите роль для демонстрации сценария системы. "
            "При необходимости администратор сможет изменить ее позже."
        )
        self.fields["email"].required = True

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "faculty",
            "department",
            "password1",
            "password2",
        )
        labels = {
            "first_name": "Имя",
            "last_name": "Фамилия",
            "role": "Роль в системе",
            "faculty": "Факультет",
            "department": "Кафедра",
        }
        help_texts = {
            "role": "Выберите свою роль. При необходимости администратор сможет изменить ее позже.",
        }

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get("role")
        dean_school = (cleaned_data.get("dean_school") or "").strip()

        if role == User.Role.DEAN and not dean_school:
            self.add_error("dean_school", "Выберите управление школы для деканата.")

        return cleaned_data

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            return username

        existing = User.objects.filter(username__iexact=username).first()
        if existing:
            if existing.is_active:
                raise ValidationError("Пользователь с таким именем уже существует.")
            if self.existing_user and self.existing_user.pk != existing.pk:
                raise ValidationError(
                    "Имя пользователя и email уже заняты разными аккаунтами. Проверьте данные."
                )
            self.existing_user = existing
            self.instance = existing
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if not email:
            raise ValidationError("Введите email.")

        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            if existing.is_active:
                raise ValidationError("Пользователь с таким email уже существует.")
            if self.existing_user and self.existing_user.pk != existing.pk:
                raise ValidationError(
                    "Имя пользователя и email уже заняты разными аккаунтами. Проверьте данные."
                )
            self.existing_user = existing
            self.instance = existing
        return email

    def save(self, commit=True):
        user = super().save(commit=False)

        if self.cleaned_data.get("role") == User.Role.DEAN:
            user.faculty = self.cleaned_data.get("dean_school", "")
            user.department = ""

        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields["username"].label = "Имя пользователя или email"
        self.fields["username"].widget.attrs["placeholder"] = "логин или email"
        self.error_messages["invalid_login"] = "Введите корректный логин/email и пароль."

    def clean(self):
        username_or_email = (self.cleaned_data.get("username") or "").strip()
        password = self.cleaned_data.get("password")

        lookup_username = username_or_email
        if username_or_email and "@" in username_or_email:
            user = User.objects.filter(email__iexact=username_or_email).first()
            if user:
                lookup_username = user.username

        self.cleaned_data["username"] = lookup_username
        user = authenticate(self.request, username=lookup_username, password=password)
        if user is None:
            raise ValidationError(
                self.error_messages["invalid_login"],
                code="invalid_login",
                params={"username": self.username_field.verbose_name},
            )

        self.confirm_login_allowed(user)
        self.user_cache = user
        return self.cleaned_data

    def confirm_login_allowed(self, user):
        if not user.is_active:
            raise ValidationError(
                "Аккаунт не активирован. Подтвердите email или обратитесь к администратору."
            )


class PasswordResetIdentifierForm(PasswordResetForm):
    not_found_error = (
        "Аккаунт с таким email или логином не найден. "
        "Проверьте данные или обратитесь к администратору."
    )

    email = forms.CharField(
        label="Email или логин",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "placeholder": "Email или логин",
            }
        ),
    )

    def clean_email(self):
        identifier = (self.cleaned_data.get("email") or "").strip()
        if not identifier:
            raise ValidationError("Введите email или логин.")

        if "@" in identifier:
            user = (
                User.objects.filter(email__iexact=identifier, is_active=True)
                .exclude(email="")
                .first()
            )
        else:
            user = (
                User.objects.filter(username__iexact=identifier, is_active=True)
                .exclude(email="")
                .first()
            )

        if not user or not user.has_usable_password():
            raise ValidationError(self.not_found_error)
        return user.email


class ProfileForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if getattr(self.instance, "role", "") == User.Role.DEAN:
            self.fields["faculty"] = forms.ChoiceField(
                label="Управление школы",
                choices=(("", "Выберите школу"),) + DEAN_SCHOOL_CHOICES,
                initial=self.instance.faculty,
            )
            self.fields.pop("department", None)

    def save(self, commit=True):
        user = super().save(commit=False)

        if getattr(user, "role", "") == User.Role.DEAN:
            user.department = ""

        if commit:
            user.save()
        return user

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "faculty", "department")
        labels = {
            "first_name": "Имя",
            "last_name": "Фамилия",
            "email": "Email",
            "faculty": "Факультет",
            "department": "Кафедра",
        }
