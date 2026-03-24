from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.forms import PasswordResetIdentifierForm, SignupForm


User = get_user_model()


class AccountFormsTests(TestCase):
    def test_signup_form_exposes_demo_roles(self):
        form = SignupForm()

        allowed_roles = {value for value, _ in form.fields["role"].choices}

        self.assertEqual(
            allowed_roles,
            {
                User.Role.TEACHER,
                User.Role.PROGRAM_LEADER,
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
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )

        self.assertTrue(form.is_valid())


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
