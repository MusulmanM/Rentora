from datetime import date
from datetime import timedelta
import json
import logging
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .forms import (
    BookingForm, ContactMessageForm, HostOnboardingForm, PhoneNumberForm, RegistrationForm,
    RegistrationOTPForm, RentalListingForm, homeForm, carForm, normalize_phone_number,
)
from .models import (
    Booking, BookingOrder, District, HostProfile, PendingRegistration,
    PendingPhoneVerification, Region, RentalListing, ListingImage, TelegramAccount,
    UserProfile, home, car,
)
from .payments import payment_url
from .serializers import BookingSerializer, ListingSerializer, homeSerializer, carSerializer
from .ai_assistant import RentalAssistantError, find_rentals
from .telegram import TelegramError, request_contact, send_message


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


def _otp_rate_limited(account, now):
    return bool(account.last_otp_sent_at and now - account.last_otp_sent_at < OTP_RESEND_INTERVAL)


def _record_otp_delivery(account, now):
    account.last_otp_sent_at = now
    account.save(update_fields=["last_otp_sent_at"])


def home(request):
    listings = RentalListing.objects.filter(is_active=True).select_related("region", "district").prefetch_related("images")
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

    context = {
        "listings": listings,
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
                            send_message(
                                telegram_account.chat_id,
                                f"Rentora ro'yxatdan o'tish kodi: {code}\nKod 10 daqiqa amal qiladi.",
                            )
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
        send_message(
            pending.telegram_account.chat_id,
            f"Rentora ro'yxatdan o'tish kodi: {code}\nKod 10 daqiqa amal qiladi.",
        )
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
                send_message(account.chat_id, f"Rentora telefon tasdiqlash kodi: {code}\nKod 10 daqiqa amal qiladi.")
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
        send_message(pending.telegram_account.chat_id, f"Rentora telefon tasdiqlash kodi: {code}\nKod 10 daqiqa amal qiladi.")
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
    message = update.get("message")
    if not isinstance(message, dict):
        return JsonResponse({"ok": True})
    sender = message.get("from") or {}
    chat = message.get("chat") or {}
    telegram_user_id = sender.get("id")
    chat_id = chat.get("id")
    if not telegram_user_id or not chat_id or chat.get("type") != "private" or str(chat_id) != str(telegram_user_id):
        return JsonResponse({"ok": True})

    contact = message.get("contact")
    if isinstance(contact, dict):
        if str(contact.get("user_id", "")) != str(telegram_user_id):
            return JsonResponse({"ok": True})
        try:
            phone_number = normalize_phone_number(contact.get("phone_number", ""))
        except ValidationError:
            try:
                send_message(str(chat_id), "Faqat O'zbekiston telefon raqami bilan ro'yxatdan o'tish mumkin.")
            except TelegramError:
                logger.warning("Telegram could not send a contact validation message.")
            return JsonResponse({"ok": True})
        try:
            account, _ = TelegramAccount.objects.get_or_create(
                phone_number=phone_number,
                defaults={"telegram_user_id": str(telegram_user_id), "chat_id": str(chat_id)},
            )
        except IntegrityError:
            account = TelegramAccount.objects.filter(phone_number=phone_number).first()
        if account and (
            account.telegram_user_id == str(telegram_user_id)
            and account.chat_id == str(chat_id)
        ):
            response_text = "Telefon raqamingiz bog'landi. Endi Rentora saytida ro'yxatdan o'tishingiz mumkin."
        else:
            response_text = "Bu Telegram hisobi yoki telefon raqami boshqa akkauntga bog'langan."
        try:
            send_message(str(chat_id), response_text)
        except TelegramError:
            logger.warning("Telegram could not send the contact-link confirmation.")
        return JsonResponse({"ok": True})

    if str(message.get("text", "")).split(maxsplit=1)[0:1] == ["/start"]:
        try:
            request_contact(str(chat_id))
        except TelegramError:
            logger.warning("Telegram could not send the contact request prompt.")
    return JsonResponse({"ok": True})


def listing_detail(request, slug):
    listing = get_object_or_404(
        RentalListing.objects.select_related("region", "district").prefetch_related("images"),
        slug=slug, is_active=True,
    )
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
def user_profile(request):
    profile = UserProfile.objects.filter(user=request.user).select_related("telegram_account").first()
    host_profile = HostProfile.objects.filter(user=request.user).first()
    listings = RentalListing.objects.filter(owner=request.user).order_by("-created_at") if host_profile else ()
    return render(request, "core/profile.html", {
        "profile": profile,
        "host_profile": host_profile,
        "listings": listings,
    })


@login_required
def provider_onboarding(request):
    if not UserProfile.objects.filter(user=request.user).exists():
        messages.error(request, "Ijara beruvchi bo'lish uchun telefon raqamingizni Telegram orqali tasdiqlang.")
        return redirect("profile")
    existing = HostProfile.objects.filter(user=request.user).first()
    if existing:
        return redirect("provider-dashboard")
    form = HostOnboardingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        host_profile = form.save(commit=False)
        host_profile.user = request.user
        host_profile.save()
        messages.success(request, "Ijara beruvchi profilingiz yaratildi. E'lon qo'shishingiz mumkin.")
        return redirect("provider-dashboard")
    return render(request, "core/provider_onboarding.html", {"form": form})


@login_required
def provider_dashboard(request):
    host_profile = get_object_or_404(HostProfile, user=request.user)
    listings = RentalListing.objects.filter(owner=request.user).select_related("region", "district").prefetch_related("images")
    return render(request, "core/provider_dashboard.html", {
        "host_profile": host_profile,
        "listings": listings,
    })


@login_required
def create_listing(request):
    host_profile = get_object_or_404(HostProfile, user=request.user)
    if request.method == "POST":
        form = RentalListingForm(request.POST, request.FILES)
        if form.is_valid():
            images = form.cleaned_data["image_uploads"]
            listing = form.save(commit=False)
            listing.owner = request.user
            listing.is_active = True
            listing.full_clean()
            with transaction.atomic():
                listing.save()
                for image in images:
                    ListingImage.objects.create(listing=listing, image=image)
            messages.success(request, "E'loningiz yaratildi.")
            return redirect("provider-dashboard")
    else:
        form = RentalListingForm()
    return render(request, "core/provider_listing_form.html", {
        "form": form,
        "host_profile": host_profile,
    })


def contact_admin(request):
    initial = {}
    if request.user.is_authenticated:
        initial = {"name": request.user.get_full_name(), "email": request.user.email}
    form = ContactMessageForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        contact_message = form.save(commit=False)
        if request.user.is_authenticated:
            contact_message.user = request.user
        contact_message.save()
        messages.success(request, "Xabaringiz administratorlarga yuborildi.")
        return redirect("contact-admin")
    return render(request, "core/contact.html", {"form": form})


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
    listings = RentalListing.objects.filter(is_active=True).select_related("region", "district").prefetch_related("images")
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
    listing = get_object_or_404(
        RentalListing.objects.select_related("region", "district").prefetch_related("images"),
        pk=listing_id, is_active=True,
    )
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