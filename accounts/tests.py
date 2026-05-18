from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.forms import (
    DEAN_SCHOOL_CHOICES,
    PasswordResetIdentifierForm,
    ProfileForm,
    SignupForm,
)


User = get_user_model()


class AccountFormsTests(TestCase):
    def test_signup_form_exposes_demo_roles(self):
        form = SignupForm()

        allowed_roles = {value for value, _ in form.fields["role"].choices}

        self.assertEqual(
            allowed_roles,
            {
                User.Role.TEACHER,
                User.Role.DEAN,
                User.Role.UMU,
            },
        )

    def test_password_reset_accepts_username_identifier(self):
        user = User.objects.create_user(
            username="reset_user",
            password="pass1234",
            email="reset_user@example.com",
            role="teacher",
            is_active=True,
        )

        form = PasswordResetIdentifierForm(data={"email": user.username})
        self.assertTrue(form.is_valid())

        matched_users = list(form.get_users(form.cleaned_data["email"]))
        self.assertEqual(len(matched_users), 1)
        self.assertEqual(matched_users[0].pk, user.pk)

    def test_password_reset_accepts_email_identifier(self):
        user = User.objects.create_user(
            username="reset_by_email",
            password="pass1234",
            email="reset_by_email@example.com",
            role="teacher",
            is_active=True,
        )

        form = PasswordResetIdentifierForm(data={"email": "RESET_BY_EMAIL@example.com"})
        self.assertTrue(form.is_valid())

        matched_users = list(form.get_users(form.cleaned_data["email"]))
        self.assertEqual(len(matched_users), 1)
        self.assertEqual(matched_users[0].pk, user.pk)

    def test_password_reset_rejects_unknown_identifier(self):
        form = PasswordResetIdentifierForm(data={"email": "missing@example.com"})

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_password_reset_rejects_user_without_email(self):
        User.objects.create_user(
            username="reset_without_email",
            password="pass1234",
            email="",
            role="teacher",
            is_active=True,
        )

        form = PasswordResetIdentifierForm(data={"email": "reset_without_email"})

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_signup_form_does_not_reference_removed_email_verified(self):
        User.objects.create_user(
            username="existing_user",
            password="pass1234",
            email="existing@example.com",
            role="teacher",
            is_active=True,
        )

        form = SignupForm(
            data={
                "username": "existing_user",
                "first_name": "A",
                "last_name": "B",
                "email": "new@example.com",
                "role": "teacher",
                "faculty": "",
                "department": "",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)

    def test_signup_form_accepts_reviewer_role_for_demo(self):
        form = SignupForm(
            data={
                "username": "reviewer_attempt",
                "first_name": "Dean",
                "last_name": "Attempt",
                "email": "reviewer_attempt@example.com",
                "role": User.Role.DEAN,
                "faculty": "",
                "department": "",
                "dean_school": DEAN_SCHOOL_CHOICES[0][0],
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )

        self.assertTrue(form.is_valid())

    def test_dean_signup_requires_school_management(self):
        form = SignupForm(
            data={
                "username": "dean_without_school",
                "first_name": "Dean",
                "last_name": "NoSchool",
                "email": "dean_without_school@example.com",
                "role": User.Role.DEAN,
                "faculty": "",
                "department": "",
                "dean_school": "",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("dean_school", form.errors)

    def test_dean_signup_saves_selected_school_in_faculty_field(self):
        school_name = DEAN_SCHOOL_CHOICES[1][0]
        form = SignupForm(
            data={
                "username": "dean_with_school",
                "first_name": "Dean",
                "last_name": "School",
                "email": "dean_with_school@example.com",
                "role": User.Role.DEAN,
                "faculty": "Будет заменено",
                "department": "Будет очищено",
                "dean_school": school_name,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertEqual(user.faculty, school_name)
        self.assertEqual(user.department, "")

    def test_teacher_signup_does_not_require_dean_school(self):
        form = SignupForm(
            data={
                "username": "teacher_without_dean_school",
                "first_name": "Teacher",
                "last_name": "Regular",
                "email": "teacher_without_dean_school@example.com",
                "role": User.Role.TEACHER,
                "faculty": "Факультет",
                "department": "Кафедра",
                "dean_school": "",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_dean_profile_uses_school_management_without_department(self):
        dean = User.objects.create_user(
            username="profile_dean",
            password="pass1234",
            email="profile_dean@example.com",
            role=User.Role.DEAN,
            faculty=DEAN_SCHOOL_CHOICES[0][0],
            department="Лишняя кафедра",
        )

        form = ProfileForm(instance=dean)

        self.assertEqual(form.fields["faculty"].label, "Управление школы")
        self.assertNotIn("department", form.fields)

    def test_dean_profile_page_hides_department(self):
        dean = User.objects.create_user(
            username="profile_dean_page",
            password="pass1234",
            email="profile_dean_page@example.com",
            role=User.Role.DEAN,
            faculty=DEAN_SCHOOL_CHOICES[0][0],
            department="Лишняя кафедра",
        )
        self.client.force_login(dean)

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Управление школы")
        self.assertNotContains(response, "Кафедра")
        self.assertContains(response, "управление школы")

    def test_dean_profile_save_clears_department(self):
        dean = User.objects.create_user(
            username="profile_dean_save",
            password="pass1234",
            email="profile_dean_save@example.com",
            role=User.Role.DEAN,
            faculty=DEAN_SCHOOL_CHOICES[0][0],
            department="Лишняя кафедра",
        )
        form = ProfileForm(
            data={
                "first_name": "Dean",
                "last_name": "Profile",
                "email": dean.email,
                "faculty": DEAN_SCHOOL_CHOICES[1][0],
            },
            instance=dean,
        )

        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()

        self.assertEqual(user.faculty, DEAN_SCHOOL_CHOICES[1][0])
        self.assertEqual(user.department, "")


class LogoutSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="logout_user",
            password="pass1234",
            role="teacher",
            is_active=True,
        )

    def test_logout_rejects_get_requests(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("logout"))

        self.assertEqual(response.status_code, 405)
        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard_response.status_code, 200)

    def test_logout_works_via_post(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("logout"))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("home"))
        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard_response.status_code, 302)


class PasswordResetRouteTests(TestCase):
    def test_password_reset_confirm_route_is_standard(self):
        url = reverse(
            "password_reset_confirm",
            kwargs={"uidb64": "abc123", "token": "set-password"},
        )

        self.assertEqual(url, "/accounts/reset/abc123/set-password/")
