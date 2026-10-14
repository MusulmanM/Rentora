from django.conf import settings

from .chat import has_unread_messages


def ai_assistant(request):
    user = request.user
    has_unread_chat_messages = False
    if user.is_authenticated:
        has_unread_chat_messages = has_unread_messages(user)
    return {
        "ai_enabled": bool(getattr(settings, "GEMINI_API_KEY", "")),
        "has_unread_chat_messages": has_unread_chat_messages,
        "chat_max_upload_bytes": settings.CHAT_ATTACHMENT_MAX_BYTES,
        "chat_max_upload_mb": settings.CHAT_ATTACHMENT_MAX_BYTES // (1024 * 1024),
        "admin_url": settings.ADMIN_URL if user.is_authenticated and user.is_superuser else "",
    }
