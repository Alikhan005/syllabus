from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get("email")
        if not identifier or password is None:
            return None
        if isinstance(identifier, str):
            identifier = identifier.strip()

        user_model = get_user_model()
        user = user_model.objects.filter(email__iexact=identifier).order_by("id").first()
        if not user:
            user = user_model.objects.filter(username__iexact=identifier).order_by("id").first()
        if not user:
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
