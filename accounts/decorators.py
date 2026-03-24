from functools import wraps

from django.core.exceptions import PermissionDenied


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied

            is_admin_like = bool(
                request.user.is_superuser
                or getattr(request.user, "is_admin_like", False)
                or getattr(request.user, "role", "") == "admin"
            )
            if is_admin_like or request.user.role in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped
    return decorator


def content_editor_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied

        is_admin_like = bool(
            request.user.is_superuser
            or getattr(request.user, "is_admin_like", False)
            or getattr(request.user, "role", "") == "admin"
        )
        if is_admin_like or getattr(request.user, "can_edit_content", False):
            return view_func(request, *args, **kwargs)
        raise PermissionDenied

    return _wrapped


def teacher_like_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied

        is_admin_like = bool(
            request.user.is_superuser
            or getattr(request.user, "is_admin_like", False)
            or getattr(request.user, "role", "") == "admin"
        )
        if is_admin_like or getattr(request.user, "is_teacher_like", False):
            return view_func(request, *args, **kwargs)
        raise PermissionDenied

    return _wrapped
