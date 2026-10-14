"""AI assistant for staff in the helper-admin panel. Read-only: it can inspect, never change."""
from datetime import date

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from .ai_agent import AgentError, Tool, run_agent
from .models import Booking, ChatMessage, Conversation, HostProfile, RentalListing

User = get_user_model()


class AdminAssistantError(Exception):
    pass


SYSTEM_PROMPT = """You assist the Rentora admin team inside the helper-admin panel.
You can read users, bookings, listings and chats with the tools and answer questions about them
(counts, statuses, who booked what, unanswered support chats, problems to look at).
You are strictly read-only: you cannot create, delete, block or edit users, admins, bookings or listings.
If asked to, explain which panel page the admin should use (Users, Bookings, Products) instead.
Never reveal password hashes or secrets. Answer in the admin's language, briefly, with concrete numbers and IDs.
Today is {today}."""


def _date(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _user_row(user):
    profile = getattr(user, "profile", None)
    host = getattr(user, "host_profile", None)
    account = getattr(user, "account", None)
    return {
        "id": user.pk, "uid": str(account.uid) if account else "", "username": user.username,
        "name": user.get_full_name(), "email": user.email, "phone": profile.phone_number if profile else "",
        "is_staff": user.is_staff, "is_active": user.is_active, "company": host.display_name if host else "",
        "joined": user.date_joined.date(),
    }


def build_tools():
    def site_stats():
        today = timezone.localdate()
        return {
            "users": User.objects.count(),
            "providers": HostProfile.objects.count(),
            "listings": dict(RentalListing.objects.values_list("kind").annotate(total=Count("id"))),
            "bookings_by_status": dict(Booking.objects.values_list("status").annotate(total=Count("id"))),
            "bookings_created_today": Booking.objects.filter(created_at__date=today).count(),
            "support_by_status": dict(
                Conversation.objects.filter(kind=Conversation.Kind.SUPPORT)
                .values_list("support_status").annotate(total=Count("id"))
            ),
        }

    def search_users(query="", role="", limit=20):
        users = User.objects.select_related("profile", "host_profile", "account").order_by("-date_joined")
        if query:
            users = users.filter(
                Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query)
                | Q(email__icontains=query) | Q(profile__phone_number__icontains=query)
            )
        if role == "provider":
            users = users.filter(host_profile__isnull=False)
        elif role == "staff":
            users = users.filter(is_staff=True)
        return [_user_row(user) for user in users[: max(1, min(int(limit or 20), 50))]]

    def search_bookings(status="", query="", date_from="", date_to="", limit=20):
        bookings = Booking.objects.select_related("listing", "user").order_by("-created_at")
        if status in Booking.Status.values:
            bookings = bookings.filter(status=status)
        if query:
            bookings = bookings.filter(Q(listing__title__icontains=query) | Q(user__username__icontains=query))
        if _date(date_from):
            bookings = bookings.filter(check_in__gte=_date(date_from))
        if _date(date_to):
            bookings = bookings.filter(check_in__lte=_date(date_to))
        return [{
            "id": booking.pk, "listing_id": booking.listing_id, "listing": booking.listing.title,
            "user_id": booking.user_id, "username": booking.user.username, "status": booking.status,
            "check_in": booking.check_in, "check_out": booking.check_out, "total": float(booking.total_price),
            "payment": booking.payment_method, "created_at": booking.created_at,
        } for booking in bookings[: max(1, min(int(limit or 20), 50))]]

    def search_listings(query="", kind="", limit=20):
        listings = RentalListing.objects.select_related("owner", "region").annotate(bookings_total=Count("bookings"))
        if kind in RentalListing.Kind.values:
            listings = listings.filter(kind=kind)
        if query:
            listings = listings.filter(Q(title__icontains=query) | Q(brand__icontains=query) | Q(city__icontains=query))
        return [{
            "id": listing.pk, "title": listing.title, "kind": listing.kind, "price_per_day": float(listing.price_per_day),
            "owner": listing.owner.username if listing.owner_id else "", "region": listing.region.name_uz if listing.region_id else "",
            "is_active": listing.is_active, "availability": listing.availability_status, "bookings": listing.bookings_total,
        } for listing in listings.order_by("-created_at")[: max(1, min(int(limit or 20), 50))]]

    def list_support_chats(status="", limit=20):
        chats = Conversation.objects.filter(kind=Conversation.Kind.SUPPORT).select_related("customer").order_by("-updated_at")
        if status in Conversation.SupportStatus.values:
            chats = chats.filter(support_status=status)
        return [{
            "conversation_id": chat.pk, "user": chat.customer.username, "status": chat.support_status,
            "updated_at": chat.updated_at,
        } for chat in chats[: max(1, min(int(limit or 20), 50))]]

    def read_chat(conversation_id, limit=30):
        messages = ChatMessage.objects.filter(conversation_id=conversation_id).select_related("sender").order_by("-pk")
        rows = [{
            "from": "AI" if message.is_ai else (message.sender.username if message.sender_id else "?"),
            "text": message.text[:1000], "attachment": message.attachment_type, "at": message.created_at,
        } for message in messages[: max(1, min(int(limit or 30), 100))]]
        rows.reverse()
        return rows

    integer = {"type": ["integer", "null"]}
    text = {"type": "string"}
    return [
        Tool("site_stats", "Overall counts of users, listings, bookings and support chats.", {"type": "object", "properties": {}}, site_stats),
        Tool("search_users", "Find users by name, username, email or phone.", {
            "type": "object", "properties": {"query": text, "role": {"type": "string", "enum": ["", "provider", "staff"]}, "limit": integer},
        }, search_users),
        Tool("search_bookings", "Find bookings by status, listing/user text or check-in date range (YYYY-MM-DD).", {
            "type": "object", "properties": {
                "status": {"type": "string", "enum": ["", *Booking.Status.values]}, "query": text,
                "date_from": text, "date_to": text, "limit": integer,
            },
        }, search_bookings),
        Tool("search_listings", "Find listings (products) by text or kind.", {
            "type": "object", "properties": {"query": text, "kind": {"type": "string", "enum": ["", "home", "car"]}, "limit": integer},
        }, search_listings),
        Tool("list_support_chats", "Support chats with the admin team, optionally by status.", {
            "type": "object", "properties": {"status": {"type": "string", "enum": ["", *Conversation.SupportStatus.values]}, "limit": integer},
        }, list_support_chats),
        Tool("read_chat", "Read the latest messages of a chat by conversation id.", {
            "type": "object", "properties": {"conversation_id": {"type": "integer"}, "limit": integer}, "required": ["conversation_id"],
        }, read_chat),
    ]


def ask_admin_assistant(question, staff_user):
    if not staff_user.is_staff:
        raise AdminAssistantError("Ruxsat yo'q.")
    try:
        return run_agent(
            SYSTEM_PROMPT.format(today=timezone.localdate().isoformat()),
            [{"role": "user", "content": question}],
            build_tools(),
        ) or "Javob topilmadi."
    except AgentError as exc:
        raise AdminAssistantError(str(exc)) from exc
