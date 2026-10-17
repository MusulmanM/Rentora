from datetime import date
from datetime import timedelta
import json
import logging
from decimal import Decimal
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Avg, Case, Count, F, IntegerField, Q, Value, When
from django.db.models.functions import Abs
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .analytics import provider_income
from .availability import ACTIVE_BOOKING_STATUSES, active_bookings, can_view_listing, listings_visible_to
from .chat import (
    conversations_for, mark_read, other_side_last_read, post_message,
    serialize_message, support_conversation_for, unread_messages,
)
from .forms import (
    BookingForm, ChatMessageForm, ContactMessageForm, HostOnboardingForm, ListingAvailabilityForm,
    ListingReviewForm, PhoneNumberForm, ProfileEditForm, ProviderPaymentForm, RegistrationForm,
    RegistrationOTPForm, RentalListingForm, StartAppAuthenticationForm,
)
from .media import serve_private_file
from .models import (
    Booking, BookingOrder, District, HostProfile, ListingReview, PendingRegistration,
    Installment, Payout, PendingPhoneVerification, ProviderPaymentAccount, Region, RentalListing, ListingImage, TelegramAccount,
    UserProfile, Conversation, ChatMessage, account_for,
)
from .security import rate_limited
from .installments import create_installments, mark_installment_paid, next_unpaid
from .payments import installment_payment_url, payment_url
from .payouts import commission_percent, notify_card_review, refund_for_cancelled, release_payout
from .serializers import BookingSerializer, ListingSerializer
from .ai_assistant import RentalAssistantError, find_rentals
from .listing_translation import translate_listing, translation_enabled
from .telegram import (
    TelegramError, handle_telegram_update, notify_booking_parties, notify_installment_paid, send_localized, send_message,
)


logger = logging.getLogger(__name__)
User = get_user_model()
PENDING_REGISTRATION_SESSION_KEY = "pending_registration_id"
OTP_LIFETIME = timedelta(minutes=10)
OTP_RESEND_INTERVAL = timedelta(seconds=60)
OTP_MAX_ATTEMPTS = 5
PENDING_PHONE_SESSION_KEY = "pending_phone_verification_id"


def _parse_date(value):
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def _available_for_dates(queryset, check_in, check_out):
    if check_in and check_out and check_out > check_in:
        unavailable_ids = Booking.objects.filter(
            status__in=ACTIVE_BOOKING_STATUSES,
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


def _otp_rate_limited(account, now):
    return bool(account.last_otp_sent_at and now - account.last_otp_sent_at < OTP_RESEND_INTERVAL)


def _record_otp_delivery(account, now):
    account.last_otp_sent_at = now
    account.save(update_fields=["last_otp_sent_at"])


def home(request):
    listings = listings_visible_to(
        request.user,
        RentalListing.objects.select_related("region", "district").prefetch_related("images"),
    )
    kind = request.GET.get("kind", "")
    city = request.GET.get("city", "").strip()
    region = None
    district = None
    try:
        region = Region.objects.filter(pk=int(request.GET.get("region", ""))).first()
    except (TypeError, ValueError):
        pass
    try:
        district = District.objects.select_related("region").filter(
            pk=int(request.GET.get("district", "")),
        ).first()
    except (TypeError, ValueError):
        pass
    if district and region and district.region_id != region.pk:
        district = None
    if district and region is None:
        region = district.region
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
    if region:
        listings = listings.filter(region=region)
    if district:
        listings = listings.filter(district=district)
    if query:
        listings = listings.filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(address__icontains=query) | Q(brand__icontains=query))
    listings = listings.filter(capacity__gte=guests)
    listings = _available_for_dates(listings, check_in, check_out)
    listings = listings.order_by("-is_featured", "-created_at")
    page = Paginator(listings, 24).get_page(request.GET.get("page"))

    context = {
        "listings": page,
        "page": page,
        "regions": Region.objects.all(),
        "districts": District.objects.select_related("region").all(),
        "selected_kind": kind,
        "selected_city": city,
        "selected_region": region.pk if region else "",
        "selected_district": district.pk if district else "",
        "query": query,
        "check_in": check_in_raw,
        "check_out": check_out_raw,
        "guests": guests,
        "today": timezone.localdate().isoformat(),
        "home_count": listings_visible_to(request.user).filter(kind=RentalListing.Kind.HOME).count(),
        "car_count": listings_visible_to(request.user).filter(kind=RentalListing.Kind.CAR).count(),
    }
    return render(request, "core/home.html", context)


class StartAppLoginView(LoginView):
    template_name = "core/login.html"
    redirect_authenticated_user = True
    authentication_form = StartAppAuthenticationForm

    def get_initial(self):
        # After a password reset the username is already filled in.
        initial = super().get_initial()
        username = self.request.GET.get("username", "").strip()[:150]
        if username:
            initial["username"] = username
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Kirish"
        form = context.get("form")
        context["account_blocked"] = bool(form and form.is_bound and form.has_error("__all__", "blocked"))
        context["password_missing"] = bool(form and form.is_bound and form.has_error("__all__", "no_password"))
        return context


@rate_limited("register", limit=10, window=3600)
def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            phone_number = form.cleaned_data["phone_number"]
            pending = PendingRegistration.objects.filter(
                phone_number=phone_number, expires_at__gt=timezone.now(),
            ).first()
            if pending:
                if pending.attempts < OTP_MAX_ATTEMPTS:
                    request.session[PENDING_REGISTRATION_SESSION_KEY] = pending.pk
                    return redirect("verify-registration")
                pending.delete()
            try:
                telegram_account = TelegramAccount.objects.get(phone_number=phone_number)
            except TelegramAccount.DoesNotExist:
                form.add_error(
                    "phone_number",
                    "Avval Telegram botga kirib, telefon raqamingizni yuboring.",
                )
            else:
                PendingRegistration.objects.filter(telegram_account=telegram_account).delete()
                if UserProfile.objects.filter(phone_number=phone_number).exists():
                    form.add_error("phone_number", "Bu telefon raqami allaqachon ro'yxatdan o'tgan.")
                else:
                    now = timezone.now()
                    if _otp_rate_limited(telegram_account, now):
                        form.add_error("phone_number", "Yangi kodni 60 soniyadan keyin so'rashingiz mumkin.")
                    else:
                        user = form.save(commit=False)
                        code = f"{secrets.randbelow(1_000_000):06d}"
                        pending = PendingRegistration.objects.create(
                            username=user.get_username(),
                            first_name=user.first_name,
                            email=user.email,
                            phone_number=phone_number,
                            password_hash=user.password,
                            telegram_account=telegram_account,
                            otp_hash=make_password(code),
                            expires_at=now + OTP_LIFETIME,
                            sent_at=now,
                        )
                        try:
                            send_localized(telegram_account.chat_id, "otp_register", code=code)
                        except TelegramError as exc:
                            pending.delete()
                            form.add_error(None, str(exc))
                        else:
                            _record_otp_delivery(telegram_account, now)
                            request.session[PENDING_REGISTRATION_SESSION_KEY] = pending.pk
                            messages.success(request, "Tasdiqlash kodi Telegram botga yuborildi.")
                            return redirect("verify-registration")
    else:
        form = RegistrationForm()
    return render(request, "core/register.html", {
        "form": form,
        "telegram_bot_username": getattr(settings, "TELEGRAM_BOT_USERNAME", ""),
    })


def verify_registration(request):
    pending_id = request.session.get(PENDING_REGISTRATION_SESSION_KEY)
    if not pending_id:
        return redirect("register")
    pending = PendingRegistration.objects.filter(pk=pending_id).first()
    if pending is None:
        request.session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
        return redirect("register")
    if pending.expires_at <= timezone.now():
        pending.delete()
        request.session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
        messages.error(request, "Tasdiqlash kodi muddati tugadi. Qayta ro'yxatdan o'ting.")
        return redirect("register")

    form = RegistrationOTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        created_user = None
        expired = False
        attempts_exhausted = False
        invalid_code = False
        duplicate_phone = False
        try:
            with transaction.atomic():
                pending = PendingRegistration.objects.select_for_update().get(pk=pending_id)
                now = timezone.now()
                if pending.expires_at <= now:
                    pending.delete()
                    expired = True
                elif pending.attempts >= OTP_MAX_ATTEMPTS:
                    pending.delete()
                    attempts_exhausted = True
                else:
                    pending.attempts += 1
                    if not check_password(form.cleaned_data["code"], pending.otp_hash):
                        if pending.attempts >= OTP_MAX_ATTEMPTS:
                            pending.delete()
                            attempts_exhausted = True
                        else:
                            pending.save(update_fields=["attempts"])
                            invalid_code = True
                    elif UserProfile.objects.filter(phone_number=pending.phone_number).exists():
                        pending.delete()
                        duplicate_phone = True
                    else:
                        created_user = User(
                            username=pending.username,
                            first_name=pending.first_name,
                            email=pending.email,
                            password=pending.password_hash,
                        )
                        created_user.save()
                        UserProfile.objects.create(
                            user=created_user,
                            phone_number=pending.phone_number,
                            telegram_account=pending.telegram_account,
                        )
                        pending.delete()
        except (PendingRegistration.DoesNotExist, IntegrityError):
            logger.info("Registration OTP completion conflicted with another registration.")
            PendingRegistration.objects.filter(pk=pending_id).delete()
            request.session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
            messages.error(request, "Ro'yxatdan o'tish yakunlanmadi. Qaytadan urinib ko'ring.")
            return redirect("register")
        if expired:
            request.session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
            messages.error(request, "Tasdiqlash kodi muddati tugadi. Qayta ro'yxatdan o'ting.")
            return redirect("register")
        if attempts_exhausted:
            request.session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
            messages.error(request, "Urinishlar limiti tugadi. Qayta ro'yxatdan o'ting.")
            return redirect("register")
        elif invalid_code:
            form.add_error("code", "Kod noto'g'ri. 5 tagacha urinish mumkin.")
        elif duplicate_phone:
            request.session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
            messages.error(request, "Bu telefon raqami allaqachon ro'yxatdan o'tgan.")
            return redirect("register")
        elif created_user:
            request.session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
            login(request, created_user)
            messages.success(request, "Telefon raqamingiz tasdiqlandi. Xush kelibsiz!")
            return redirect("home")

    return render(request, "core/verify_registration.html", {"form": form, "expires_at": pending.expires_at})


@require_POST
def resend_registration_otp(request):
    pending_id = request.session.get(PENDING_REGISTRATION_SESSION_KEY)
    pending = PendingRegistration.objects.filter(pk=pending_id).select_related("telegram_account").first()
    if pending is None:
        request.session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
        messages.error(request, "Faol tasdiqlash jarayoni topilmadi. Qayta ro'yxatdan o'ting.")
        return redirect("register")
    now = timezone.now()
    if pending.expires_at <= now:
        pending.delete()
        request.session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
        messages.error(request, "Tasdiqlash kodi muddati tugadi. Qayta ro'yxatdan o'ting.")
        return redirect("register")
    if pending.attempts >= OTP_MAX_ATTEMPTS:
        pending.delete()
        request.session.pop(PENDING_REGISTRATION_SESSION_KEY, None)
        messages.error(request, "Urinishlar limiti tugadi. Qayta ro'yxatdan o'ting.")
        return redirect("register")
    if now - pending.sent_at < OTP_RESEND_INTERVAL or _otp_rate_limited(pending.telegram_account, now):
        messages.error(request, "Yangi kodni 60 soniyadan keyin so'rashingiz mumkin.")
        return redirect("verify-registration")
    code = f"{secrets.randbelow(1_000_000):06d}"
    try:
        send_localized(pending.telegram_account.chat_id, "otp_register", code=code)
    except TelegramError as exc:
        messages.error(request, str(exc))
        return redirect("verify-registration")
    pending.otp_hash = make_password(code)
    pending.sent_at = now
    pending.expires_at = now + OTP_LIFETIME
    pending.save(update_fields=["otp_hash", "sent_at", "expires_at"])
    _record_otp_delivery(pending.telegram_account, now)
    messages.success(request, "Yangi kod Telegram botga yuborildi.")
    return redirect("verify-registration")


@login_required
def verify_profile_phone(request):
    if UserProfile.objects.filter(user=request.user).exists():
        return redirect("profile")
    PendingPhoneVerification.objects.filter(expires_at__lte=timezone.now()).delete()
    form = PhoneNumberForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        phone_number = form.cleaned_data["phone_number"]
        pending = PendingPhoneVerification.objects.filter(user=request.user).first()
        if pending and (pending.attempts >= OTP_MAX_ATTEMPTS or pending.expires_at <= timezone.now()):
            pending.delete()
            pending = None
        if pending and pending.expires_at > timezone.now() and pending.phone_number == phone_number:
            request.session[PENDING_PHONE_SESSION_KEY] = pending.pk
            return redirect("confirm-profile-phone")
        if pending:
            pending.delete()
        account = TelegramAccount.objects.filter(phone_number=phone_number).first()
        if account is None:
            form.add_error("phone_number", "Avval Telegram botga kirib, telefon raqamingizni yuboring.")
        elif _otp_rate_limited(account, timezone.now()):
            form.add_error("phone_number", "Yangi kodni 60 soniyadan keyin so'rashingiz mumkin.")
        elif UserProfile.objects.filter(telegram_account=account).exists():
            form.add_error("phone_number", "Bu Telegram hisobi boshqa foydalanuvchiga bog'langan.")
        else:
            now = timezone.now()
            code = f"{secrets.randbelow(1_000_000):06d}"
            pending = PendingPhoneVerification.objects.create(
                user=request.user,
                phone_number=phone_number,
                telegram_account=account,
                otp_hash=make_password(code),
                expires_at=now + OTP_LIFETIME,
                sent_at=now,
            )
            try:
                send_localized(account.chat_id, "otp_phone", code=code)
            except TelegramError as exc:
                pending.delete()
                form.add_error(None, str(exc))
            else:
                _record_otp_delivery(account, now)
                request.session[PENDING_PHONE_SESSION_KEY] = pending.pk
                messages.success(request, "Tasdiqlash kodi Telegram botga yuborildi.")
                return redirect("confirm-profile-phone")
    return render(request, "core/verify_profile_phone.html", {"form": form})


@login_required
def confirm_profile_phone(request):
    pending_id = request.session.get(PENDING_PHONE_SESSION_KEY)
    pending = PendingPhoneVerification.objects.filter(pk=pending_id, user=request.user).first()
    if pending is None:
        request.session.pop(PENDING_PHONE_SESSION_KEY, None)
        return redirect("verify-profile-phone")
    if pending.expires_at <= timezone.now():
        pending.delete()
        request.session.pop(PENDING_PHONE_SESSION_KEY, None)
        messages.error(request, "Tasdiqlash kodi muddati tugadi. Qaytadan so'rang.")
        return redirect("verify-profile-phone")
    form = RegistrationOTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        expired = False
        invalid_code = False
        attempts_exhausted = False
        duplicate_phone = False
        try:
            with transaction.atomic():
                pending = PendingPhoneVerification.objects.select_for_update().get(pk=pending_id, user=request.user)
                if pending.expires_at <= timezone.now():
                    pending.delete()
                    expired = True
                elif pending.attempts >= OTP_MAX_ATTEMPTS:
                    pending.delete()
                    attempts_exhausted = True
                else:
                    pending.attempts += 1
                    if not check_password(form.cleaned_data["code"], pending.otp_hash):
                        if pending.attempts >= OTP_MAX_ATTEMPTS:
                            pending.delete()
                            attempts_exhausted = True
                        else:
                            pending.save(update_fields=["attempts"])
                            invalid_code = True
                    elif UserProfile.objects.filter(phone_number=pending.phone_number).exists():
                        pending.delete()
                        duplicate_phone = True
                    else:
                        UserProfile.objects.create(
                            user=request.user,
                            phone_number=pending.phone_number,
                            telegram_account=pending.telegram_account,
                        )
                        pending.delete()
        except (PendingPhoneVerification.DoesNotExist, IntegrityError):
            logger.info("Phone verification conflicted with another account.")
            PendingPhoneVerification.objects.filter(pk=pending_id, user=request.user).delete()
            request.session.pop(PENDING_PHONE_SESSION_KEY, None)
            messages.error(request, "Telefon raqami tasdiqlanmadi. Qaytadan urinib ko'ring.")
            return redirect("profile")
        if expired:
            request.session.pop(PENDING_PHONE_SESSION_KEY, None)
            messages.error(request, "Tasdiqlash kodi muddati tugadi. Qaytadan so'rang.")
            return redirect("verify-profile-phone")
        if attempts_exhausted:
            messages.error(request, "Urinishlar limiti tugadi. Qaytadan tasdiqlashni boshlang.")
            request.session.pop(PENDING_PHONE_SESSION_KEY, None)
            return redirect("verify-profile-phone")
        elif invalid_code:
            form.add_error("code", "Kod noto'g'ri. 5 tagacha urinish mumkin.")
        elif duplicate_phone:
            request.session.pop(PENDING_PHONE_SESSION_KEY, None)
            messages.error(request, "Bu telefon raqami allaqachon boshqa hisobga bog'langan.")
            return redirect("profile")
        else:
            request.session.pop(PENDING_PHONE_SESSION_KEY, None)
            messages.success(request, "Telefon raqamingiz tasdiqlandi.")
            return redirect("profile")
    return render(request, "core/confirm_profile_phone.html", {"form": form})


@login_required
@require_POST
def resend_profile_phone_otp(request):
    pending_id = request.session.get(PENDING_PHONE_SESSION_KEY)
    pending = PendingPhoneVerification.objects.filter(
        pk=pending_id, user=request.user,
    ).select_related("telegram_account").first()
    if pending is None:
        request.session.pop(PENDING_PHONE_SESSION_KEY, None)
        messages.error(request, "Faol tasdiqlash jarayoni topilmadi.")
        return redirect("verify-profile-phone")
    now = timezone.now()
    if pending.expires_at <= now:
        pending.delete()
        request.session.pop(PENDING_PHONE_SESSION_KEY, None)
        messages.error(request, "Tasdiqlash kodi muddati tugadi. Qaytadan so'rang.")
        return redirect("verify-profile-phone")
    if pending.attempts >= OTP_MAX_ATTEMPTS:
        pending.delete()
        request.session.pop(PENDING_PHONE_SESSION_KEY, None)
        messages.error(request, "Urinishlar limiti tugadi. Qaytadan tasdiqlashni boshlang.")
        return redirect("verify-profile-phone")
    if now - pending.sent_at < OTP_RESEND_INTERVAL or _otp_rate_limited(pending.telegram_account, now):
        messages.error(request, "Yangi kodni 60 soniyadan keyin so'rashingiz mumkin.")
        return redirect("confirm-profile-phone")
    code = f"{secrets.randbelow(1_000_000):06d}"
    try:
        send_localized(pending.telegram_account.chat_id, "otp_phone", code=code)
    except TelegramError as exc:
        messages.error(request, str(exc))
        return redirect("confirm-profile-phone")
    pending.otp_hash = make_password(code)
    pending.sent_at = now
    pending.expires_at = now + OTP_LIFETIME
    pending.save(update_fields=["otp_hash", "sent_at", "expires_at"])
    _record_otp_delivery(pending.telegram_account, now)
    messages.success(request, "Yangi kod Telegram botga yuborildi.")
    return redirect("confirm-profile-phone")


@csrf_exempt
@require_POST
def telegram_webhook(request):
    expected_secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "")
    provided_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not expected_secret or not secrets.compare_digest(provided_secret, expected_secret):
        return JsonResponse({"detail": "Webhook ruxsati yo'q."}, status=403)
    if len(request.body) > 1_000_000:
        return JsonResponse({"detail": "So'rov juda katta."}, status=413)
    try:
        update = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Noto'g'ri JSON."}, status=400)
    if not isinstance(update, dict):
        return JsonResponse({"detail": "Noto'g'ri Telegram yangilanishi."}, status=400)
    handle_telegram_update(update)
    return JsonResponse({"ok": True})


def _similar_listings(listing, user, limit=4):
    """Same type first, then same region, then the closest daily price."""
    return (
        listings_visible_to(user, RentalListing.objects.select_related("region", "district").prefetch_related("images"))
        .filter(kind=listing.kind)
        .exclude(pk=listing.pk)
        .annotate(
            same_region=Case(When(region_id=listing.region_id, then=Value(1)), default=Value(0), output_field=IntegerField()),
            price_gap=Abs(F("price_per_day") - listing.price_per_day),
        )
        .order_by("-same_region", "price_gap")[:limit]
    )


def _listing_detail_context(request, listing, form, review_form=None):
    current_booking = active_bookings().filter(listing=listing).select_related("user").first()
    host_profile = HostProfile.objects.filter(user_id=listing.owner_id).first() if listing.owner_id else None
    reviews = listing.reviews.select_related("user", "user__account")
    review_stats = reviews.aggregate(average=Avg("rating"), count=Count("id"))
    is_owner = request.user.is_authenticated and listing.owner_id == request.user.pk
    own_review = reviews.filter(user=request.user).first() if request.user.is_authenticated else None
    if review_form is None and request.user.is_authenticated and not is_owner:
        review_form = ListingReviewForm(instance=own_review)
    return {
        "listing": listing, "form": form, "today": timezone.localdate().isoformat(),
        "current_booking": current_booking,
        "can_book_listing": (
            listing.availability_status == RentalListing.AvailabilityStatus.ACTIVE
            and current_booking is None
            and not is_owner
        ),
        "host_profile": host_profile,
        "reviews": reviews[:50],
        "review_average": review_stats["average"],
        "review_count": review_stats["count"],
        "review_form": review_form,
        "own_review": own_review,
        "similar_listings": _similar_listings(listing, request.user),
    }


@login_required
@require_POST
@rate_limited("review", limit=10, window=3600, by="user")
def post_review(request, slug):
    listing = get_object_or_404(
        RentalListing.objects.select_related("region", "district").prefetch_related("images"), slug=slug,
    )
    if not can_view_listing(request.user, listing):
        raise Http404
    if listing.owner_id == request.user.pk:
        messages.error(request, "O'z e'loningizga baho bera olmaysiz.")
        return redirect("listing-detail", slug=slug)
    review = ListingReview.objects.filter(listing=listing, user=request.user).first()
    review_form = ListingReviewForm(request.POST, instance=review)
    if review_form.is_valid():
        review = review_form.save(commit=False)
        review.listing = listing
        review.user = request.user
        review.save()
        messages.success(request, "Izohingiz uchun rahmat!")
        return redirect(f"{reverse('listing-detail', args=[slug])}#reviews")
    booking_form = BookingForm(listing=listing, user=request.user)
    return render(
        request, "core/listing_detail.html",
        _listing_detail_context(request, listing, booking_form, review_form=review_form), status=400,
    )


def listing_detail(request, slug):
    listing = get_object_or_404(
        RentalListing.objects.select_related("region", "district").prefetch_related("images"),
        slug=slug,
    )
    if not can_view_listing(request.user, listing):
        raise Http404
    initial = {
        field: request.GET[field]
        for field in ("check_in", "check_out", "guests")
        if request.GET.get(field)
    }
    form = BookingForm(initial=initial, listing=listing, user=request.user if request.user.is_authenticated else None)
    return render(request, "core/listing_detail.html", _listing_detail_context(request, listing, form))


def _warn_if_telegram_not_linked(request):
    if not UserProfile.objects.filter(user=request.user).exists():
        messages.warning(
            request,
            "Bron holati haqida Telegram xabarlarini olish uchun profilingizda telefon raqamingizni tasdiqlang.",
        )


@login_required
def create_booking(request, slug):
    listing = get_object_or_404(RentalListing, slug=slug, is_active=True)
    if request.method != "POST":
        return redirect("listing-detail", slug=slug)
    if listing.owner_id == request.user.pk:
        messages.error(request, "O'zingiz joylagan e'lonni bron qila olmaysiz.")
        return redirect("listing-detail", slug=slug)
    if listing.availability_status != RentalListing.AvailabilityStatus.ACTIVE:
        messages.error(request, "Bu e'lon hozir remontda.")
        return redirect("home")
    form = BookingForm(request.POST, listing=listing, user=request.user)
    if form.is_valid():
        try:
            with transaction.atomic():
                locked_listing = RentalListing.objects.select_for_update().filter(
                    pk=listing.pk,
                    is_active=True,
                    availability_status=RentalListing.AvailabilityStatus.ACTIVE,
                ).first()
                if locked_listing is None:
                    messages.error(request, "Bu e'lon hozir faol emas.")
                    return redirect("home")
                if form.cleaned_data["payment_method"] == Booking.PaymentMethod.CASH:
                    booking = form.save(commit=False)
                    booking.user = request.user
                    booking.listing = locked_listing
                    booking.full_clean()
                    booking.save()
                    create_installments(booking)
                    messages.success(request, "Buyurtma qabul qilindi. Naqd to'lovni xizmatni olganingizda amalga oshirasiz.")
                else:
                    order = BookingOrder(
                        user=request.user,
                        listing=locked_listing,
                        check_in=form.cleaned_data["check_in"],
                        check_out=form.cleaned_data["check_out"],
                        guests=form.cleaned_data["guests"],
                        payment_method=form.cleaned_data["payment_method"],
                        rental_unit=form.cleaned_data["rental_unit"],
                        months=form.cleaned_data["months"],
                        payment_plan=form.cleaned_data["payment_plan"],
                        status=BookingOrder.Status.AWAITING_PAYMENT,
                    )
                    order.full_clean()
                    order.save()
            _warn_if_telegram_not_linked(request)
            if form.cleaned_data["payment_method"] == Booking.PaymentMethod.CASH:
                transaction.on_commit(lambda: notify_booking_parties(
                    booking.pk, "requested", request.build_absolute_uri("/").rstrip("/"),
                ))
                return redirect("my-bookings")
            return redirect("pay-booking-order", order_id=order.pk)
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                for field, errors in exc.message_dict.items():
                    for error in errors:
                        form.add_error(field if field in form.fields else None, error)
            else:
                form.add_error(None, "; ".join(exc.messages))
    return render(
        request, "core/listing_detail.html", _listing_detail_context(request, listing, form), status=400,
    )


@login_required
def my_bookings(request):
    bookings = Booking.objects.filter(user=request.user).select_related("listing").prefetch_related("listing__images", "installments")
    booking_orders = BookingOrder.objects.filter(
        user=request.user,
        status__in=[
            BookingOrder.Status.PENDING,
            BookingOrder.Status.AWAITING_PAYMENT,
            BookingOrder.Status.REJECTED,
            BookingOrder.Status.CANCELLED,
        ],
    ).select_related("listing").prefetch_related("listing__images")
    active_bookings_count = active_bookings().filter(user=request.user).count()
    return render(request, "core/my_bookings.html", {
        "bookings": bookings,
        "booking_orders": booking_orders,
        "active_bookings_count": active_bookings_count,
        "today": timezone.localdate(),
    })


@login_required
def user_profile(request):
    profile = UserProfile.objects.filter(user=request.user).select_related("telegram_account").first()
    host_profile = HostProfile.objects.filter(user=request.user).first()
    return render(request, "core/profile.html", {
        "profile": profile,
        "host_profile": host_profile,
        "account": account_for(request.user),
    })


@login_required
def profile_edit(request):
    account = account_for(request.user)
    form = ProfileEditForm(
        request.POST or None, request.FILES or None,
        initial={"first_name": request.user.first_name, "last_name": request.user.last_name},
    )
    if request.method == "POST" and form.is_valid():
        request.user.first_name = form.cleaned_data["first_name"]
        request.user.last_name = form.cleaned_data["last_name"]
        request.user.save(update_fields=["first_name", "last_name"])
        avatar = form.cleaned_data.get("avatar")
        if avatar or form.cleaned_data.get("remove_avatar"):
            if account.avatar:
                account.avatar.delete(save=False)
            account.avatar = avatar or ""
            account.save(update_fields=["avatar"])
        messages.success(request, "Profil yangilandi.")
        return redirect("profile")
    return render(request, "core/profile_edit.html", {"form": form, "account": account})


@login_required
def provider_onboarding(request):
    if not UserProfile.objects.filter(user=request.user).exists():
        messages.error(request, "Ijara beruvchi bo'lish uchun telefon raqamingizni Telegram orqali tasdiqlang.")
        return redirect("profile")
    if HostProfile.objects.filter(user=request.user).exists():
        return redirect("provider-dashboard")
    form = HostOnboardingForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        host_profile = form.save(commit=False)
        host_profile.user = request.user
        host_profile.save()
        messages.success(request, "Ijara beruvchi profilingiz yaratildi. E'lon qo'shishingiz mumkin.")
        return redirect("provider-dashboard")
    return render(request, "core/provider_onboarding.html", {"form": form})


@login_required
def provider_company(request):
    host_profile = get_object_or_404(HostProfile, user=request.user)
    old_logo = host_profile.logo.name if host_profile.logo else ""
    form = HostOnboardingForm(request.POST or None, request.FILES or None, instance=host_profile)
    if request.method == "POST" and form.is_valid():
        host_profile = form.save()
        if old_logo and host_profile.logo.name != old_logo:
            host_profile.logo.storage.delete(old_logo)
        messages.success(request, "Kompaniya ma'lumotlari yangilandi.")
        return redirect("provider-dashboard")
    return render(request, "core/provider_onboarding.html", {"form": form, "is_edit": True})


@login_required
@rate_limited("provider-payments", limit=10, window=900, by="user")
def provider_payments(request):
    """The provider adds the bank card that receives their share of online payments."""
    get_object_or_404(HostProfile, user=request.user)
    account, _ = ProviderPaymentAccount.objects.get_or_create(user=request.user)
    form = ProviderPaymentForm(request.POST or None, account=account, user=request.user)
    if request.method == "POST" and form.is_valid():
        if form.save():
            logger.info("Provider %s changed the payout card; waiting for approval.", request.user.pk)
            transaction.on_commit(lambda: notify_card_review(account))
            messages.success(request, "Karta saqlandi. Bosh admin tekshirib tasdiqlagach, mijozlar onlayn to'lay oladi.")
        else:
            messages.info(request, "O'zgarish yo'q.")
        return redirect("provider-payments")
    payouts = Payout.objects.filter(provider=request.user).select_related("booking", "booking__listing")[:50]
    return render(request, "core/provider_payments.html", {
        "form": form,
        "account": account,
        "payouts": payouts,
        "commission_percent": commission_percent(),
        "pending_total": sum(
            (payout.net_amount for payout in payouts if payout.status in (Payout.Status.HELD, Payout.Status.READY)),
            Decimal("0"),
        ),
    })


@login_required
def provider_dashboard(request):
    host_profile = get_object_or_404(HostProfile, user=request.user)
    listings = RentalListing.objects.filter(owner=request.user).select_related("region", "district").prefetch_related("images")
    query = request.GET.get("q", "").strip()[:100]
    kind = request.GET.get("kind", "")
    status_filter = request.GET.get("status", "")
    booking_status = request.GET.get("booking_status", "")
    if query:
        listings = listings.filter(
            Q(title__icontains=query) | Q(title_ru__icontains=query) | Q(title_en__icontains=query)
            | Q(brand__icontains=query) | Q(address__icontains=query) | Q(city__icontains=query)
        )
    if kind in RentalListing.Kind.values:
        listings = listings.filter(kind=kind)
    if status_filter in RentalListing.AvailabilityStatus.values:
        listings = listings.filter(availability_status=status_filter)
    provider_bookings = active_bookings().filter(
        listing__owner=request.user,
    ).select_related("listing", "user").prefetch_related("listing__images", "installments").order_by("check_out")
    if booking_status in (Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.HANDED_OVER):
        provider_bookings = provider_bookings.filter(status=booking_status)
    if query:
        provider_bookings = provider_bookings.filter(
            Q(listing__title__icontains=query) | Q(user__username__icontains=query) | Q(user__first_name__icontains=query)
        )
    return render(request, "core/provider_dashboard.html", {
        "host_profile": host_profile,
        "listings": listings,
        "listing_total": RentalListing.objects.filter(owner=request.user).count(),
        "provider_bookings": provider_bookings,
        "provider_has_telegram": UserProfile.objects.filter(user=request.user).exists(),
        "rented_listing_ids": set(
            Booking.objects.filter(
                listing__owner=request.user, status=Booking.Status.HANDED_OVER,
            ).values_list("listing_id", flat=True)
        ),
        "filters": {"q": query, "kind": kind, "status": status_filter, "booking_status": booking_status},
        "is_filtered": bool(query or kind or status_filter or booking_status),
        "income": provider_income(request.user, request.GET.get("year")),
        "today": timezone.localdate(),
    })


@login_required
@require_POST
def update_listing_availability(request, listing_id):
    listing = get_object_or_404(RentalListing, pk=listing_id, owner=request.user)
    form = ListingAvailabilityForm(request.POST)
    if form.is_valid():
        listing.availability_status = form.cleaned_data["status"]
        listing.save(update_fields=["availability_status"])
        if listing.availability_status == RentalListing.AvailabilityStatus.REPAIR:
            messages.success(request, "E'lon remontga o'tkazildi va foydalanuvchilardan yashirildi.")
        else:
            messages.success(request, "E'lon holati Faol qilindi.")
    else:
        messages.error(request, "E'lon holatini tanlang.")
    return redirect("provider-dashboard")


@login_required
@require_POST
def update_provider_booking(request, booking_id, action):
    if action not in {"confirm", "handover", "reject", "return"}:
        raise Http404
    with transaction.atomic():
        booking = get_object_or_404(
            Booking.objects.select_for_update().select_related("listing"),
            pk=booking_id,
            listing__owner=request.user,
        )
        if action == "return":
            if booking.status != Booking.Status.HANDED_OVER:
                messages.error(request, "Faqat mijozga topshirilgan mahsulotni qaytarilgan deb belgilash mumkin.")
                return redirect("provider-dashboard")
            late_days, debt = booking.late_days(), booking.current_debt()
            if debt and request.POST.get("debt_paid") != "1":
                messages.error(request, f"Avval kechikish qarzini oling: {late_days} kun, {debt:,.0f} so'm. Keyin \"Qarz to'landi\" belgisini qo'ying.")
                return redirect("provider-dashboard")
            now = timezone.now()
            booking.status = Booking.Status.RETURNED
            booking.returned_at = now
            booking.overdue_days, booking.debt_amount = late_days, debt
            booking.debt_paid_at = now if debt else None
            booking.save(update_fields=["status", "returned_at", "overdue_days", "debt_amount", "debt_paid_at", "updated_at"])
            base_url = request.build_absolute_uri("/").rstrip("/")
            transaction.on_commit(lambda: notify_booking_parties(booking.pk, "returned", base_url))
            messages.success(request, "Mahsulot qaytarildi." + (f" Qarz {debt:,.0f} so'm to'langan deb yozildi." if debt else ""))
            return redirect("provider-dashboard")
        if booking.check_out <= timezone.localdate():
            messages.error(request, "Ijara muddati tugagan bronni o'zgartirib bo'lmaydi.")
            return redirect("provider-dashboard")
        if action == "confirm" and booking.status == Booking.Status.PENDING:
            booking.status = Booking.Status.CONFIRMED
            event = "confirmed"
        elif action == "handover" and booking.status == Booking.Status.CONFIRMED:
            booking.status = Booking.Status.HANDED_OVER
            booking.handed_over_at = timezone.now()
            event = "handed_over"
            transaction.on_commit(lambda: release_payout(booking))
        elif action == "reject" and booking.status in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
            booking.status = Booking.Status.CANCELLED
            event = "rejected"
            transaction.on_commit(lambda: refund_for_cancelled(booking))
        else:
            messages.error(request, "Bu bron uchun amalni bajarib bo'lmaydi.")
            return redirect("provider-dashboard")
        booking.save(update_fields=["status", "handed_over_at", "updated_at"])
        base_url = request.build_absolute_uri("/").rstrip("/")
        transaction.on_commit(lambda: notify_booking_parties(booking.pk, event, base_url))
    messages.success(request, {
        "confirm": "Bron tasdiqlandi.",
        "handover": "Mahsulot ijaraga topshirildi.",
        "reject": "Bron so'rovi rad etildi.",
    }[action])
    return redirect("provider-dashboard")


def _save_listing_form(form, owner=None):
    images = form.cleaned_data.get("image_uploads") or []
    removed = form.cleaned_data.get("remove_images") or []
    listing = form.save(commit=False)
    if form.is_edit and translation_enabled():
        # Re-translate copy whose Uzbek source changed, unless the provider edited that translation too.
        for source, targets in (("title", ("title_ru", "title_en")), ("description", ("description_ru", "description_en"))):
            if source in form.changed_data:
                for target in targets:
                    if target not in form.changed_data:
                        setattr(listing, target, "")
    if owner is not None:
        listing.owner = owner
        listing.is_active = True
    listing.full_clean()
    with transaction.atomic():
        listing.save()
        for image in removed:
            image.image.delete(save=False)
            image.delete()
        for image in images:
            ListingImage.objects.create(listing=listing, image=image)
    translate_listing(listing)
    return listing


@login_required
def create_listing(request):
    host_profile = get_object_or_404(HostProfile, user=request.user)
    kind = request.POST.get("kind") or request.GET.get("kind")
    if kind not in RentalListing.Kind.values:
        # Step 1: the provider picks "home" or "car" before seeing any fields.
        return render(request, "core/provider_listing_form.html", {
            "form": None, "host_profile": host_profile, "kind_choices": RentalListing.Kind.choices,
        })
    if request.method == "POST":
        form = RentalListingForm(request.POST, request.FILES, kind=kind, auto_translate=translation_enabled())
        if form.is_valid():
            _save_listing_form(form, owner=request.user)
            messages.success(request, "E'loningiz yaratildi.")
            return redirect("provider-dashboard")
    else:
        form = RentalListingForm(kind=kind, auto_translate=translation_enabled())
    return render(request, "core/provider_listing_form.html", {
        "form": form,
        "host_profile": host_profile,
    })


@login_required
def edit_listing(request, listing_id):
    host_profile = get_object_or_404(HostProfile, user=request.user)
    listing = get_object_or_404(
        RentalListing.objects.prefetch_related("images"), pk=listing_id, owner=request.user,
    )
    form = RentalListingForm(
        request.POST or None, request.FILES or None, instance=listing, auto_translate=translation_enabled(),
    )
    if request.method == "POST" and form.is_valid():
        _save_listing_form(form)
        messages.success(request, "E'lon yangilandi.")
        return redirect("provider-dashboard")
    return render(request, "core/provider_listing_form.html", {
        "form": form,
        "host_profile": host_profile,
        "listing": listing,
    })


def contact_admin(request):
    if request.user.is_authenticated:
        return redirect("chat-room", conversation_id=support_conversation_for(request.user).pk)
    form = ContactMessageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Xabaringiz administratorlarga yuborildi.")
        return redirect("contact-admin")
    return render(request, "core/contact.html", {"form": form})


@login_required
@require_POST
def start_chat(request, slug):
    listing = get_object_or_404(RentalListing, slug=slug, is_active=True, owner__isnull=False)
    if listing.owner_id == request.user.pk:
        messages.error(request, "O'zingiz bilan chat boshlay olmaysiz.")
        return redirect("listing-detail", slug=slug)
    if not can_view_listing(request.user, listing):
        raise Http404
    conversation, _ = Conversation.objects.get_or_create(
        listing=listing,
        customer=request.user,
        defaults={"provider_id": listing.owner_id, "kind": Conversation.Kind.LISTING},
    )
    return redirect("chat-room", conversation_id=conversation.pk)


@login_required
@require_POST
def start_booking_chat(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("listing", "user"),
        pk=booking_id,
        listing__owner=request.user,
    )
    conversation, _ = Conversation.objects.get_or_create(
        listing=booking.listing,
        customer=booking.user,
        defaults={"provider": request.user},
    )
    return redirect("chat-room", conversation_id=conversation.pk)


@login_required
def chat_inbox(request):
    conversations = list(conversations_for(request.user))
    return render(request, "core/chat_inbox.html", {
        "conversations": conversations,
        "unread_total": sum(conversation.unread_count for conversation in conversations),
    })


def _conversation_for_user(user, conversation_id):
    conversation = get_object_or_404(
        Conversation.objects.select_related("listing", "customer", "provider"), pk=conversation_id,
    )
    if not conversation.is_participant(user):
        raise Http404
    return conversation


@login_required
@rate_limited("chat-send", limit=40, window=60, by="user")
def chat_room(request, conversation_id):
    conversation = _conversation_for_user(request.user, conversation_id)
    wants_json = request.headers.get("Accept", "").startswith("application/json")
    if request.method == "POST":
        form = ChatMessageForm(request.POST, request.FILES)
        if form.is_valid():
            message = post_message(
                conversation, request.user, text=form.cleaned_data["text"],
                attachment=form.cleaned_data.get("attachment"),
                attachment_type=form.cleaned_data.get("attachment_type", ""),
            )
            if wants_json:
                return JsonResponse({"message": serialize_message(
                    message, request.user, other_side_last_read(conversation, request.user),
                )}, status=201)
            return redirect("chat-room", conversation_id=conversation.pk)
        if wants_json:
            errors = [error for field_errors in form.errors.values() for error in field_errors]
            return JsonResponse({"detail": " ".join(errors)}, status=400)
    else:
        form = ChatMessageForm()
    chat_messages = list(
        conversation.messages.select_related("sender", "conversation").order_by("-created_at", "-pk")[:200]
    )
    chat_messages.reverse()
    latest_message_id = chat_messages[-1].pk if chat_messages else 0
    mark_read(conversation, request.user, latest_message_id)
    other_read = other_side_last_read(conversation, request.user)
    return render(request, "core/chat_room.html", {
        "conversation": conversation,
        "chat_messages": [serialize_message(message, request.user, other_read) for message in chat_messages],
        "latest_chat_message_id": latest_message_id,
        "form": form,
    })


@login_required
@require_GET
def chat_messages_api(request, conversation_id):
    conversation = _conversation_for_user(request.user, conversation_id)
    try:
        after = max(0, int(request.GET.get("after", "0")))
    except (TypeError, ValueError):
        return JsonResponse({"detail": "after musbat butun son bo'lishi kerak."}, status=400)
    messages_qs = list(
        conversation.messages.filter(pk__gt=after).select_related("sender", "conversation").order_by("created_at", "pk")[:100]
    )
    if messages_qs:
        mark_read(conversation, request.user, max(message.pk for message in messages_qs))
    other_read = other_side_last_read(conversation, request.user)
    return JsonResponse({
        "messages": [serialize_message(message, request.user, other_read) for message in messages_qs],
        "other_last_read_id": other_read,
    })


@login_required
@require_GET
def chat_unread_status(request):
    count = unread_messages(request.user).count()
    return JsonResponse({"has_unread": bool(count), "count": count})


@login_required
@require_GET
def chat_media(request, message_id):
    message = get_object_or_404(ChatMessage.objects.select_related("conversation"), pk=message_id)
    if not (message.conversation.is_participant(request.user) or request.user.is_staff) or not message.attachment:
        raise Http404
    return serve_private_file(request, message.attachment)


@require_GET
def districts_api(request):
    try:
        region_id = int(request.GET.get("region_id", ""))
    except (TypeError, ValueError):
        return JsonResponse({"detail": "region_id musbat butun son bo'lishi kerak."}, status=400)
    districts = District.objects.filter(region_id=region_id).order_by("name_uz")
    return JsonResponse({
        "results": [
            {"id": district.pk, "name": district.name_uz, "region_id": district.region_id}
            for district in districts
        ],
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
def pay_installment(request, installment_id):
    """Pay the next part of an instalment plan online (Click / Payme)."""
    installment = get_object_or_404(
        Installment.objects.select_related("booking"), pk=installment_id, booking__user=request.user,
    )
    booking = installment.booking
    if (
        installment.status != Installment.Status.PENDING
        or booking.payment_method not in (Booking.PaymentMethod.CLICK, Booking.PaymentMethod.PAYME)
        or booking.status in (Booking.Status.CANCELLED, Booking.Status.RETURNED)
    ):
        messages.error(request, "Bu to'lovni onlayn to'lab bo'lmaydi.")
        return redirect("my-bookings")
    if next_unpaid(booking).pk != installment.pk:
        messages.error(request, "Avval oldingi to'lovni to'lang.")
        return redirect("my-bookings")
    try:
        return redirect(installment_payment_url(installment, request))
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("my-bookings")


@login_required
@require_POST
def provider_installment_paid(request, installment_id):
    """The provider received a cash part of an instalment plan."""
    with transaction.atomic():
        installment = get_object_or_404(
            Installment.objects.select_for_update().select_related("booking"),
            pk=installment_id, booking__listing__owner=request.user,
        )
        booking = installment.booking
        if booking.payment_method != Booking.PaymentMethod.CASH or installment.status != Installment.Status.PENDING:
            messages.error(request, "Bu to'lovni belgilab bo'lmaydi.")
            return redirect("provider-dashboard")
        mark_installment_paid(installment, Booking.PaymentMethod.CASH)
        base_url = request.build_absolute_uri("/").rstrip("/")
        transaction.on_commit(lambda: notify_installment_paid(installment.pk, base_url))
    messages.success(request, f"{installment.number}-to'lov ({installment.amount:,.0f} so'm) qabul qilindi.".replace(",", " "))
    return redirect("provider-dashboard")


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
        transaction.on_commit(lambda: refund_for_cancelled(booking))
        transaction.on_commit(lambda: notify_booking_parties(
            booking.pk, "cancelled", request.build_absolute_uri("/").rstrip("/"),
        ))
        messages.success(request, f"#{booking.pk} bron bekor qilindi.")
    else:
        messages.info(request, "Bu bron avval bekor qilingan.")
    return redirect("my-bookings")


@require_GET
def health(request):
    return JsonResponse({"status": "ok", "app": "Rentora", "time": timezone.now().isoformat()})


@require_POST
@rate_limited("ai-search", limit=20, window=600)
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
    language = payload.get("language", "uz")
    if language not in {"uz", "ru", "en"}:
        language = "uz"
    try:
        result = find_rentals(message, user=request.user, language=language)
    except RentalAssistantError as exc:
        return JsonResponse({"detail": str(exc)}, status=exc.status_code)
    return JsonResponse(result)


@api_view(["GET"])
@permission_classes([AllowAny])
def listings_api(request):
    listings = listings_visible_to(
        request.user,
        RentalListing.objects.select_related("region", "district").prefetch_related("images"),
    )
    kind = request.query_params.get("kind")
    city = request.query_params.get("city", "").strip()
    query = request.query_params.get("q", "").strip()
    if kind in (RentalListing.Kind.HOME, RentalListing.Kind.CAR):
        listings = listings.filter(kind=kind)
    if city:
        listings = listings.filter(city__icontains=city)
    try:
        region_id = int(request.query_params.get("region", ""))
    except (TypeError, ValueError):
        region_id = None
    try:
        district_id = int(request.query_params.get("district", ""))
    except (TypeError, ValueError):
        district_id = None
    if region_id:
        listings = listings.filter(region_id=region_id)
    if district_id:
        listings = listings.filter(district_id=district_id)
    if query:
        listings = listings.filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(brand__icontains=query))
    check_in = _parse_date(request.query_params.get("check_in", ""))
    check_out = _parse_date(request.query_params.get("check_out", ""))
    listings = _available_for_dates(listings, check_in, check_out)
    return Response(ListingSerializer(listings, many=True).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def listing_detail_api(request, listing_id):
    listing = get_object_or_404(RentalListing.objects.select_related("region", "district").prefetch_related("images"), pk=listing_id)
    if not can_view_listing(request.user, listing):
        return Response({"detail": "E'lon topilmadi."}, status=status.HTTP_404_NOT_FOUND)
    return Response(ListingSerializer(listing).data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def bookings_api(request):
    if request.method == "GET":
        bookings = Booking.objects.filter(user=request.user).select_related("listing").prefetch_related("listing__images", "installments")
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
    if booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
        return Response({"detail": "Bron avval bekor qilingan."}, status=status.HTTP_400_BAD_REQUEST)
    booking.status = Booking.Status.CANCELLED
    booking.save(update_fields=["status", "updated_at"])
    transaction.on_commit(lambda: refund_for_cancelled(booking))
    transaction.on_commit(lambda: notify_booking_parties(booking.pk, "cancelled"))
    return Response(BookingSerializer(booking).data)
