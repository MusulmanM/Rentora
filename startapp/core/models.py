from decimal import Decimal
import secrets
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone
from django.utils.deconstruct import deconstructible
from django.utils.text import slugify

from .uploads import SAFE_CHAT_EXTENSIONS, randomized_upload_path


@deconstructible
class ChatMediaStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=settings.CHAT_MEDIA_ROOT)


chat_media_storage = ChatMediaStorage()


class Region(models.Model):
    code = models.PositiveSmallIntegerField(primary_key=True)
    name_uz = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)
    name_ru = models.CharField(max_length=100)

    class Meta:
        ordering = ["name_uz"]
        verbose_name = "Viloyat"
        verbose_name_plural = "Viloyatlar"

    def __str__(self):
        return self.name_uz


class District(models.Model):
    code = models.PositiveSmallIntegerField(primary_key=True)
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="districts")
    name_uz = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)
    name_ru = models.CharField(max_length=100)

    class Meta:
        ordering = ["name_uz"]
        verbose_name = "Shahar / tuman"
        verbose_name_plural = "Shaharlar va tumanlar"
        indexes = [models.Index(fields=["region", "name_uz"], name="core_district_region_name_idx")]

    def __str__(self):
        return f"{self.name_uz} — {self.region.name_uz}"


class TelegramAccount(models.Model):
    phone_number = models.CharField(max_length=16, unique=True)
    telegram_user_id = models.CharField(max_length=32, unique=True)
    chat_id = models.CharField(max_length=32, unique=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    last_otp_sent_at = models.DateTimeField(null=True, blank=True)
    linked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Telegram hisobi"
        verbose_name_plural = "Telegram hisoblari"

    def __str__(self):
        return self.phone_number



class TelegramChatLanguage(models.Model):
    """The language a Telegram chat chose in the Rentora bot (also before a phone is linked)."""

    class Language(models.TextChoices):
        UZ = "uz", "O'zbekcha"
        RU = "ru", "Русский"
        EN = "en", "English"

    chat_id = models.CharField(max_length=32, unique=True)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.UZ)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Telegram tili"
        verbose_name_plural = "Telegram tillari"

    def __str__(self):
        return f"{self.chat_id} — {self.language}"


def chat_language(chat_id):
    """The bot language of a chat; Uzbek until the user picks one."""
    row = TelegramChatLanguage.objects.filter(chat_id=str(chat_id)).values_list("language", flat=True).first()
    return row or TelegramChatLanguage.Language.UZ

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    phone_number = models.CharField(max_length=16, unique=True)
    telegram_account = models.OneToOneField(
        TelegramAccount, on_delete=models.PROTECT, related_name="profile",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Foydalanuvchi profili"
        verbose_name_plural = "Foydalanuvchi profillari"

    def __str__(self):
        return f"{self.user} — {self.phone_number}"


class PendingRegistration(models.Model):
    username = models.CharField(max_length=150)
    first_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone_number = models.CharField(max_length=16)
    password_hash = models.CharField(max_length=128)
    telegram_account = models.OneToOneField(TelegramAccount, on_delete=models.CASCADE)
    otp_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["phone_number", "expires_at"], name="core_pending_phone_exp_idx")]


class PendingPhoneVerification(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pending_phone_verification")
    phone_number = models.CharField(max_length=16, unique=True)
    telegram_account = models.ForeignKey(TelegramAccount, on_delete=models.CASCADE)
    otp_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)


class UserAccount(models.Model):
    """Public identity for every user: a stable UID and an optional avatar."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="account")
    uid = models.UUIDField("UID", default=uuid.uuid4, unique=True, editable=False)
    avatar = models.ImageField("Rasm", upload_to=randomized_upload_path("avatars"), blank=True)
    # A visitor without an account who writes to the admin team from the login / sign-up pages.
    # Guests are inactive users: they can never sign in, they only own their support chat.
    is_guest = models.BooleanField("Mehmon", default=False)
    guest_phone = models.CharField("Mehmon telefoni", max_length=16, blank=True)

    class Meta:
        verbose_name = "Foydalanuvchi hisobi"
        verbose_name_plural = "Foydalanuvchi hisoblari"

    def __str__(self):
        return f"{self.user} — {self.uid}"


def account_for(user):
    account, _ = UserAccount.objects.get_or_create(user=user)
    return account


class HostProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="host_profile")
    display_name = models.CharField("Kompaniya nomi", max_length=120)
    logo = models.ImageField("Kompaniya logotipi", upload_to=randomized_upload_path("host-logos"), blank=True)
    phone_number = models.CharField("Kompaniya telefoni", max_length=16, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_complete(self):
        return bool(self.display_name and self.logo and self.phone_number)

    class Meta:
        verbose_name = "Ijara beruvchi"
        verbose_name_plural = "Ijara beruvchilar"

    def __str__(self):
        return self.display_name


def _callback_token():
    """Used by migration 0018 (per-provider merchants, since replaced by payout cards)."""
    return secrets.token_urlsafe(24)


class ProviderPaymentAccount(models.Model):
    """Where a provider receives money: just their own bank card (Uzcard / Humo).

    Customers pay Rentora's single Click / Payme merchant; after the hand-over Rentora pays the provider
    (minus commission) to this card. The card number is stored encrypted (core.secret_box) and is shown
    masked everywhere except to the head admin who sends the payout. A new card takes effect only after
    the head admin approves it, so a hijacked account cannot silently redirect payouts.
    """

    class CardBrand(models.TextChoices):
        UZCARD = "uzcard", "Uzcard"
        HUMO = "humo", "Humo"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payment_account")
    card_number_encrypted = models.TextField(blank=True, editable=False)
    card_last4 = models.CharField("Karta (oxirgi 4 raqam)", max_length=4, blank=True)
    card_brand = models.CharField("Karta turi", max_length=10, choices=CardBrand.choices, blank=True)
    card_holder = models.CharField("Karta egasi", max_length=80, blank=True)
    offer_accepted_at = models.DateTimeField("Oferta qabul qilingan", null=True, blank=True)
    approved = models.BooleanField("Bosh admin tasdiqlagan", default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "To'lov kartasi (ijara beruvchi)"
        verbose_name_plural = "To'lov kartalari (ijara beruvchilar)"

    def __str__(self):
        return f"{self.user.get_username()} — {self.masked_card or 'karta yo‘q'}"

    @property
    def card_number(self):
        from .secret_box import decrypt
        return decrypt(self.card_number_encrypted)

    @card_number.setter
    def card_number(self, value):
        from .secret_box import encrypt
        self.card_number_encrypted = encrypt(value)
        self.card_last4 = value[-4:] if value else ""

    @property
    def masked_card(self):
        return f"•••• •••• •••• {self.card_last4}" if self.card_last4 else ""

    @property
    def has_card(self):
        return bool(self.card_number_encrypted and self.card_last4)

    @property
    def can_receive_payouts(self):
        return self.approved and self.has_card and self.offer_accepted_at is not None


class ContactMessage(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="contact_messages",
        null=True, blank=True,
    )
    name = models.CharField("Ism", max_length=120)
    email = models.EmailField("Elektron pochta", blank=True)
    subject = models.CharField("Mavzu", max_length=160)
    message = models.TextField("Xabar", max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField("Ko'rildi", default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bog'lanish xabari"
        verbose_name_plural = "Bog'lanish xabarlari"

    def __str__(self):
        return f"{self.subject} — {self.name}"


class RentalListing(models.Model):
    class Kind(models.TextChoices):
        HOME = "home", "Uylar"
        CAR = "car", "Avtomobillar"

    class Transmission(models.TextChoices):
        AUTOMATIC = "automatic", "Avtomat"
        MANUAL = "manual", "Mexanika"
        NOT_APPLICABLE = "na", "Ko'rsatilmagan"

    class AvailabilityStatus(models.TextChoices):
        ACTIVE = "active", "Faol"
        REPAIR = "repair", "Remont"

    kind = models.CharField("Turi", max_length=10, choices=Kind.choices)
    title = models.CharField("Nomi (UZ)", max_length=160)
    title_ru = models.CharField("Название (RU)", max_length=160, blank=True)
    title_en = models.CharField("Title (EN)", max_length=160, blank=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    city = models.CharField("Shahar", max_length=80)
    region = models.ForeignKey(
        Region, on_delete=models.PROTECT, related_name="listings", null=True, blank=True,
    )
    district = models.ForeignKey(
        District, on_delete=models.PROTECT, related_name="listings", null=True, blank=True,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="owned_listings",
        null=True, blank=True,
    )
    address = models.CharField("Manzil", max_length=220)
    description = models.TextField("Tavsif (UZ)")
    description_ru = models.TextField("Описание (RU)", blank=True)
    description_en = models.TextField("Description (EN)", blank=True)
    price_per_day = models.DecimalField("Kunlik narx (so'm)", max_digits=12, decimal_places=2)
    # Homes can also be rented by the month; empty means daily rental only.
    price_per_month = models.DecimalField("Oylik narx (so'm)", max_digits=14, decimal_places=2, null=True, blank=True)
    legacy_image_url = models.URLField("Eski rasm URL", max_length=600, blank=True, db_column="image_url")
    capacity = models.PositiveSmallIntegerField("Sig'im", default=2, help_text="Uy uchun mehmonlar, mashina uchun o'rindiqlar.")
    bedrooms = models.PositiveSmallIntegerField("Yotoq xonalari", blank=True, null=True)
    bathrooms = models.PositiveSmallIntegerField("Hammomlar", blank=True, null=True)
    brand = models.CharField("Marka", max_length=80, blank=True)
    transmission = models.CharField("Uzatmalar qutisi", max_length=12, choices=Transmission.choices, default=Transmission.NOT_APPLICABLE)
    year = models.PositiveSmallIntegerField("Ishlab chiqarilgan yil", blank=True, null=True)
    is_featured = models.BooleanField("Tavsiya etilgan", default=False)
    is_active = models.BooleanField("Faol", default=True)
    availability_status = models.CharField(
        "Ijara holati", max_length=10, choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_featured", "-created_at"]
        verbose_name = "Ijara e'loni"
        verbose_name_plural = "Ijara e'lonlari"
        indexes = [models.Index(fields=["kind", "city", "is_active"], name="core_rent_kind_city_active_idx")]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "ijara"
            slug = base_slug
            number = 2
            while RentalListing.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{number}"
                number += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def clean(self):
        if self.district_id and not self.region_id:
            raise ValidationError({"region": "Shahar yoki tuman tanlanganda viloyat ham tanlanishi kerak."})
        if self.region_id and self.district_id and self.district.region_id != self.region_id:
            raise ValidationError({"district": "Tanlangan shahar yoki tuman viloyatga mos kelmaydi."})

    @property
    def is_home(self):
        return self.kind == self.Kind.HOME

    @property
    def is_car(self):
        return self.kind == self.Kind.CAR

    @property
    def kind_label(self):
        return self.get_kind_display()

    @property
    def primary_image_url(self):
        image = next(iter(self.images.all()), None)
        return image.image.url if image else self.legacy_image_url

    @property
    def image_url(self):
        return self.primary_image_url

    @property
    def card_image_url(self):
        """A light WebP thumbnail for listing cards; the full photo if no thumbnail exists yet."""
        from .thumbnails import thumbnail_url

        image = next(iter(self.images.all()), None)
        return thumbnail_url(image.image) if image else self.legacy_image_url

    def __str__(self):
        return f"{self.title} — {self.city}"


class ListingImage(models.Model):
    listing = models.ForeignKey(RentalListing, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField("Rasm", upload_to=randomized_upload_path("listing-images"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "E'lon rasmi"
        verbose_name_plural = "E'lon rasmlari"

    def __str__(self):
        return f"{self.listing.title} — rasm {self.pk or 'yangi'}"


class ListingReview(models.Model):
    listing = models.ForeignKey(RentalListing, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="listing_reviews")
    rating = models.PositiveSmallIntegerField("Baho", validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField("Izoh", max_length=2000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Izoh va baho"
        verbose_name_plural = "Izohlar va baholar"
        constraints = [
            models.UniqueConstraint(fields=["listing", "user"], name="core_review_listing_user_uniq"),
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="core_review_rating_range"),
        ]

    def __str__(self):
        return f"{self.listing.title} — {self.rating}/5"


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        CONFIRMED = "confirmed", "Tasdiqlangan"
        HANDED_OVER = "handed_over", "Mijozga topshirilgan"
        RETURNED = "returned", "Qaytarilgan"
        CANCELLED = "cancelled", "Bekor qilingan"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Naqd"
        CLICK = "click", "Click"
        PAYME = "payme", "Payme"

    class RentalUnit(models.TextChoices):
        DAY = "day", "Kunlik"
        MONTH = "month", "Oylik"

    class PaymentPlan(models.TextChoices):
        FULL = "full", "To'liq"
        MONTHLY = "monthly", "Har oy"
        BIWEEKLY = "biweekly", "Har 15 kunda"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings", verbose_name="Foydalanuvchi")
    listing = models.ForeignKey(RentalListing, on_delete=models.PROTECT, related_name="bookings", verbose_name="E'lon")
    check_in = models.DateField("Boshlanish sanasi")
    check_out = models.DateField("Tugash sanasi")
    guests = models.PositiveSmallIntegerField("Mehmonlar / yo'lovchilar", default=1)
    payment_method = models.CharField("To'lov turi", max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    rental_unit = models.CharField("Ijara turi", max_length=5, choices=RentalUnit.choices, default=RentalUnit.DAY)
    months = models.PositiveSmallIntegerField("Oylar soni", null=True, blank=True)
    payment_plan = models.CharField("To'lov rejasi", max_length=8, choices=PaymentPlan.choices, default=PaymentPlan.FULL)
    total_price = models.DecimalField("Jami narx (so'm)", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField("Holati", max_length=12, choices=Status.choices, default=Status.PENDING)
    requested_at = models.DateTimeField("Bron so'rovi vaqti", default=timezone.now)
    handed_over_at = models.DateTimeField("Topshirilgan vaqt", null=True, blank=True)
    returned_at = models.DateTimeField("Qaytarilgan vaqt", null=True, blank=True)
    # Late return: every day past check_out costs one more day of rent, paid when the item comes back.
    overdue_days = models.PositiveIntegerField("Kechikkan kunlar", default=0)
    debt_amount = models.DecimalField("Kechikish qarzi (so'm)", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    debt_paid_at = models.DateTimeField("Qarz to'langan vaqt", null=True, blank=True)
    end_notice_sent_on = models.DateField(null=True, blank=True, editable=False)
    overdue_notice_sent_on = models.DateField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bron"
        verbose_name_plural = "Bronlar"
        indexes = [models.Index(fields=["listing", "check_in", "check_out", "status"], name="core_book_listing_dates_idx")]

    @property
    def days(self):
        return max((self.check_out - self.check_in).days, 0)

    @property
    def daily_rate(self):
        """The agreed price of one day (the listing price may change later)."""
        if self.days and self.total_price:
            return (self.total_price / self.days).quantize(Decimal("0.01"))
        return self.listing.price_per_day

    def late_days(self, on=None):
        """Days past check_out while the item is still with the customer."""
        if self.status != self.Status.HANDED_OVER:
            return 0
        return max(((on or timezone.localdate()) - self.check_out).days, 0)

    def current_debt(self, on=None):
        return self.daily_rate * self.late_days(on)

    @property
    def is_overdue(self):
        return self.late_days() > 0

    def clean(self):
        errors = {}
        if self.listing_id and self.user_id and self.listing.owner_id == self.user_id:
            errors["listing"] = "O'zingiz joylagan e'lonni bron qila olmaysiz."
        if (
            self.listing_id
            and self.listing.availability_status != RentalListing.AvailabilityStatus.ACTIVE
            and self.status not in (self.Status.CANCELLED, self.Status.RETURNED)
        ):
            errors["listing"] = "Bu e'lon hozir remontda."
        if self.check_in and self.check_out:
            if self.check_in < timezone.localdate():
                errors["check_in"] = "Boshlanish sanasi bugundan oldin bo'lishi mumkin emas."
            if self.check_out <= self.check_in:
                errors["check_out"] = "Tugash sanasi boshlanish sanasidan keyin bo'lishi kerak."
        if self.guests is not None and self.guests < 1:
            errors["guests"] = "Kamida 1 kishi bo'lishi kerak."
        if self.listing_id and self.guests:
            if self.guests > self.listing.capacity:
                errors["guests"] = f"Bu e'lon uchun eng ko'p sig'im: {self.listing.capacity}."
        if self.listing_id and self.check_in and self.check_out and self.check_out > self.check_in:
            conflicts = Booking.objects.filter(
                listing_id=self.listing_id,
                status__in=[self.Status.PENDING, self.Status.CONFIRMED, self.Status.HANDED_OVER],
                check_in__lt=self.check_out,
                check_out__gt=self.check_in,
            )
            if self.pk:
                conflicts = conflicts.exclude(pk=self.pk)
            if conflicts.exists():
                errors["check_in"] = "Bu sanalarda e'lon band. Boshqa sanalarni tanlang."
            if not self.pk and unreturned_rentals(self.listing_id).exists():
                errors["check_in"] = "Bu mahsulot oldingi mijozdan hali qaytarilmagan."
            if BookingOrder.objects.filter(
                listing_id=self.listing_id,
                status__in=[BookingOrder.Status.PENDING, BookingOrder.Status.AWAITING_PAYMENT],
                check_in__lt=self.check_out,
                check_out__gt=self.check_in,
            ).exists():
                errors["check_in"] = "Bu sanalarda e'lon uchun to'lov kutilayotgan buyurtma bor."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.pk and not self.total_price and self.listing_id and self.check_in and self.check_out and self.check_out > self.check_in:
            from .installments import rental_total

            self.total_price = rental_total(self.listing, self.check_in, self.check_out, self.rental_unit, self.months)
        super().save(*args, **kwargs)

    @property
    def is_monthly(self):
        return self.rental_unit == self.RentalUnit.MONTH

    @property
    def has_installments(self):
        return self.payment_plan != self.PaymentPlan.FULL

    def __str__(self):
        return f"Bron #{self.pk or 'yangi'} — {self.listing.title}"


def unreturned_rentals(listing_id):
    """Rentals whose end date has passed but whose item was not brought back yet."""
    return Booking.objects.filter(
        listing_id=listing_id, status=Booking.Status.HANDED_OVER, check_out__lte=timezone.localdate(),
    )


class BookingOrder(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Qabul qilinishi kutilmoqda"
        AWAITING_PAYMENT = "awaiting_payment", "To'lov kutilmoqda"
        PAID = "paid", "To'langan"
        REJECTED = "rejected", "Rad etilgan"
        CANCELLED = "cancelled", "Bekor qilingan"

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="booking_orders", verbose_name="Foydalanuvchi")
    listing = models.ForeignKey(RentalListing, on_delete=models.PROTECT, related_name="booking_orders", verbose_name="E'lon")
    check_in = models.DateField("Boshlanish sanasi")
    check_out = models.DateField("Tugash sanasi")
    guests = models.PositiveSmallIntegerField("Mehmonlar / yo'lovchilar", default=1)
    payment_method = models.CharField("To'lov turi", max_length=20, choices=Booking.PaymentMethod.choices)
    rental_unit = models.CharField("Ijara turi", max_length=5, choices=Booking.RentalUnit.choices, default=Booking.RentalUnit.DAY)
    months = models.PositiveSmallIntegerField("Oylar soni", null=True, blank=True)
    payment_plan = models.CharField("To'lov rejasi", max_length=8, choices=Booking.PaymentPlan.choices, default=Booking.PaymentPlan.FULL)
    total_price = models.DecimalField("Jami narx (so'm)", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    # Paid online now: the whole rent, or the first part of an instalment plan.
    first_amount = models.DecimalField("Hozir to'lanadi (so'm)", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField("Holati", max_length=20, choices=Status.choices, default=Status.AWAITING_PAYMENT)
    booking = models.OneToOneField(Booking, on_delete=models.SET_NULL, related_name="paid_order", null=True, blank=True, verbose_name="Yaratilgan bron")
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Bron buyurtmasi"
        verbose_name_plural = "Bron buyurtmalari"
        indexes = [
            models.Index(fields=["listing", "check_in", "check_out", "status"], name="core_order_dates_status_idx"),
        ]

    @property
    def days(self):
        return max((self.check_out - self.check_in).days, 0)

    def clean(self):
        errors = {}
        if self.listing_id and self.user_id and self.listing.owner_id == self.user_id:
            errors["listing"] = "O'zingiz joylagan e'lonni bron qila olmaysiz."
        if (
            self.listing_id
            and self.listing.availability_status != RentalListing.AvailabilityStatus.ACTIVE
        ):
            errors["listing"] = "Bu e'lon hozir remontda."
        if self.check_in and self.check_out:
            if self.check_in < timezone.localdate():
                errors["check_in"] = "Boshlanish sanasi bugundan oldin bo'lishi mumkin emas."
            if self.check_out <= self.check_in:
                errors["check_out"] = "Tugash sanasi boshlanish sanasidan keyin bo'lishi kerak."
        if self.guests is not None and self.guests < 1:
            errors["guests"] = "Kamida 1 kishi bo'lishi kerak."
        if self.listing_id and self.guests and self.guests > self.listing.capacity:
            errors["guests"] = f"Bu e'lon uchun eng ko'p sig'im: {self.listing.capacity}."
        if self.listing_id and self.check_in and self.check_out and self.check_out > self.check_in:
            conflicts = Booking.objects.filter(
                listing_id=self.listing_id,
                status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.HANDED_OVER],
                check_in__lt=self.check_out,
                check_out__gt=self.check_in,
            )
            if conflicts.exists():
                errors["check_in"] = "Bu sanalarda e'lon band. Boshqa sanalarni tanlang."
            if not self.pk and unreturned_rentals(self.listing_id).exists():
                errors["check_in"] = "Bu mahsulot oldingi mijozdan hali qaytarilmagan."
            orders = BookingOrder.objects.filter(
                listing_id=self.listing_id,
                status__in=[self.Status.PENDING, self.Status.AWAITING_PAYMENT],
                check_in__lt=self.check_out,
                check_out__gt=self.check_in,
            )
            if self.pk:
                orders = orders.exclude(pk=self.pk)
            if orders.exists():
                errors["check_in"] = "Bu sanalarda e'lon band. Boshqa sanalarni tanlang."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.pk and self.listing_id and self.check_in and self.check_out and self.check_out > self.check_in:
            from .installments import rental_total, schedule

            self.total_price = rental_total(self.listing, self.check_in, self.check_out, self.rental_unit, self.months)
            self.first_amount = schedule(self.total_price, self.check_in, self.check_out, self.payment_plan, self.months)[0][1]
        super().save(*args, **kwargs)

    @property
    def payable_amount(self):
        return self.first_amount or self.total_price

    def __str__(self):
        return f"Buyurtma {self.reference} — {self.listing.title}"


class Installment(models.Model):
    """One part of a monthly rental paid in instalments (every month or every 15 days)."""

    class Status(models.TextChoices):
        PENDING = "pending", "To'lanmagan"
        PAID = "paid", "To'langan"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="installments", verbose_name="Bron")
    number = models.PositiveSmallIntegerField("Tartib raqami")
    due_date = models.DateField("To'lov sanasi")
    amount = models.DecimalField("Summa (so'm)", max_digits=14, decimal_places=2)
    status = models.CharField("Holati", max_length=8, choices=Status.choices, default=Status.PENDING)
    method = models.CharField("Qanday to'landi", max_length=20, choices=Booking.PaymentMethod.choices, blank=True)
    paid_at = models.DateTimeField("To'langan vaqt", null=True, blank=True)
    # Click / Payme order id for paying this part online.
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    reminded_on = models.DateField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["booking", "number"]
        verbose_name = "To'lov bo'lagi"
        verbose_name_plural = "To'lov bo'laklari"
        constraints = [models.UniqueConstraint(fields=["booking", "number"], name="core_installment_booking_number_uniq")]
        indexes = [models.Index(fields=["status", "due_date"], name="core_installment_due_idx")]

    @property
    def is_overdue(self):
        return self.status == self.Status.PENDING and self.due_date < timezone.localdate()

    def __str__(self):
        return f"#{self.booking_id} — {self.number}-to'lov, {self.amount} so'm"


class PaymentTransaction(models.Model):
    class Provider(models.TextChoices):
        CLICK = "click", "Click"
        PAYME = "payme", "Payme"

    booking_order = models.ForeignKey(BookingOrder, on_delete=models.PROTECT, related_name="payments", null=True, blank=True)
    installment = models.ForeignKey("Installment", on_delete=models.PROTECT, related_name="payments", null=True, blank=True)
    provider = models.CharField(max_length=10, choices=Provider.choices)
    provider_transaction_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    state = models.SmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    performed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.SmallIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "To'lov tranzaksiyasi"
        verbose_name_plural = "To'lov tranzaksiyalari"

    def __str__(self):
        return f"{self.provider} — {self.provider_transaction_id}"


class Payout(models.Model):
    """Money Rentora owes a provider for one online-paid booking, or owes back to the customer.

    held     — paid online, the item is not handed over yet;
    ready    — handed over: send `net_amount` to the provider's card;
    paid     — sent to the provider;
    refund   — cancelled before the hand-over: return `gross_amount` to the customer;
    refunded — returned to the customer.
    """

    class Status(models.TextChoices):
        HELD = "held", "Ushlab turilibdi"
        READY = "ready", "Ijara beruvchiga o'tkazish kerak"
        PAID = "paid", "Ijara beruvchiga o'tkazildi"
        REFUND = "refund", "Mijozga qaytarish kerak"
        REFUNDED = "refunded", "Mijozga qaytarildi"

    booking = models.ForeignKey("Booking", on_delete=models.PROTECT, related_name="payouts")
    installment = models.ForeignKey("Installment", on_delete=models.PROTECT, null=True, blank=True, related_name="payouts")
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payouts")
    payment = models.ForeignKey("PaymentTransaction", on_delete=models.PROTECT, null=True, blank=True, related_name="payouts")
    gross_amount = models.DecimalField("Mijoz to'lagan", max_digits=14, decimal_places=2)
    commission_percent = models.DecimalField("Komissiya, %", max_digits=5, decimal_places=2)
    commission_amount = models.DecimalField("Rentora komissiyasi", max_digits=14, decimal_places=2)
    net_amount = models.DecimalField("Ijara beruvchiga", max_digits=14, decimal_places=2)
    status = models.CharField("Holati", max_length=10, choices=Status.choices, default=Status.HELD)
    card_last4 = models.CharField("Karta", max_length=4, blank=True)
    reference = models.CharField("O'tkazma raqami / izoh", max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "To'lov o'tkazmasi"
        verbose_name_plural = "To'lov o'tkazmalari"
        indexes = [models.Index(fields=["status", "created_at"], name="core_payout_status_idx")]

    def __str__(self):
        return f"#{self.booking_id} — {self.net_amount} so'm — {self.get_status_display()}"


class Conversation(models.Model):
    """A chat. Listing chats link a customer and a provider; support chats link a user and the admin team."""

    class Kind(models.TextChoices):
        LISTING = "listing", "E'lon bo'yicha"
        SUPPORT = "support", "Admin bilan"

    class SupportStatus(models.TextChoices):
        WAITING = "waiting", "Javob kutmoqda"
        AI = "ai", "AI javob berdi"
        ESCALATED = "escalated", "Admin kerak"
        ANSWERED = "answered", "Admin javob berdi"

    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.LISTING)
    listing = models.ForeignKey(
        RentalListing, on_delete=models.CASCADE, related_name="conversations", null=True, blank=True,
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rental_conversations",
    )
    # Empty for support chats: any admin answers on behalf of the team.
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="provider_conversations",
        null=True, blank=True,
    )
    support_status = models.CharField(max_length=10, choices=SupportStatus.choices, blank=True)
    customer_last_read_message_id = models.PositiveBigIntegerField(default=0)
    provider_last_read_message_id = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["listing", "customer"], name="core_chat_listing_customer_uniq"),
            models.UniqueConstraint(
                fields=["customer"], condition=models.Q(kind="support"), name="core_chat_one_support_per_user",
            ),
        ]
        indexes = [models.Index(fields=["kind", "support_status", "updated_at"], name="core_chat_support_idx")]

    @property
    def is_support(self):
        return self.kind == self.Kind.SUPPORT

    def is_participant(self, user):
        if not getattr(user, "is_authenticated", False):
            return False
        if self.is_support:
            return user.pk == self.customer_id or user.is_staff
        return user.pk in (self.customer_id, self.provider_id)

    def last_read_for(self, user):
        """The newest message id this user has seen (admins share the support team's read marker)."""
        if user.pk == self.customer_id:
            return self.customer_last_read_message_id
        return self.provider_last_read_message_id

    def other_side_last_read(self, user):
        if user.pk == self.customer_id:
            return self.provider_last_read_message_id
        return self.customer_last_read_message_id

    def __str__(self):
        if self.is_support:
            return f"Admin chat: {self.customer}"
        return f"{self.listing.title}: {self.customer} ↔ {self.provider}"


class ChatMessage(models.Model):
    class AttachmentType(models.TextChoices):
        IMAGE = "image", "Rasm"
        AUDIO = "audio", "Ovozli xabar"
        VIDEO = "video", "Video"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    # Empty for messages written by the support AI.
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rental_chat_messages",
        null=True, blank=True,
    )
    is_ai = models.BooleanField(default=False)
    text = models.TextField(blank=True, max_length=5000)
    attachment = models.FileField(upload_to=randomized_upload_path("chat", allowed=SAFE_CHAT_EXTENSIONS, fallback="bin"), storage=chat_media_storage, blank=True)
    attachment_type = models.CharField(max_length=10, choices=AttachmentType.choices, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def from_support_team(self):
        """True for admin or AI messages in a support chat (shown to the user as "Rentora Admin")."""
        return self.conversation.is_support and self.sender_id != self.conversation.customer_id

    def display_sender(self, viewer=None):
        if self.from_support_team and not (viewer is not None and viewer.is_staff):
            return "Rentora Admin"
        if self.is_ai or self.sender is None:
            return "Rentora AI"
        return self.sender.get_full_name() or self.sender.get_username()

    class Meta:
        ordering = ["created_at"]

    def clean(self):
        if not self.text.strip() and not self.attachment:
            raise ValidationError("Xabar matni yoki rasm/ovozli fayl yuboring.")
        if self.attachment and not self.attachment_type:
            raise ValidationError({"attachment_type": "Fayl turi aniqlanmagan."})

    def __str__(self):
        return f"{self.sender} — {self.created_at:%Y-%m-%d %H:%M}"
