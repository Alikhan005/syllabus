def sidebar_notifications(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {
            "sidebar_notifications": [],
            "sidebar_notifications_count": 0,
        }

    try:
        from core.notifications import build_dashboard_notifications, count_unread_notifications

        notifications = build_dashboard_notifications(request.user, limit=None)
        unread_count = count_unread_notifications(request.user)
    except Exception:
        notifications = []
        unread_count = 0

    return {
        "sidebar_notifications": notifications,
        "sidebar_notifications_count": unread_count,
    }
