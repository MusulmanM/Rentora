from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class RentalListing(models.Model):
    class Kind(models.TextChoices):
        HOME = "home", "Uylar"
        CAR = "car", "Avtomobillar"

    class Transmission(models.TextChoices):
        AUTOMATIC = "automatic", "Avtomat"
        MANUAL = "manual", "Mexanika"
        NOT_APPLICABLE = "na", "Ko'rsatilmagan"

    kind = models.CharField("Turi", max_length=10, choices=Kind.choices)
    title = models.CharField("Nomi (UZ)", max_length=160)
    title_ru = models.CharField("Название (RU)", max_length=160, blank=True)
    title_en = models.CharField("Title (EN)", max_length=160, blank=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    city = models.CharField("Shahar", max_length=80)
    address = models.CharField("Manzil", max_length=220)
    description = models.TextField("Tavsif (UZ)")
    description_ru = models.TextField("Описание (RU)", blank=True)
    description_en = models.TextField("Description (EN)", blank=True)
    price_per_day = models.DecimalField("Kunlik narx (so'm)", max_digits=12, decimal_places=2)
    image_url = models.URLField("Rasm URL", max_length=600, blank=True)
    capacity = models.PositiveSmallIntegerField("Sig'im", default=2, help_text="Uy uchun mehmonlar, mashina uchun o'rindiqlar.")
    bedrooms = models.PositiveSmallIntegerField("Yotoq xonalari", blank=True, null=True)
    bathrooms = models.PositiveSmallIntegerField("Hammomlar", blank=True, null=True)
    brand = models.CharField("Marka", max_length=80, blank=True)
    transmission = models.CharField("Uzatmalar qutisi", max_length=12, choices=Transmission.choices, default=Transmission.NOT_APPLICABLE)
    year = models.PositiveSmallIntegerField("Ishlab chiqarilgan yil", blank=True, null=True)
    is_featured = models.BooleanField("Tavsiya etilgan", default=False)
    is_active = models.BooleanField("Faol", default=True)
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

    @property
    def is_home(self):
        return self.kind == self.Kind.HOME

    @property
    def is_car(self):
        return self.kind == self.Kind.CAR

    @property
    def kind_label(self):
        return self.get_kind_display()

    def __str__(self):
        return f"{self.title} — {self.city}"


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Kutilmoqda"
        CONFIRMED = "confirmed", "Tasdiqlangan"
        CANCELLED = "cancelled", "Bekor qilingan"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings", verbose_name="Foydalanuvchi")
    listing = models.ForeignKey(RentalListing, on_delete=models.PROTECT, related_name="bookings", verbose_name="E'lon")
    check_in = models.DateField("Boshlanish sanasi")
    check_out = models.DateField("Tugash sanasi")
    guests = models.PositiveSmallIntegerField("Mehmonlar / yo'lovchilar", default=1)
    total_price = models.DecimalField("Jami narx (so'm)", max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField("Holati", max_length=12, choices=Status.choices, default=Status.PENDING)
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

    def clean(self):
        errors = {}
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
                status__in=[self.Status.PENDING, self.Status.CONFIRMED],
                check_in__lt=self.check_out,
                check_out__gt=self.check_in,
            )
            if self.pk:
                conflicts = conflicts.exclude(pk=self.pk)
            if conflicts.exists():
                errors["check_in"] = "Bu sanalarda e'lon band. Boshqa sanalarni tanlang."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.listing_id and self.check_in and self.check_out and self.check_out > self.check_in:
            self.total_price = self.listing.price_per_day * (self.check_out - self.check_in).days
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Bron #{self.pk or 'yangi'} — {self.listing.title}"
    




class home(models.Model):
    title = models.CharField(max_length=255, blank=True, null=True)
    slug = models.SlugField(unique=True, blank=True, null=True)
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    price_per_day = models.DecimalField(max_digits=10, decimal_places=2)
    capacity = models.PositiveIntegerField(default=1)
    bedrooms = models.PositiveIntegerField(default=1)
    bathrooms = models.PositiveIntegerField(default=1)
    image_url = models.URLField(blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title or "Untitled Home"


class car(models.Model):
    name = models.CharField(max_length=255)
    brand = models.CharField(max_length=100)
    year = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.brand} {self.name} ({self.year})"
