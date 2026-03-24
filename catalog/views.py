from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import content_editor_required
from .forms import CourseForm, TopicForm, TopicLiteratureFormSet, TopicQuestionFormSet
from .models import Course, Topic, TopicLiterature, TopicQuestion


def _build_fork_code(user, source_code: str) -> str:
    base_code = f"{source_code}_copy"
    candidate = base_code
    suffix = 2

    while Course.objects.filter(owner=user, code=candidate).exists():
        candidate = f"{base_code}_{suffix}"
        suffix += 1

    return candidate


@login_required
@content_editor_required
def courses_list(request):
    courses = Course.objects.filter(owner=request.user)
    return render(request, "catalog/courses_list.html", {"courses": courses})


@login_required
@content_editor_required
def course_create(request):
    if request.method == "POST":
        form = CourseForm(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.owner = request.user
            course.save()
            return redirect("course_detail", pk=course.pk)
    else:
        form = CourseForm()
    return render(request, "catalog/course_form.html", {"form": form})


@login_required
@content_editor_required
def course_edit(request, pk):
    course = get_object_or_404(Course, pk=pk, owner=request.user)
    if request.method == "POST":
        form = CourseForm(request.POST, instance=course)
        if form.is_valid():
            course = form.save(commit=False)
            course.save()
            return redirect("course_detail", pk=course.pk)
    else:
        form = CourseForm(instance=course)
    return render(request, "catalog/course_form.html", {"form": form})


@login_required
def course_detail(request, pk):
    course = get_object_or_404(
        Course.objects.prefetch_related("topics__literature", "topics__questions"),
        pk=pk,
    )
    if not (
        course.owner == request.user
        or course.is_shared
        or getattr(request.user, "is_admin_like", False)
        or getattr(request.user, "role", "") == "umu"
        or getattr(request.user, "is_superuser", False)
    ):
        raise PermissionDenied("Доступ к этому курсу запрещен.")
    topics = course.topics.order_by("order_index")
    return render(request, "catalog/course_detail.html", {"course": course, "topics": topics})


@login_required
@content_editor_required
def topic_create(request, course_pk):
    course = get_object_or_404(Course, pk=course_pk, owner=request.user)
    if request.method == "POST":
        form = TopicForm(request.POST)
        literature_formset = TopicLiteratureFormSet(request.POST, prefix="lit")
        question_formset = TopicQuestionFormSet(request.POST, prefix="q")
    else:
        form = TopicForm()
        literature_formset = TopicLiteratureFormSet(prefix="lit")
        question_formset = TopicQuestionFormSet(prefix="q")
    if request.method == "POST" and all(
        (
            form.is_valid(),
            literature_formset.is_valid(),
            question_formset.is_valid(),
        )
    ):
        topic = form.save(commit=False)
        topic.course = course
        topic.save()

        literature_formset.instance = topic
        literature_formset.save()
        question_formset.instance = topic
        question_formset.save()

        return redirect("course_detail", pk=course.pk)

    return render(
        request,
        "catalog/topic_form.html",
        {
            "course": course,
            "form": form,
            "literature_formset": literature_formset,
            "question_formset": question_formset,
        },
    )


@login_required
@content_editor_required
def topic_edit(request, course_pk, pk):
    course = get_object_or_404(Course, pk=course_pk, owner=request.user)
    topic = get_object_or_404(Topic, pk=pk, course=course)
    if request.method == "POST":
        form = TopicForm(request.POST, instance=topic)
        literature_formset = TopicLiteratureFormSet(request.POST, prefix="lit", instance=topic)
        question_formset = TopicQuestionFormSet(request.POST, prefix="q", instance=topic)
    else:
        form = TopicForm(instance=topic)
        literature_formset = TopicLiteratureFormSet(prefix="lit", instance=topic)
        question_formset = TopicQuestionFormSet(prefix="q", instance=topic)
    if request.method == "POST" and all(
        (
            form.is_valid(),
            literature_formset.is_valid(),
            question_formset.is_valid(),
        )
    ):
        form.save()
        literature_formset.save()
        question_formset.save()
        return redirect("course_detail", pk=course.pk)

    return render(
        request,
        "catalog/topic_form.html",
        {
            "course": course,
            "form": form,
            "literature_formset": literature_formset,
            "question_formset": question_formset,
        },
    )


@login_required
def shared_courses_list(request):
    if not request.user.can_view_shared_courses:
        raise PermissionDenied("У вас нет доступа к общим шаблонам курсов.")

    query = (request.GET.get("q") or "").strip()
    courses = Course.objects.filter(is_shared=True).select_related("owner")

    if query:
        courses = courses.filter(
            Q(code__icontains=query)
            | Q(title_ru__icontains=query)
            | Q(title_kz__icontains=query)
            | Q(title_en__icontains=query)
            | Q(owner__username__icontains=query)
            | Q(owner__first_name__icontains=query)
            | Q(owner__last_name__icontains=query)
        )

    courses = courses.order_by("owner__last_name", "owner__first_name", "code")
    return render(
        request,
        "catalog/shared_courses_list.html",
        {"courses": courses, "search_query": query},
    )


@login_required
@content_editor_required
@transaction.atomic
@require_POST
def course_fork(request, pk):
    if not request.user.can_view_shared_courses:
        raise PermissionDenied("У вас нет доступа к шаблонам курсов.")

    source = get_object_or_404(Course, pk=pk, is_shared=True)

    new_course = Course.objects.create(
        owner=request.user,
        code=_build_fork_code(request.user, source.code),
        title_ru=source.title_ru,
        title_kz=source.title_kz,
        title_en=source.title_en,
        description_ru=source.description_ru,
        description_kz=source.description_kz,
        description_en=source.description_en,
        available_languages=source.available_languages,
        is_shared=False,
    )

    for topic in source.topics.all().order_by("order_index"):
        new_topic = Topic.objects.create(
            course=new_course,
            order_index=topic.order_index,
            title_ru=topic.title_ru,
            title_kz=topic.title_kz,
            title_en=topic.title_en,
            description_ru=topic.description_ru,
            description_kz=topic.description_kz,
            description_en=topic.description_en,
            default_hours=topic.default_hours,
            week_type=topic.week_type,
            is_active=topic.is_active,
        )

        for lit in topic.literature.all():
            TopicLiterature.objects.create(
                topic=new_topic,
                title=lit.title,
                author=lit.author,
                year=lit.year,
                lit_type=lit.lit_type,
            )

        for q in topic.questions.all():
            TopicQuestion.objects.create(
                topic=new_topic,
                question_ru=q.question_ru,
                question_kz=q.question_kz,
                question_en=q.question_en,
            )

    source_title = source.display_title or source.code
    messages.success(
        request,
        f'Шаблон "{source_title}" скопирован в раздел "Мои курсы". Сейчас открыта ваша личная копия.',
    )
    return redirect("course_detail", pk=new_course.pk)
