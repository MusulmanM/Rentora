from django.db.models import QuerySet
from django.utils import timezone

from .models import Booking, RentalListing


ACTIVE_BOOKING_STATUSES = (
    Booking.Status.PENDING,
    Booking.Status.CONFIRMED,
    Booking.Status.HANDED_OVER,
)


def active_bookings():
    return Booking.objects.filter(
        status__in=ACTIVE_BOOKING_STATUSES,
        check_out__gt=timezone.localdate(),
    )


def listings_visible_to(user, queryset=None) -> QuerySet:
    listings = queryset if queryset is not None else RentalListing.objects.all()
    listings = listings.filter(
        is_active=True,
        availability_status=RentalListing.AvailabilityStatus.ACTIVE,
    )
    reservations = active_bookings()
    if getattr(user, "is_authenticated", False):
        reservations = reservations.exclude(user_id=user.pk)
    return listings.exclude(pk__in=reservations.values("listing_id"))


def can_view_listing(user, listing):
    if getattr(user, "is_authenticated", False):
        if listing.owner_id == user.pk or user.is_staff:
            return True
        if active_bookings().filter(listing=listing, user=user).exists():
            return True
    return listings_visible_to(user, RentalListing.objects.filter(pk=listing.pk)).exists()
