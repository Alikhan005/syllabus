from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class DiagnosticsAccessTests(TestCase):
    def test_healthz_is_public(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)

    def test_diagnostics_requires_privileged_user(self):
        response = self.client.get(reverse("diagnostics"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_diagnostics(self):
        admin_user = User.objects.create_user(
            username="diag_admin",
            password="pass1234",
            role="admin",
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("diagnostics"))
        self.assertNotEqual(response.status_code, 403)
