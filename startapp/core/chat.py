"""Chat helpers shared by the site chat, the support chat and the helper-admin panel."""
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, F, OuterRef, Q, Subquery, When
from django.urls import reverse
from django.utils import timezone

from .models import ChatMessage, Conversation


def support_conversation_for(user):
    """The user's single chat with the admin team, created on first use."""
    conversation = Conversation.objects.filter(kind=Conversation.Kind.SUPPORT, customer=user).first()
    if conversation:
        return conversation
    try:
        with transaction.atomic():
            return Conversation.objects.create(kind=Conversation.Kind.SUPPORT, customer=user)
    except IntegrityError:  # Created concurrently by another request.
        return Conversation.objects.get(kind=Conversation.Kind.SUPPORT, customer=user)


def conversations_for(user):
    """A user's chats, newest first, annotated with unread counts and the last message."""
    last_message = ChatMessage.objects.filter(conversation=OuterRef("pk")).order_by("-pk")
    return (
        Conversation.objects.filter(Q(customer=user) | Q(provider=user))
        .select_related("listing", "customer", "provider")
        .annotate(
            viewer_last_read=Case(
                When(customer=user, then=F("customer_last_read_message_id")),
                default=F("provider_last_read_message_id"),
            ),
            unread_count=Count(
                "messages",
                filter=Q(messages__pk__gt=Case(
                    When(customer=user, then=F("customer_last_read_message_id")),
                    default=F("provider_last_read_message_id"),
                )) & (Q(messages__sender__isnull=True) | ~Q(messages__sender=user)),
            ),
            last_text=Subquery(last_message.values("text")[:1]),
            last_attachment_type=Subquery(last_message.values("attachment_type")[:1]),
            last_at=Subquery(last_message.values("created_at")[:1]),
        )
        .order_by("-kind", "-updated_at")  # "support" sorts before "listing": the admin chat stays on top.
    )


def unread_messages(user):
    return ChatMessage.objects.filter(
        Q(conversation__customer=user, pk__gt=F("conversation__customer_last_read_message_id"))
        | Q(conversation__provider=user, pk__gt=F("conversation__provider_last_read_message_id")),
    ).filter(Q(sender__isnull=True) | ~Q(sender=user))


def has_unread_messages(user):
    return unread_messages(user).exists()


def mark_read(conversation, user, message_id):
    if not message_id:
        return
    if conversation.customer_id == user.pk:
        field = "customer_last_read_message_id"
    elif conversation.provider_id == user.pk or (conversation.is_support and user.is_staff):
        field = "provider_last_read_message_id"
    else:
        return
    Conversation.objects.filter(pk=conversation.pk, **{f"{field}__lt": message_id}).update(**{field: message_id})
    setattr(conversation, field, max(getattr(conversation, field), message_id))


def post_message(conversation, sender, text="", attachment=None, attachment_type="", is_ai=False):
    message = ChatMessage(
        conversation=conversation, sender=sender, text=text, is_ai=is_ai,
        attachment_type=attachment_type if attachment else "",
    )
    if attachment:
        message.attachment = attachment
    message.full_clean()
    message.save()
    updates = {"updated_at": timezone.now()}
    if conversation.is_support:
        if is_ai:
            pass  # The AI sets the status itself (answered or escalated).
        elif sender is not None and sender.pk == conversation.customer_id:
            updates["support_status"] = Conversation.SupportStatus.WAITING
        else:
            updates["support_status"] = Conversation.SupportStatus.ANSWERED
    Conversation.objects.filter(pk=conversation.pk).update(**updates)
    for field, value in updates.items():
        setattr(conversation, field, value)
    # The sender has obviously read everything up to their own message.
    if sender is not None:
        mark_read(conversation, sender, message.pk)
    return message


def serialize_message(message, viewer, other_last_read):
    mine = message.sender_id == viewer.pk or (
        viewer.is_staff and message.from_support_team and message.conversation.customer_id != viewer.pk
    )
    return {
        "id": message.pk,
        "sender": message.display_sender(viewer),
        "mine": mine,
        "is_ai": message.is_ai,
        "text": message.text,
        "attachment_type": message.attachment_type,
        "attachment_url": reverse("chat-media", args=[message.pk]) if message.attachment else "",
        "created_at": timezone.localtime(message.created_at).strftime("%d.%m.%Y %H:%M"),
        "time": timezone.localtime(message.created_at).strftime("%H:%M"),
        "date": timezone.localtime(message.created_at).strftime("%d.%m.%Y"),
        "read": mine and message.pk <= other_last_read,
    }


def other_side_last_read(conversation, viewer):
    if conversation.is_support and viewer.is_staff and viewer.pk != conversation.customer_id:
        return conversation.customer_last_read_message_id
    return conversation.other_side_last_read(viewer)
