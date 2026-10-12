from datetime import date
import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.views import View
from rest_framework import viewsets
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .forms import BookingForm, RegistrationForm, homeForm, carForm
from .models import Booking, BookingOrder, RentalListing, home, car
from .payments import payment_url
from .serializers import BookingSerializer, ListingSerializer, homeSerializer, carSerializer
from .ai_assistant import RentalAssistantError, find_rentals



def _parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def _available_for_dates(queryset, check_in, check_out):
    if check_in and check_out and check_out > check_in:
        unavailable_ids = Booking.objects.filter(
            status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
            check_in__lt=check_out,
            check_out__gt=check_in,
        ).values_list("listing_id", flat=True)
        unavailable_order_ids = BookingOrder.objects.filter(
            status__in=[BookingOrder.Status.PENDING, BookingOrder.Status.AWAITING_PAYMENT],
            check_in__lt=check_out,
            check_out__gt=check_in,
        ).values_list("listing_id", flat=True)
        return queryset.exclude(id__in=unavailable_ids).exclude(id__in=unavailable_order_ids)
    return queryset


def home(request):
    listings = RentalListing.objects.filter(is_active=True).prefetch_related("images")
    kind = request.GET.get("kind", "")
    city = request.GET.get("city", "").strip()
    query = request.GET.get("q", "").strip()
    check_in_raw = request.GET.get("check_in", "")
    check_out_raw = request.GET.get("check_out", "")
    check_in = _parse_date(check_in_raw)
    check_out = _parse_date(check_out_raw)
    guests_raw = request.GET.get("guests", "1")
    try:
        guests = max(1, min(int(guests_raw), 20))
    except (TypeError, ValueError):
        guests = 1

    if kind in (RentalListing.Kind.HOME, RentalListing.Kind.CAR):
        listings = listings.filter(kind=kind)
    if city:
        listings = listings.filter(city__icontains=city)
    if query:
        listings = listings.filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(address__icontains=query) | Q(brand__icontains=query))
    listings = listings.filter(capacity__gte=guests)
    listings = _available_for_dates(listings, check_in, check_out)
    listings = listings.order_by("-is_featured", "-created_at")

    cities = RentalListing.objects.filter(is_active=True).order_by("city").values_list("city", flat=True).distinct()
    context = {
        "listings": listings,
        "cities": cities,
        "selected_kind": kind,
        "selected_city": city,
        "query": query,
        "check_in": check_in_raw,
        "check_out": check_out_raw,
        "guests": guests,
        "today": timezone.localdate().isoformat(),
        "home_count": RentalListing.objects.filter(is_active=True, kind=RentalListing.Kind.HOME).count(),
        "car_count": RentalListing.objects.filter(is_active=True, kind=RentalListing.Kind.CAR).count(),
        "ai_enabled": bool(getattr(settings, "OPENAI_API_KEY", "")),
    }
    return render(request, "core/home.html", context)


class StartAppLoginView(LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Kirish"
        return context


def register(request):
    if request.user.is_authenticated:
        return redirect("my-bookings")
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Hisobingiz yaratildi. Xush kelibsiz!")
            return redirect("home")
    else:
        form = RegistrationForm()
    return render(request, "core/register.html", {"form": form})


def listing_detail(request, slug):
    listing = get_object_or_404(RentalListing.objects.prefetch_related("images"), slug=slug, is_active=True)
    initial = {}
    for field in ("check_in", "check_out", "guests"):
        if request.GET.get(field):
            initial[field] = request.GET[field]
    form = BookingForm(initial=initial, listing=listing, user=request.user if request.user.is_authenticated else None)
    return render(request, "core/listing_detail.html", {"listing": listing, "form": form, "today": timezone.localdate().isoformat()})


@login_required
def create_booking(request, slug):
    listing = get_object_or_404(RentalListing, slug=slug, is_active=True)
    if request.method != "POST":
        return redirect("listing-detail", slug=slug)
    form = BookingForm(request.POST, listing=listing, user=request.user)
    if form.is_valid():
        try:
            with transaction.atomic():
                locked_listing = RentalListing.objects.select_for_update().filter(pk=listing.pk, is_active=True).first()
                if locked_listing is None:
                    messages.error(request, "Bu e'lon hozir faol emas.")
                    return redirect("home")
                if form.cleaned_data["payment_method"] == Booking.PaymentMethod.CASH:
                    booking = form.save(commit=False)
                    booking.user = request.user
                    booking.listing = locked_listing
                    booking.full_clean()
                    booking.save()
                    messages.success(request, "Buyurtma qabul qilindi. Naqd to'lovni xizmatni olganingizda amalga oshirasiz.")
                else:
                    order = BookingOrder(
                        user=request.user,
                        listing=locked_listing,
                        check_in=form.cleaned_data["check_in"],
                        check_out=form.cleaned_data["check_out"],
                        guests=form.cleaned_data["guests"],
                        payment_method=form.cleaned_data["payment_method"],
                        status=BookingOrder.Status.AWAITING_PAYMENT,
                    )
                    order.full_clean()
                    order.save()
            if form.cleaned_data["payment_method"] == Booking.PaymentMethod.CASH:
                return redirect("my-bookings")
            return redirect("pay-booking-order", order_id=order.pk)
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                for field, errors in exc.message_dict.items():
                    for error in errors:
                        form.add_error(field if field in form.fields else None, error)
            else:
                form.add_error(None, "; ".join(exc.messages))
    return render(request, "core/listing_detail.html", {"listing": listing, "form": form, "today": timezone.localdate().isoformat()}, status=400)


@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(user=request.user).select_related("listing").prefetch_related("listing__images")
    booking_orders = BookingOrder.objects.filter(
        user=request.user,
        status__in=[
            BookingOrder.Status.PENDING,
            BookingOrder.Status.AWAITING_PAYMENT,
            BookingOrder.Status.REJECTED,
            BookingOrder.Status.CANCELLED,
        ],
    ).select_related("listing").prefetch_related("listing__images")
    active_bookings_count = bookings.exclude(status=Booking.Status.CANCELLED).count()
    return render(request, "core/my_bookings.html", {
        "bookings": bookings,
        "booking_orders": booking_orders,
        "active_bookings_count": active_bookings_count,
    })


@login_required
def pay_booking_order(request, order_id):
    order = get_object_or_404(BookingOrder, pk=order_id, user=request.user)
    if order.status != BookingOrder.Status.AWAITING_PAYMENT:
        messages.error(request, "Buyurtma to'lov uchun tayyor emas yoki endi faol emas.")
        return redirect("my-bookings")
    try:
        return redirect(payment_url(order, request))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("my-bookings")


@login_required
@require_POST
def cancel_booking_order(request, order_id):
    order = get_object_or_404(BookingOrder, pk=order_id, user=request.user)
    can_cancel = order.status == BookingOrder.Status.PENDING or (
        order.status == BookingOrder.Status.AWAITING_PAYMENT
        and not order.payments.filter(state=1).exists()
    )
    if can_cancel:
        order.status = BookingOrder.Status.CANCELLED
        order.save(update_fields=["status"])
        messages.success(request, "Buyurtma bekor qilindi.")
    else:
        messages.info(request, "Bu buyurtmani bekor qilib bo'lmaydi.")
    return redirect("my-bookings")


@login_required
@require_POST
def cancel_booking(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, user=request.user)
    if booking.status in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
        booking.status = Booking.Status.CANCELLED
        booking.save(update_fields=["status", "updated_at"])
        messages.success(request, f"#{booking.pk} bron bekor qilindi.")
    else:
        messages.info(request, "Bu bron avval bekor qilingan.")
    return redirect("my-bookings")


@require_GET
def health(request):
    return JsonResponse({"status": "ok", "app": "Rentora", "time": timezone.now().isoformat()})


@require_POST
def ai_rental_search(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "So'rov JSON formatida bo'lishi kerak."}, status=400)
    if not isinstance(payload, dict) or not isinstance(payload.get("message"), str):
        return JsonResponse({"detail": "Qidiruv matni yuborilmadi."}, status=400)
    message = payload["message"].strip()
    if not message or len(message) > 500:
        return JsonResponse({"detail": "So'rov 1–500 ta belgidan iborat bo'lishi kerak."}, status=400)
    try:
        result = find_rentals(message)
    except RentalAssistantError as exc:
        return JsonResponse({"detail": str(exc)}, status=exc.status_code)
    return JsonResponse(result)


@api_view(["GET"])
@permission_classes([AllowAny])
def listings_api(request):
    listings = RentalListing.objects.filter(is_active=True).prefetch_related("images")
    kind = request.query_params.get("kind")
    city = request.query_params.get("city", "").strip()
    query = request.query_params.get("q", "").strip()
    if kind in (RentalListing.Kind.HOME, RentalListing.Kind.CAR):
        listings = listings.filter(kind=kind)
    if city:
        listings = listings.filter(city__icontains=city)
    if query:
        listings = listings.filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(brand__icontains=query))
    check_in = _parse_date(request.query_params.get("check_in", ""))
    check_out = _parse_date(request.query_params.get("check_out", ""))
    listings = _available_for_dates(listings, check_in, check_out)
    return Response(ListingSerializer(listings, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def listing_detail_api(request, listing_id):
    listing = get_object_or_404(RentalListing.objects.prefetch_related("images"), pk=listing_id, is_active=True)
    return Response(ListingSerializer(listing).data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def bookings_api(request):
    if request.method == "GET":
        bookings = Booking.objects.filter(user=request.user).select_related("listing").prefetch_related("listing__images")
        orders = BookingOrder.objects.filter(user=request.user).select_related("listing").prefetch_related("listing__images")
        entries = sorted([*bookings, *orders], key=lambda entry: entry.created_at, reverse=True)
        return Response(BookingSerializer(entries, many=True).data)
    serializer = BookingSerializer(data=request.data, context={"request": request})
    if serializer.is_valid():
        booking = serializer.save()
        response_status = status.HTTP_202_ACCEPTED if isinstance(booking, BookingOrder) else status.HTTP_201_CREATED
        return Response(BookingSerializer(booking).data, status=response_status)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_booking_api(request, booking_id):
    booking = Booking.objects.filter(pk=booking_id, user=request.user).first()
    if not booking:
        return Response({"detail": "Bron topilmadi."}, status=status.HTTP_404_NOT_FOUND)
    if booking.status == Booking.Status.CANCELLED:
        return Response({"detail": "Bron avval bekor qilingan."}, status=status.HTTP_400_BAD_REQUEST)
    booking.status = Booking.Status.CANCELLED
    booking.save(update_fields=["status", "updated_at"])
    return Response(BookingSerializer(booking).data)



class HomeViewSet(viewsets.ModelViewSet):
    serializer_class = homeSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return home.objects.all()
    
class CarViewSet(viewsets.ModelViewSet):
    serializer_class = carSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return car.objects.all()