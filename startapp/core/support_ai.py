"""The support AI answers users in the admin chat when no admin has replied yet.

Privacy is enforced by the tools: the AI can read the public catalog and *only the asking
user's own* bookings. It has no tool that returns other users or admins, so it cannot leak them.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Avg, Count, Q
from django.urls import reverse
from django.utils import timezone

from .ai_agent import AgentError, Tool, run_agent
from .availability import listings_visible_to
from .chat import post_message
from .models import Booking, BookingOrder, Conversation, HostProfile, RentalListing

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the support assistant of Rentora, a home and car rental website in Uzbekistan.
You reply in the user's chat with the Rentora admin team and sign nothing: the user sees your reply as "Rentora Admin".
Reply in the language the user writes in (Uzbek, Russian or English). Be short, friendly and concrete.

What you can do:
- Find homes and cars with search_listings / get_listing (prices are Uzbek so'm per day).
- Look at THIS user's own bookings and orders with my_bookings and explain their status.
- Explain how Rentora works: search, booking (cash = request sent to the provider; Click/Payme = pay online first),
  provider confirms, then marks the hand-over; cancelling pending/confirmed bookings from "Bronlarim";
  chatting with providers from a listing page; becoming a provider from the profile (verified phone,
  company name, logo and phone are required); Telegram notifications need the phone verified via the Telegram bot.

Strict rules:
- Never reveal personal data of other users or of admins (names, usernames, phone numbers, emails, IDs,
  their bookings or messages). You only have access to the current user's own data; say so if asked.
- You cannot create, delete, block or change accounts, admins, payments or bookings. Never pretend you did.
  For refunds, disputes, account problems, payment problems, safety or anything you cannot answer, call
  escalate_to_admin and tell the user an admin will reply here soon.
- Never ask for passwords, OTP codes or card details.
- Do not invent listings, prices or policies; use the tools.
Today is {today}."""


def _public_listing(listing):
    host = HostProfile.objects.filter(user_id=listing.owner_id).first() if listing.owner_id else None
    stats = listing.reviews.aggregate(average=Avg("rating"), count=Count("id"))
    return {
        "id": listing.pk,
        "title": listing.title,
        "title_ru": listing.title_ru,
        "title_en": listing.title_en,
        "kind": listing.kind,
        "region": listing.region.name_uz if listing.region_id else "",
        "district": listing.district.name_uz if listing.district_id else listing.city,
        "price_per_day": float(listing.price_per_day),
        "capacity": listing.capacity,
        "bedrooms": listing.bedrooms,
        "brand": listing.brand,
        "year": listing.year,
        "transmission": listing.get_transmission_display() if listing.is_car else "",
        "company": host.display_name if host else "",
        "company_phone": host.phone_number if host else "",
        "rating": round(stats["average"], 1) if stats["average"] else None,
        "reviews": stats["count"],
        "url": reverse("listing-detail", args=[listing.slug]),
    }


def build_tools(user, state):
    def search_listings(query="", kind="", max_price=None, min_price=None, guests=None, region="", limit=6):
        listings = listings_visible_to(user, RentalListing.objects.select_related("region", "district"))
        if kind in RentalListing.Kind.values:
            listings = listings.filter(kind=kind)
        if query:
            listings = listings.filter(
                Q(title__icontains=query) | Q(title_ru__icontains=query) | Q(title_en__icontains=query)
                | Q(brand__icontains=query) | Q(description__icontains=query)
            )
        if region:
            listings = listings.filter(
                Q(region__name_uz__icontains=region) | Q(region__name_ru__icontains=region)
                | Q(region__name_en__icontains=region) | Q(district__name_uz__icontains=region)
                | Q(district__name_ru__icontains=region) | Q(city__icontains=region)
            )
        if max_price:
            listings = listings.filter(price_per_day__lte=max_price)
        if min_price:
            listings = listings.filter(price_per_day__gte=min_price)
        if guests:
            listings = listings.filter(capacity__gte=guests)
        limit = max(1, min(int(limit or 6), 10))
        return [_public_listing(listing) for listing in listings.order_by("price_per_day")[:limit]]

    def get_listing(listing_id):
        listing = listings_visible_to(user, RentalListing.objects.select_related("region", "district")).filter(
            pk=listing_id,
        ).first()
        return _public_listing(listing) if listing else {"error": "not found"}

    def my_bookings():
        bookings = Booking.objects.filter(user=user).select_related("listing").order_by("-created_at")[:10]
        orders = BookingOrder.objects.filter(user=user).select_related("listing").order_by("-created_at")[:5]
        return {
            "bookings": [{
                "id": booking.pk, "listing": booking.listing.title, "status": booking.get_status_display(),
                "check_in": booking.check_in, "check_out": booking.check_out, "total": float(booking.total_price),
                "payment": booking.get_payment_method_display(),
            } for booking in bookings],
            "online_orders": [{
                "listing": order.listing.title, "status": order.get_status_display(),
                "check_in": order.check_in, "check_out": order.check_out, "total": float(order.total_price),
            } for order in orders],
        }

    def escalate_to_admin(reason=""):
        state["escalated"] = True
        return {"ok": True}

    number = {"type": ["number", "null"]}
    return [
        Tool("search_listings", "Search public homes and cars that are available on Rentora.", {
            "type": "object",
            "properties": {
                "query": {"type": "string"}, "kind": {"type": "string", "enum": ["", "home", "car"]},
                "max_price": number, "min_price": number, "guests": {"type": ["integer", "null"]},
                "region": {"type": "string", "description": "Region, city or district name"},
                "limit": {"type": "integer"},
            },
        }, search_listings),
        Tool("get_listing", "Public details of one listing by id.", {
            "type": "object", "properties": {"listing_id": {"type": "integer"}}, "required": ["listing_id"],
        }, get_listing),
        Tool("my_bookings", "The current user's own bookings and online orders.", {
            "type": "object", "properties": {},
        }, my_bookings),
        Tool("escalate_to_admin", "Hand the conversation to a human admin.", {
            "type": "object", "properties": {"reason": {"type": "string"}},
        }, escalate_to_admin),
    ]


def _history(conversation, limit=20):
    messages = list(conversation.messages.select_related("sender").order_by("-pk")[:limit])
    messages.reverse()
    history = []
    for message in messages:
        text = message.text or f"[{message.get_attachment_type_display() or 'fayl'}]"
        role = "user" if message.sender_id == conversation.customer_id else "assistant"
        history.append({"role": role, "content": text})
    return history


def answer_conversation(conversation):
    """Write one AI reply in a support chat. Returns the created message."""
    state = {"escalated": False}
    reply = run_agent(
        SYSTEM_PROMPT.format(today=timezone.localdate().isoformat()),
        _history(conversation),
        build_tools(conversation.customer, state),
    )
    if not reply:
        raise AgentError("AI bo'sh javob qaytardi.")
    message = post_message(conversation, None, text=reply[:5000], is_ai=True)
    status = Conversation.SupportStatus.ESCALATED if state["escalated"] else Conversation.SupportStatus.AI
    Conversation.objects.filter(pk=conversation.pk).update(support_status=status)
    conversation.support_status = status
    return message


def conversations_needing_ai():
    """Support chats where the user's last message has waited longer than the configured delay."""
    cutoff = timezone.now() - timedelta(seconds=getattr(settings, "SUPPORT_AI_DELAY_SECONDS", 120))
    waiting = Conversation.objects.filter(
        kind=Conversation.Kind.SUPPORT, support_status=Conversation.SupportStatus.WAITING,
    ).select_related("customer")
    ready = []
    for conversation in waiting:
        last = conversation.messages.order_by("-pk").first()
        if last and last.sender_id == conversation.customer_id and last.created_at <= cutoff:
            ready.append(conversation)
    return ready
