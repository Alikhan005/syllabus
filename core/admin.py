from django.contrib import admin

from .models import Announcement, Notification


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "created_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("title", "body")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "syllabus", "title", "created_at", "read_at")
    list_filter = ("created_at", "read_at")
    search_fields = ("title", "body", "recipient__username", "syllabus__course__code")
