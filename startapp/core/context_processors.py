from django.conf import settings
from django.db.models import F, Q

from .models import ChatMessage


def ai_assistant(request):
    user = request.user
    has_unread_chat_messages = False
    if user.is_authenticated:
        has_unread_chat_messages = ChatMessage.objects.filter(
            Q(
                conversation__customer=user,
                pk__gt=F("conversation__customer_last_read_message_id"),
            )
            | Q(
                conversation__provider=user,
                pk__gt=F("conversation__provider_last_read_message_id"),
            ),
        ).exclude(sender=user).exists()
    return {
        "ai_enabled": bool(getattr(settings, "OPENAI_API_KEY", "")),
        "has_unread_chat_messages": has_unread_chat_messages,
    }
