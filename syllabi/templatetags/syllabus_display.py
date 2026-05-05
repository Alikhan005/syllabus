from django import template

from syllabi.display import course_code_for_user, course_title_for_user

register = template.Library()


@register.filter
def course_code_for(syllabus, user):
    return course_code_for_user(syllabus, user)


@register.filter
def course_title_for(syllabus, user):
    return course_title_for_user(syllabus, user)
