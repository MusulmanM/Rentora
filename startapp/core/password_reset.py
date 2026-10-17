"""Set a new password with a code from the Rentora Telegram bot.

Used when a user forgot their password or the head admin removed it ("Set password" left empty).
The code goes to the Telegram chat linked to the account's verified phone, so only the owner can
finish. The request page never says whether an account exists, and a code allows 5 tries.
"""
import logging
import secrets

from django.contrib import messages
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import PasswordResetCodeForm, PasswordResetRequestForm, normalize_phone_number
from .models import UserProfile
from .security import rate_limited
from .telegram import TelegramError, send_localized

logger = logging.getLogger(__name__)

SESSION_KEY = "password_reset_user_id"
CODE_LIFETIME = 10 * 60
RESEND_INTERVAL = 60
MAX_ATTEMPTS = 5


def _cache_key(user_id):
    return f"password-reset:{user_id}"


def _find_profile(login_value):
    """The account behind a username or a phone number, if it can receive Telegram codes."""
    value = login_value.strip()
    profile = UserProfile.objects.select_related("user", "telegram_account").filter(user__username=value).first()
    if profile is None:
        try:
            phone = normalize_phone_number(value)
        except ValidationError:  # not a phone number either
            phone = ""
        if phone:
            profile = UserProfile.objects.select_related("user", "telegram_account").filter(phone_number=phone).first()
    if profile is None or not profile.telegram_account_id or not profile.user.is_active:
        return None
    if getattr(getattr(profile.user, "account", None), "is_guest", False):
        return None
    return profile


@rate_limited("password-reset", limit=6, window=3600)
def password_reset_request(request):
    form = PasswordResetRequestForm(request.POST or None, initial={"login": request.GET.get("username", "")})
    if request.method == "POST" and form.is_valid():
        profile = _find_profile(form.cleaned_data["login"])
        request.session[SESSION_KEY] = profile.user_id if profile else 0
        if profile:
            account = profile.telegram_account
            now = timezone.now()
            if account.last_otp_sent_at and (now - account.last_otp_sent_at).total_seconds() < RESEND_INTERVAL:
                messages.info(request, "Kod yaqinda yuborilgan. Yangisini 60 soniyadan keyin so'rashingiz mumkin.")
                return redirect("password-reset-verify")
            code = f"{secrets.randbelow(1_000_000):06d}"
            try:
                send_localized(account.chat_id, "password_code", code=code)
            except TelegramError:
                logger.warning("Password reset code could not be sent to user %s.", profile.user_id)
            else:
                cache.set(_cache_key(profile.user_id), {"hash": make_password(code), "attempts": 0}, CODE_LIFETIME)
                account.last_otp_sent_at = now
                account.save(update_fields=["last_otp_sent_at"])
        # Same answer whether or not the account exists, so nobody can probe usernames or phones.
        messages.success(request, "Akkaunt topilsa, tasdiqlash kodi Rentora Telegram botiga yuborildi.")
        return redirect("password-reset-verify")
    return render(request, "core/password_reset.html", {"form": form, "step": "request"})


@rate_limited("password-reset-verify", limit=20, window=900)
def password_reset_verify(request):
    if SESSION_KEY not in request.session:
        return redirect("password-reset")
    user_id = request.session.get(SESSION_KEY) or 0
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first() if user_id else None
    form = PasswordResetCodeForm(user or get_user_model()(), request.POST or None)
    if request.method == "POST" and form.is_valid():
        entry = cache.get(_cache_key(user_id)) if user else None
        if entry is None:
            form.add_error("code", "Kod noto'g'ri yoki muddati tugagan. Yangi kod so'rang.")
        else:
            entry["attempts"] += 1
            if not check_password(form.cleaned_data["code"], entry["hash"]):
                if entry["attempts"] >= MAX_ATTEMPTS:
                    cache.delete(_cache_key(user_id))
                    form.add_error("code", "Urinishlar tugadi. Yangi kod so'rang.")
                else:
                    cache.set(_cache_key(user_id), entry, CODE_LIFETIME)
                    form.add_error("code", f"Kod noto'g'ri. Yana {MAX_ATTEMPTS - entry['attempts']} marta urinish mumkin.")
            else:
                cache.delete(_cache_key(user_id))
                form.save()
                request.session.pop(SESSION_KEY, None)
                _notify_password_changed(user)
                messages.success(request, "Yangi parol o'rnatildi. Endi yangi parol bilan kiring.")
                return redirect(f"{reverse('login')}?{urlencode({'username': user.get_username()})}")
    return render(request, "core/password_reset.html", {"form": form, "step": "verify"})


def _notify_password_changed(user):
    profile = UserProfile.objects.select_related("telegram_account").filter(user=user).first()
    if not profile or not profile.telegram_account_id:
        return
    try:
        send_localized(profile.telegram_account.chat_id, "password_changed")
    except TelegramError:
        logger.warning("Password change notice could not be sent to user %s.", user.pk)
