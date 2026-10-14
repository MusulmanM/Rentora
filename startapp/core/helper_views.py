"""Helper-admin panel for staff: support inbox, user chats, bookings, users and products."""
import json
from datetime import date
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Max, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .admin_ai import AdminAssistantError, ask_admin_assistant
from .chat import mark_read, other_side_last_read, serialize_message
from .forms import ChatMessageForm, HelperUserCreateForm
from .models import (
    Booking, BookingOrder, ChatMessage, ContactMessage, Conversation, HostProfile, RentalListing,
)
from .security import rate_limited
from .telegram import notify_booking_parties

User = get_user_model()
PAGE_SIZE = 30


def staff_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not (request.user.is_active and request.user.is_staff):
            raise Http404
        return view(request, *args, **kwargs)

    return wrapped


def superuser_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, "Bu amalni faqat bosh admin bajara oladi.")
            return redirect("helper-users")
        return view(request, *args, **kwargs)

    return staff_required(wrapped)


def _page(request, queryset):
    return Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))


def _support_queryset():
    return (
        Conversation.objects.filter(kind=Conversation.Kind.SUPPORT)
        .select_related("customer", "customer__account")
        .annotate(
            message_total=Count("messages"),
            last_message_id=Max("messages__id"),
            unread_count=Count(
                "messages",
                filter=Q(messages__pk__gt=F("provider_last_read_message_id"), messages__sender=F("customer")),
            ),
        )
        .filter(message_total__gt=0)
    )


@staff_required
def dashboard(request):
    today = timezone.localdate()
    support = _support_queryset()
    stats = {
        "users": User.objects.count(),
        "providers": HostProfile.objects.count(),
        "listings": RentalListing.objects.count(),
        "homes": RentalListing.objects.filter(kind=RentalListing.Kind.HOME).count(),
        "cars": RentalListing.objects.filter(kind=RentalListing.Kind.CAR).count(),
        "bookings_today": Booking.objects.filter(created_at__date=today).count(),
        "bookings_active": Booking.objects.filter(
            status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.HANDED_OVER],
            check_out__gt=today,
        ).count(),
        "bookings_pending": Booking.objects.filter(status=Booking.Status.PENDING).count(),
        "support_waiting": support.filter(
            support_status__in=[Conversation.SupportStatus.WAITING, Conversation.SupportStatus.ESCALATED],
        ).count(),
        "contacts_unread": ContactMessage.objects.filter(is_read=False).count(),
    }
    return render(request, "core/helper/dashboard.html", {
        "stats": stats,
        "waiting_threads": support.filter(
            support_status__in=[Conversation.SupportStatus.WAITING, Conversation.SupportStatus.ESCALATED],
        ).order_by("-updated_at")[:8],
        "recent_bookings": Booking.objects.select_related("listing", "user").order_by("-created_at")[:8],
        "section": "dashboard",
    })


@staff_required
def support_list(request):
    threads = _support_queryset()
    status = request.GET.get("status", "open")
    query = request.GET.get("q", "").strip()[:100]
    if status == "open":
        threads = threads.filter(
            support_status__in=[Conversation.SupportStatus.WAITING, Conversation.SupportStatus.ESCALATED],
        )
    elif status in Conversation.SupportStatus.values:
        threads = threads.filter(support_status=status)
    if query:
        threads = threads.filter(
            Q(customer__username__icontains=query) | Q(customer__first_name__icontains=query)
            | Q(customer__last_name__icontains=query) | Q(customer__email__icontains=query)
            | Q(customer__profile__phone_number__icontains=query) | Q(messages__text__icontains=query)
        ).distinct()
    return render(request, "core/helper/support_list.html", {
        "page": _page(request, threads.order_by("-updated_at")),
        "status": status, "query": query,
        "status_choices": Conversation.SupportStatus.choices,
        "ai_delay_minutes": max(1, settings.SUPPORT_AI_DELAY_SECONDS // 60),
        "section": "support",
    })


@staff_required
def support_thread(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.select_related("customer", "customer__account"),
        pk=conversation_id, kind=Conversation.Kind.SUPPORT,
    )
    chat_messages = list(conversation.messages.select_related("sender", "conversation").order_by("-pk")[:200])
    chat_messages.reverse()
    latest = chat_messages[-1].pk if chat_messages else 0
    mark_read(conversation, request.user, latest)
    other_read = other_side_last_read(conversation, request.user)
    customer = conversation.customer
    return render(request, "core/helper/support_thread.html", {
        "conversation": conversation,
        "chat_messages": [serialize_message(message, request.user, other_read) for message in chat_messages],
        "latest_chat_message_id": latest,
        "customer": customer,
        "customer_bookings": Booking.objects.filter(user=customer).select_related("listing").order_by("-created_at")[:5],
        "reply_form": ChatMessageForm(),
        "section": "support",
    })


@staff_required
def chats_list(request):
    query = request.GET.get("q", "").strip()[:100]
    conversations = (
        Conversation.objects.filter(kind=Conversation.Kind.LISTING)
        .select_related("listing", "customer", "provider")
        .annotate(message_total=Count("messages"))
        .order_by("-updated_at")
    )
    if query:
        conversations = conversations.filter(
            Q(listing__title__icontains=query) | Q(customer__username__icontains=query)
            | Q(provider__username__icontains=query) | Q(customer__first_name__icontains=query)
            | Q(provider__first_name__icontains=query)
        )
    return render(request, "core/helper/chats_list.html", {
        "page": _page(request, conversations), "query": query, "section": "chats",
    })


@staff_required
def chat_view(request, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.select_related("listing", "customer", "provider"),
        pk=conversation_id, kind=Conversation.Kind.LISTING,
    )
    chat_messages = list(conversation.messages.select_related("sender", "conversation").order_by("-pk")[:300])
    chat_messages.reverse()
    # Admins only observe here: nothing is marked as read for the participants.
    return render(request, "core/helper/chat_view.html", {
        "conversation": conversation,
        "chat_messages": [serialize_message(message, request.user, 0) for message in chat_messages],
        "section": "chats",
    })


@staff_required
def bookings(request):
    bookings_qs = Booking.objects.select_related("listing", "user", "listing__owner").order_by("-created_at")
    filters = {key: request.GET.get(key, "").strip()[:100] for key in ("q", "status", "kind", "payment", "date_from", "date_to")}
    if filters["q"]:
        query = filters["q"]
        condition = (
            Q(listing__title__icontains=query) | Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query) | Q(listing__owner__username__icontains=query)
        )
        if query.lstrip("#").isdigit():
            condition |= Q(pk=int(query.lstrip("#")))
        bookings_qs = bookings_qs.filter(condition)
    if filters["status"] in Booking.Status.values:
        bookings_qs = bookings_qs.filter(status=filters["status"])
    if filters["kind"] in RentalListing.Kind.values:
        bookings_qs = bookings_qs.filter(listing__kind=filters["kind"])
    if filters["payment"] in Booking.PaymentMethod.values:
        bookings_qs = bookings_qs.filter(payment_method=filters["payment"])
    for key, lookup in (("date_from", "check_in__gte"), ("date_to", "check_in__lte")):
        try:
            bookings_qs = bookings_qs.filter(**{lookup: date.fromisoformat(filters[key])})
        except ValueError:
            filters[key] = ""
    orders = BookingOrder.objects.filter(
        status__in=[BookingOrder.Status.PENDING, BookingOrder.Status.AWAITING_PAYMENT],
    ).select_related("listing", "user").order_by("-created_at")[:20]
    return render(request, "core/helper/bookings.html", {
        "page": _page(request, bookings_qs), "filters": filters, "orders": orders,
        "status_choices": Booking.Status.choices, "payment_choices": Booking.PaymentMethod.choices,
        "kind_choices": RentalListing.Kind.choices, "section": "bookings",
    })


@staff_required
@require_POST
def booking_cancel(request, booking_id):
    with transaction.atomic():
        booking = get_object_or_404(Booking.objects.select_for_update(), pk=booking_id)
        if booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
            messages.error(request, "Bu bronni bekor qilib bo'lmaydi.")
            return redirect("helper-bookings")
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status", "updated_at"])
        transaction.on_commit(lambda: notify_booking_parties(booking.pk, "cancelled"))
    messages.success(request, f"#{booking.pk} bron bekor qilindi.")
    return redirect(request.POST.get("next") if str(request.POST.get("next", "")).startswith("/helper/") else "helper-bookings")


@staff_required
def users(request):
    users_qs = User.objects.select_related("account", "profile", "host_profile").annotate(
        booking_total=Count("bookings", distinct=True), listing_total=Count("owned_listings", distinct=True),
    ).order_by("-date_joined")
    query = request.GET.get("q", "").strip()[:100]
    role = request.GET.get("role", "")
    if query:
        condition = (
            Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query)
            | Q(email__icontains=query) | Q(profile__phone_number__icontains=query)
            | Q(account__uid__icontains=query.replace("-", ""))
        )
        if query.isdigit():
            condition |= Q(pk=int(query))
        users_qs = users_qs.filter(condition)
    role_filters = {
        "provider": Q(host_profile__isnull=False),
        "staff": Q(is_staff=True),
        "verified": Q(profile__isnull=False),
        "unverified": Q(profile__isnull=True),
        "inactive": Q(is_active=False),
    }
    if role in role_filters:
        users_qs = users_qs.filter(role_filters[role])
    return render(request, "core/helper/users.html", {
        "page": _page(request, users_qs), "query": query, "role": role, "section": "users",
    })


@staff_required
def user_detail(request, user_id):
    member = get_object_or_404(User.objects.select_related("account", "profile", "host_profile"), pk=user_id)
    return render(request, "core/helper/user_detail.html", {
        "member": member,
        "member_bookings": Booking.objects.filter(user=member).select_related("listing").order_by("-created_at")[:20],
        "member_listings": RentalListing.objects.filter(owner=member).order_by("-created_at")[:20],
        "support_conversation": Conversation.objects.filter(kind=Conversation.Kind.SUPPORT, customer=member).first(),
        "section": "users",
    })


@superuser_required
def user_create(request):
    form = HelperUserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        member = form.save()
        messages.success(request, f"{member.username} yaratildi.")
        return redirect("helper-user-detail", user_id=member.pk)
    return render(request, "core/helper/user_create.html", {"form": form, "section": "users"})


@superuser_required
@require_POST
def user_action(request, user_id, action):
    member = get_object_or_404(User, pk=user_id)
    if member.pk == request.user.pk or member.is_superuser:
        messages.error(request, "Bosh admin yoki o'zingizning hisobingizni bu yerdan o'zgartirib bo'lmaydi.")
        return redirect("helper-user-detail", user_id=member.pk)
    if action == "toggle-staff":
        member.is_staff = not member.is_staff
        member.save(update_fields=["is_staff"])
        messages.success(request, "Admin huquqi yangilandi.")
    elif action == "toggle-active":
        member.is_active = not member.is_active
        member.save(update_fields=["is_active"])
        messages.success(request, "Hisob holati yangilandi.")
    elif action == "delete":
        if Booking.objects.filter(user=member).exists() or RentalListing.objects.filter(owner=member, bookings__isnull=False).exists():
            messages.error(request, "Bronlari bor foydalanuvchini o'chirib bo'lmaydi — uni bloklang.")
            return redirect("helper-user-detail", user_id=member.pk)
        username = member.username
        member.delete()
        messages.success(request, f"{username} o'chirildi.")
        return redirect("helper-users")
    else:
        raise Http404
    return redirect("helper-user-detail", user_id=member.pk)


@staff_required
def products(request):
    listings = RentalListing.objects.select_related("owner", "region", "district").prefetch_related("images").annotate(
        booking_total=Count("bookings", distinct=True),
    ).order_by("-created_at")
    filters = {key: request.GET.get(key, "").strip()[:100] for key in ("q", "kind", "status", "visibility")}
    if filters["q"]:
        query = filters["q"]
        condition = (
            Q(title__icontains=query) | Q(title_ru__icontains=query) | Q(title_en__icontains=query)
            | Q(brand__icontains=query) | Q(owner__username__icontains=query)
            | Q(owner__host_profile__display_name__icontains=query) | Q(city__icontains=query)
        )
        if query.isdigit():
            condition |= Q(pk=int(query))
        listings = listings.filter(condition)
    if filters["kind"] in RentalListing.Kind.values:
        listings = listings.filter(kind=filters["kind"])
    if filters["status"] in RentalListing.AvailabilityStatus.values:
        listings = listings.filter(availability_status=filters["status"])
    if filters["visibility"] == "hidden":
        listings = listings.filter(is_active=False)
    elif filters["visibility"] == "visible":
        listings = listings.filter(is_active=True)
    return render(request, "core/helper/products.html", {
        "page": _page(request, listings), "filters": filters, "section": "products",
        "kind_choices": RentalListing.Kind.choices,
    })


@staff_required
@require_POST
def product_toggle(request, listing_id):
    listing = get_object_or_404(RentalListing, pk=listing_id)
    listing.is_active = not listing.is_active
    listing.save(update_fields=["is_active"])
    messages.success(request, "E'lon ko'rinishi yangilandi.")
    next_url = request.POST.get("next", "")
    return redirect(next_url if next_url.startswith("/helper/") else "helper-products")


@staff_required
def contacts(request):
    contact_messages = ContactMessage.objects.select_related("user").order_by("is_read", "-created_at")
    return render(request, "core/helper/contacts.html", {
        "page": _page(request, contact_messages), "section": "contacts",
    })


@staff_required
@require_POST
def contact_read(request, message_id):
    ContactMessage.objects.filter(pk=message_id).update(is_read=True)
    return redirect("helper-contacts")


@staff_required
@require_POST
@rate_limited("admin-ai", limit=30, window=600, by="user")
def ai_ask(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "So'rov JSON formatida bo'lishi kerak."}, status=400)
    question = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 1000:
        return JsonResponse({"detail": "Savol 1–1000 ta belgidan iborat bo'lishi kerak."}, status=400)
    try:
        answer = ask_admin_assistant(question.strip(), staff_user=request.user)
    except AdminAssistantError as exc:
        return JsonResponse({"detail": str(exc)}, status=503)
    return JsonResponse({"answer": answer})


@staff_required
def unread_counts(request):
    """Badge numbers for the panel's sidebar (polled by helper.js)."""
    support = _support_queryset()
    return JsonResponse({
        "support": support.filter(unread_count__gt=0).count(),
        "contacts": ContactMessage.objects.filter(is_read=False).count(),
        "latest_support_message": ChatMessage.objects.filter(conversation__kind=Conversation.Kind.SUPPORT).aggregate(
            latest=Max("id"),
        )["latest"] or 0,
    })
