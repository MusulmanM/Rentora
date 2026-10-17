"""Admin chat for visitors who cannot sign in: sign-up problems, blocked accounts, lost passwords.

The visitor gets an inactive "guest" user that owns one support chat. Only the browser session that
created it can read or write that chat, so the chat is as private as a normal account's chat. The
support AI and the helper panel treat it like any other support chat.
"""
import secrets

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .chat import mark_read, other_side_last_read, post_message, serialize_message, support_conversation_for
from .forms import GuestSupportForm
from .models import UserAccount
from .security import rate_limited

SESSION_KEY = "guest_support_user_id"
MAX_MESSAGE = 2000


def _guest_conversation(request):
    user_id = request.session.get(SESSION_KEY)
    if not user_id:
        return None
    guest = get_user_model().objects.filter(pk=user_id, is_active=False, account__is_guest=True).first()
    if guest is None:
        request.session.pop(SESSION_KEY, None)
        return None
    return support_conversation_for(guest)


@rate_limited("guest-support-start", limit=5, window=3600)
def guest_support(request):
    if request.user.is_authenticated:
        return redirect("chat-room", conversation_id=support_conversation_for(request.user).pk)
    conversation = _guest_conversation(request)
    if conversation is None:
        form = GuestSupportForm(request.POST or None, initial={"topic": request.GET.get("topic", "register")})
        if request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            with transaction.atomic():
                guest = get_user_model()(username=f"guest-{secrets.token_hex(6)}", first_name=data["name"], is_active=False)
                guest.set_unusable_password()
                guest.save()
                UserAccount.objects.update_or_create(
                    user=guest, defaults={"is_guest": True, "guest_phone": data["phone_number"]},
                )
                conversation = support_conversation_for(guest)
                topic = dict(GuestSupportForm.TOPICS)[data["topic"]]
                phone = f"\nTelefon: {data['phone_number']}" if data["phone_number"] else ""
                post_message(conversation, guest, text=f"[{topic}] {data['message']}{phone}")
            request.session.cycle_key()
            request.session[SESSION_KEY] = guest.pk
            messages.success(request, "Xabaringiz adminlarga yuborildi. Javob shu sahifada chiqadi.")
            return redirect("guest-support")
        return render(request, "core/guest_support.html", {"form": form})

    guest = conversation.customer
    chat_messages = list(conversation.messages.select_related("sender", "conversation").order_by("-pk")[:200])
    chat_messages.reverse()
    if chat_messages:
        mark_read(conversation, guest, chat_messages[-1].pk)
    other_read = other_side_last_read(conversation, guest)
    return render(request, "core/guest_support.html", {
        "conversation": conversation,
        "chat_messages": [serialize_message(message, guest, other_read) for message in chat_messages],
        "guest_name": guest.first_name,
    })


@rate_limited("guest-support-message", limit=30, window=600)
@require_http_methods(["GET", "POST"])
def guest_support_messages(request):
    conversation = _guest_conversation(request)
    if conversation is None:
        return JsonResponse({"detail": "Chat topilmadi. Sahifani yangilang."}, status=404)
    guest = conversation.customer
    if request.method == "POST":
        text = (request.POST.get("text") or "").strip()
        if not text:
            return JsonResponse({"detail": "Xabarni yozing."}, status=400)
        if len(text) > MAX_MESSAGE:
            return JsonResponse({"detail": f"Xabar {MAX_MESSAGE} belgidan oshmasin."}, status=400)
        message = post_message(conversation, guest, text=text)
        return JsonResponse({"message": serialize_message(message, guest, other_side_last_read(conversation, guest))}, status=201)
    try:
        after = max(0, int(request.GET.get("after", "0")))
    except ValueError:
        return JsonResponse({"detail": "after musbat butun son bo'lishi kerak."}, status=400)
    new = list(conversation.messages.filter(pk__gt=after).select_related("sender", "conversation").order_by("pk")[:100])
    if new:
        mark_read(conversation, guest, new[-1].pk)
    other_read = other_side_last_read(conversation, guest)
    return JsonResponse({
        "messages": [serialize_message(message, guest, other_read) for message in new],
        "other_last_read_id": other_read,
    })
