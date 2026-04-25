from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from syllabi.models import Syllabus
from syllabi.permissions import can_view_syllabus
from workflow.services import queue_for_ai_check

from .models import AiCheckResult


AI_CHECK_START_STATUSES = {
    Syllabus.Status.DRAFT,
    Syllabus.Status.CORRECTION,
    Syllabus.Status.AI_CHECK,
}


def _can_view(user, syllabus: Syllabus) -> bool:
    return can_view_syllabus(user, syllabus)


def _can_request_ai_check(user, syllabus: Syllabus) -> bool:
    is_admin_like = bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_admin_like", False)
        or getattr(user, "role", "") == "admin"
    )
    return user == syllabus.creator or is_admin_like


@login_required
@require_POST
def run_check(request, syllabus_pk):
    syllabus = get_object_or_404(Syllabus, pk=syllabus_pk)
    if not _can_view(request.user, syllabus):
        raise PermissionDenied("Нет доступа к этому силлабусу.")
    if not _can_request_ai_check(request.user, syllabus):
        raise PermissionDenied("Недостаточно прав для запуска AI-проверки.")
    if syllabus.status not in AI_CHECK_START_STATUSES:
        messages.error(
            request,
            "AI-проверку можно запускать только из черновика, доработки или статуса проверки ИИ.",
        )
        return redirect("syllabus_detail", pk=syllabus.pk)

    syllabus, queued_now = queue_for_ai_check(
        request.user,
        syllabus,
        comment="Запрошена AI-проверка из раздела результатов.",
    )
    if queued_now:
        messages.success(request, "Документ поставлен в очередь на AI-проверку.")
    else:
        messages.info(request, "AI-проверка уже выполняется.")
    return redirect("syllabus_detail", pk=syllabus.pk)


@login_required
def check_detail(request, pk):
    check = get_object_or_404(AiCheckResult, pk=pk)
    if not _can_view(request.user, check.syllabus):
        raise PermissionDenied("Нет доступа к результату AI-проверки.")
    return render(request, "ai_checker/check_detail.html", {"check": check})
