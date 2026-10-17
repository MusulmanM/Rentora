import re

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    Booking, BookingOrder, ChatMessage, ContactMessage, District, HostProfile, ListingImage, ListingReview,
    PendingPhoneVerification, PendingRegistration, Region, RentalListing, UserProfile,
)
from .installments import MAX_MONTHS, add_months, allowed_plans
from .payments import available_payment_methods
from .uploads import validate_image_upload, validate_media_upload

User = get_user_model()


def normalize_phone_number(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) != 12 or not digits.startswith("998"):
        raise ValidationError("O'zbekiston telefon raqamini +998 XX XXX XX XX formatida kiriting.")
    return f"+{digits}"


class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, label="Ism", widget=forms.TextInput(attrs={"placeholder": "Ismingiz"}))
    email = forms.EmailField(label="Elektron pochta", widget=forms.EmailInput(attrs={"placeholder": "siz@example.com"}))
    phone_number = forms.CharField(
        max_length=24, label="Telefon raqami",
        widget=forms.TextInput(attrs={"placeholder": "+998 90 123 45 67", "autocomplete": "tel"}),
    )

    class Meta:
        model = User
        fields = ("first_name", "username", "email", "phone_number", "password1", "password2")
        labels = {
            "username": "Foydalanuvchi nomi", "password1": "Parol",
            "password2": "Parolni takrorlang",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "form-input")
            field.help_text = ""
        self.fields["username"].widget.attrs["placeholder"] = "Foydalanuvchi nomi"
        self.fields["password1"].widget.attrs["placeholder"] = "Kamida 8 ta belgi"
        self.fields["password2"].widget.attrs["placeholder"] = "Parolni qayta kiriting"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Bu elektron pochta allaqachon ro'yxatdan o'tgan.")
        return email

    def clean_phone_number(self):
        phone_number = normalize_phone_number(self.cleaned_data["phone_number"])
        if UserProfile.objects.filter(phone_number=phone_number).exists():
            raise ValidationError("Bu telefon raqami allaqachon ro'yxatdan o'tgan.")
        if PendingRegistration.objects.filter(
            phone_number=phone_number, expires_at__gt=timezone.now(),
        ).exists():
            raise ValidationError("Bu raqam bilan tasdiqlash jarayoni boshlangan. OTP kodni kiriting.")
        return phone_number


class RegistrationOTPForm(forms.Form):
    code = forms.RegexField(
        regex=r"^\d{6}$", max_length=6, min_length=6, label="Telegram OTP kodi",
        error_messages={"invalid": "Telegram'dan kelgan 6 xonali kodni kiriting."},
        widget=forms.TextInput(attrs={
            "class": "form-input", "inputmode": "numeric", "autocomplete": "one-time-code",
            "placeholder": "123456",
        }),
    )


class PhoneNumberForm(forms.Form):
    phone_number = forms.CharField(
        max_length=24, label="Telefon raqami",
        widget=forms.TextInput(attrs={
            "class": "form-input", "placeholder": "+998 90 123 45 67", "autocomplete": "tel",
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_phone_number(self):
        phone_number = normalize_phone_number(self.cleaned_data["phone_number"])
        if UserProfile.objects.filter(phone_number=phone_number).exists():
            raise ValidationError("Bu telefon raqami allaqachon boshqa hisobga bog'langan.")
        existing = PendingPhoneVerification.objects.filter(phone_number=phone_number).first()
        if existing and existing.user_id != getattr(self.user, "pk", None):
            raise ValidationError("Bu raqam bilan boshqa tasdiqlash jarayoni davom etmoqda.")
        return phone_number


class BookingForm(forms.ModelForm):
    rental_unit = forms.ChoiceField(
        label="Ijara turi", choices=Booking.RentalUnit.choices, initial=Booking.RentalUnit.DAY,
        widget=forms.RadioSelect, required=False,
    )
    months = forms.TypedChoiceField(
        label="Necha oyga", coerce=int, required=False, empty_value=None,
        choices=[(n, f"{n} oy") for n in range(1, MAX_MONTHS + 1)],
    )
    payment_plan = forms.ChoiceField(
        label="To'lov rejasi", choices=Booking.PaymentPlan.choices, initial=Booking.PaymentPlan.FULL,
        widget=forms.RadioSelect, required=False,
    )

    class Meta:
        model = Booking
        fields = ("rental_unit", "check_in", "check_out", "months", "guests", "payment_method", "payment_plan")
        widgets = {
            "check_in": forms.DateInput(attrs={"type": "date", "class": "form-input"}, format="%Y-%m-%d"),
            "check_out": forms.DateInput(attrs={"type": "date", "class": "form-input"}, format="%Y-%m-%d"),
            "guests": forms.NumberInput(attrs={"class": "form-input", "min": 1}),
            "payment_method": forms.Select(attrs={"class": "form-input"}),
        }
        labels = {
            "check_in": "Boshlanish sanasi",
            "check_out": "Tugash sanasi",
            "guests": "Mehmonlar / yo'lovchilar",
            "payment_method": "To'lov turi",
        }

    def __init__(self, *args, listing=None, user=None, **kwargs):
        self.listing = listing
        self.user = user
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-input")
        if listing:
            self.fields["guests"].widget.attrs["max"] = listing.capacity
            self.fields["guests"].initial = 1
            # Online payment goes to the owner's own Click / Payme merchant, so offer only what they connected.
            allowed = available_payment_methods(listing)
            self.fields["payment_method"].choices = [
                (value, label) for value, label in Booking.PaymentMethod.choices if value in allowed
            ]
            self.cash_only = allowed == [Booking.PaymentMethod.CASH]
        # Monthly rental: homes whose provider set a monthly price. The end date then follows the months.
        self.monthly_available = bool(listing and listing.kind == RentalListing.Kind.HOME and listing.price_per_month)
        self.fields["check_out"].required = False
        self.fields["months"].widget.attrs["class"] = "form-input"
        for name in ("rental_unit", "payment_plan"):
            self.fields[name].widget.attrs.pop("class", None)  # radio pills, not text inputs
        if not self.monthly_available:
            self.fields["rental_unit"].choices = [(Booking.RentalUnit.DAY, "Kunlik")]
            self.fields["payment_plan"].choices = [(Booking.PaymentPlan.FULL, "To'liq")]

    def clean(self):
        cleaned = super().clean()
        unit = cleaned.get("rental_unit") or Booking.RentalUnit.DAY
        plan = cleaned.get("payment_plan") or Booking.PaymentPlan.FULL
        cleaned["rental_unit"], cleaned["payment_plan"] = unit, plan
        if unit == Booking.RentalUnit.MONTH:
            months = cleaned.get("months")
            if not self.monthly_available:
                self.add_error("rental_unit", "Bu e'lonni faqat kunlik ijaraga olish mumkin.")
            elif not months:
                self.add_error("months", "Necha oyga ijaraga olishingizni tanlang.")
            elif cleaned.get("check_in"):
                cleaned["check_out"] = add_months(cleaned["check_in"], months)
        else:
            cleaned["months"] = None
            if not cleaned.get("check_out") and "check_out" not in self.errors:
                self.add_error("check_out", "Tugash sanasini tanlang.")
        if plan not in allowed_plans(unit, cleaned.get("months")):
            self.add_error("payment_plan", "Bo'lib to'lash faqat oylik ijarada mumkin (har oy — kamida 2 oy).")
        if self.listing and self.listing.owner_id == getattr(self.user, "pk", None):
            self.add_error(None, "O'zingiz joylagan e'lonni bron qila olmaysiz.")
        if self.listing and self.listing.availability_status != RentalListing.AvailabilityStatus.ACTIVE:
            self.add_error(None, "Bu e'lon hozir remontda.")
        start = cleaned.get("check_in")
        end = cleaned.get("check_out")
        guests = cleaned.get("guests")
        if start and start < timezone.localdate():
            self.add_error("check_in", "Bugungi kundan oldingi sana tanlanmaydi.")
        if start and end and end <= start:
            self.add_error("check_out", "Tugash sanasi boshlanish sanasidan keyin bo'lishi kerak.")
        if guests is not None and guests < 1:
            self.add_error("guests", "Kamida 1 kishi bo'lishi kerak.")
        if guests and self.listing and guests > self.listing.capacity:
            self.add_error("guests", f"Bu e'lon uchun sig'im {self.listing.capacity} kishi.")
        if start and end and end > start and self.listing:
            conflicts = Booking.objects.filter(
                listing=self.listing,
                status__in=[
                    Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.HANDED_OVER,
                ],
                check_in__lt=end,
                check_out__gt=start,
            )
            if conflicts.exists():
                self.add_error("check_in", "Bu e'lon tanlangan sanalarda band. Boshqa sanalarni kiriting.")
            if BookingOrder.objects.filter(
                listing=self.listing,
                status__in=[BookingOrder.Status.PENDING, BookingOrder.Status.AWAITING_PAYMENT],
                check_in__lt=end,
                check_out__gt=start,
            ).exists():
                self.add_error("check_in", "Bu e'lon tanlangan sanalarda boshqa buyurtma uchun band.")
        return cleaned


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        if len(files) > 10:
            raise ValidationError("Har bir e'lon uchun eng ko'p 10 ta rasm yuklash mumkin.")
        cleaned_files = []
        for uploaded_file in files:
            cleaned_file = super().clean(uploaded_file, initial)
            if cleaned_file.size > 10 * 1024 * 1024:
                raise ValidationError("Har bir rasm hajmi 10 MB dan oshmasligi kerak.")
            cleaned_files.append(validate_image_upload(cleaned_file))
        return cleaned_files


class LocalizedRegionSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        region = getattr(value, "instance", None)
        if region:
            option["attrs"].update(_localized_name_attrs(region))
        return option


class DistrictSelect(LocalizedRegionSelect):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        district = getattr(value, "instance", None)
        if district:
            option["attrs"]["data-region"] = str(district.region_id)
        return option


def _localized_name_attrs(place):
    return {
        "data-localized-text": "",
        "data-uz": place.name_uz,
        "data-ru": place.name_ru or place.name_uz,
        "data-en": place.name_en or place.name_uz,
    }


class RegionChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.name_uz


# Fields that only make sense for one listing type. Everything else is shared.
HOME_ONLY_FIELDS = ("bedrooms", "bathrooms")
CAR_ONLY_FIELDS = ("brand", "transmission", "year")
LISTING_KIND_COPY = {
    RentalListing.Kind.HOME: {
        "title_placeholder": "Masalan: Chilonzordagi 2 xonali kvartira",
        "description_placeholder": "Xonalar, jihozlar, sharoitlar va qoidalar haqida yozing.",
        "address_label": "Manzil",
        "address_placeholder": "Ko'cha, uy raqami, mo'ljal",
        "capacity_label": "Mehmonlar soni",
        "details_title": "Uy tafsilotlari",
    },
    RentalListing.Kind.CAR: {
        "title_placeholder": "Masalan: Chevrolet Cobalt, oq rang",
        "description_placeholder": "Avtomobil holati, yoqilg'i turi, sharoitlar va ijara shartlari haqida yozing.",
        "address_label": "Olib ketish manzili",
        "address_placeholder": "Avtomobilni topshirish joyi",
        "capacity_label": "O'rindiqlar soni",
        "details_title": "Avtomobil tafsilotlari",
    },
}


class RentalListingForm(forms.ModelForm):
    image_uploads = MultipleFileField(
        label="Rasmlar (10 tagacha, har biri 10 MB gacha)",
        required=False,
        widget=MultipleFileInput(attrs={"class": "form-input", "accept": "image/*"}),
    )
    remove_images = forms.ModelMultipleChoiceField(
        queryset=ListingImage.objects.none(), required=False,
        label="O'chiriladigan rasmlar", widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = RentalListing
        fields = (
            "kind", "title", "title_ru", "title_en", "region", "district", "address",
            "description", "description_ru", "description_en", "price_per_day", "price_per_month", "capacity",
            "bedrooms", "bathrooms", "brand", "transmission", "year",
        )
        field_classes = {"region": RegionChoiceField, "district": RegionChoiceField}
        labels = {
            "kind": "E'lon turi", "title": "Nomi", "title_ru": "Nomi (RU)", "title_en": "Nomi (EN)",
            "region": "Viloyat", "district": "Shahar / tuman", "address": "Manzil",
            "description": "Tavsif", "description_ru": "Tavsif (RU)", "description_en": "Tavsif (EN)",
            "price_per_day": "Kunlik narx (so'm)", "price_per_month": "Oylik narx (so'm)", "bedrooms": "Yotoq xonalari", "bathrooms": "Hammomlar",
            "brand": "Marka", "transmission": "Uzatmalar qutisi", "year": "Ishlab chiqarilgan yil",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "description_ru": forms.Textarea(attrs={"rows": 3}),
            "description_en": forms.Textarea(attrs={"rows": 3}),
            "region": LocalizedRegionSelect(),
            "district": DistrictSelect(),
        }

    def __init__(self, *args, kind=None, auto_translate=False, **kwargs):
        super().__init__(*args, **kwargs)
        is_edit = bool(self.instance.pk)
        if is_edit:
            kind = self.instance.kind
        elif self.is_bound:
            kind = self.data.get("kind") or kind
        self.listing_kind = kind if kind in RentalListing.Kind.values else None
        self.is_edit = is_edit
        self.fields["district"].queryset = District.objects.select_related("region").all()
        self.fields["region"].queryset = Region.objects.all()
        region_id = self.data.get("region") or self.initial.get("region") or self.instance.region_id
        if region_id:
            self.fields["district"].queryset = District.objects.filter(region_id=region_id)
        self.fields["region"].empty_label = "Viloyatni tanlang"
        self.fields["district"].empty_label = "Avval viloyatni tanlang"

        if self.listing_kind:
            self.initial["kind"] = self.listing_kind
            self.fields["kind"].widget = forms.HiddenInput()
            for name in (CAR_ONLY_FIELDS if self.listing_kind == RentalListing.Kind.HOME else HOME_ONLY_FIELDS):
                del self.fields[name]
            copy = LISTING_KIND_COPY[self.listing_kind]
            self.fields["title"].widget.attrs["placeholder"] = copy["title_placeholder"]
            self.fields["description"].widget.attrs["placeholder"] = copy["description_placeholder"]
            self.fields["address"].label = copy["address_label"]
            self.fields["address"].widget.attrs["placeholder"] = copy["address_placeholder"]
            self.fields["capacity"].label = copy["capacity_label"]
            self.fields["capacity"].help_text = ""
            self.fields["capacity"].widget.attrs.update({"min": 1, "max": 50})
            if not is_edit:
                self.initial.setdefault("capacity", 5 if self.listing_kind == RentalListing.Kind.CAR else 2)
            if self.listing_kind == RentalListing.Kind.HOME:
                for name in HOME_ONLY_FIELDS:
                    self.fields[name].required = True
                    self.fields[name].widget.attrs.update({"min": 0, "max": 50})
                self.fields["price_per_month"].required = False
                self.fields["price_per_month"].widget.attrs.update({"min": 1, "step": "10000"})
                self.fields["price_per_month"].help_text = "Ixtiyoriy. Kiritsangiz, mijozlar uyni oylab ham ijaraga ola oladi."
            else:
                del self.fields["price_per_month"]
                self.fields["brand"].required = True
                self.fields["brand"].widget.attrs["placeholder"] = "Masalan: Chevrolet"
                self.fields["transmission"].required = True
                self.fields["transmission"].choices = [("", "Tanlang")] + [
                    choice for choice in RentalListing.Transmission.choices
                    if choice[0] != RentalListing.Transmission.NOT_APPLICABLE
                ]
                self.fields["year"].required = True
                self.fields["year"].widget.attrs.update({"min": 1980, "max": timezone.localdate().year + 1})

        if auto_translate:
            for name in ("title_ru", "title_en", "description_ru", "description_en"):
                self.fields[name].help_text = "Bo'sh qoldirsangiz, avtomatik tarjima qilinadi."
        self.fields["price_per_day"].widget.attrs.update({"min": 1, "step": "1000"})
        if is_edit:
            self.fields["image_uploads"].label = "Yangi rasmlar qo'shish (ixtiyoriy)"
            self.fields["remove_images"].queryset = self.instance.images.all()
        else:
            del self.fields["remove_images"]
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxSelectMultiple, forms.HiddenInput)):
                field.widget.attrs.setdefault("class", "form-input")
        self.fields["region"].widget.attrs["data-location-region"] = ""
        self.fields["district"].widget.attrs.update({
            "data-location-district": "", "data-chosen-label": "Shahar yoki tumanni tanlang",
        })

    def sections(self):
        """Group the bound fields so the template can render them under headings."""
        if not self.listing_kind:
            return []
        groups = [
            ("Asosiy ma'lumot", ("title", "description")),
            ("Joylashuv", ("region", "district", "address")),
            (LISTING_KIND_COPY[self.listing_kind]["details_title"], ("capacity", *(
                HOME_ONLY_FIELDS if self.listing_kind == RentalListing.Kind.HOME else CAR_ONLY_FIELDS
            ))),
            ("Narx", ("price_per_day", "price_per_month")),
            ("Tarjimalar (ixtiyoriy)", ("title_ru", "title_en", "description_ru", "description_en")),
            ("Rasmlar", ("remove_images", "image_uploads")),
        ]
        return [
            (title, [self[name] for name in names if name in self.fields])
            for title, names in groups
        ]

    def clean_kind(self):
        kind = self.cleaned_data.get("kind")
        if self.listing_kind and kind != self.listing_kind:
            raise ValidationError("E'lon turini o'zgartirib bo'lmaydi.")
        return kind

    def clean_year(self):
        year = self.cleaned_data.get("year")
        if year and not 1980 <= year <= timezone.localdate().year + 1:
            raise ValidationError(f"Yilni 1980–{timezone.localdate().year + 1} oralig'ida kiriting.")
        return year

    def clean_price_per_month(self):
        price = self.cleaned_data.get("price_per_month")
        if price is not None and price <= 0:
            raise ValidationError("Oylik narx 0 dan katta bo'lishi kerak.")
        return price

    def clean_price_per_day(self):
        price = self.cleaned_data.get("price_per_day")
        if price is not None and price <= 0:
            raise ValidationError("Kunlik narx 0 dan katta bo'lishi kerak.")
        return price

    def clean(self):
        cleaned = super().clean()
        region = cleaned.get("region")
        district = cleaned.get("district")
        if region and district and district.region_id != region.pk:
            self.add_error("district", "Tanlangan shahar yoki tuman viloyatga mos kelmaydi.")
        new_images = cleaned.get("image_uploads") or []
        removed = cleaned.get("remove_images") or []
        existing = self.instance.images.count() if self.instance.pk else 0
        remaining = existing - len(removed) + len(new_images)
        if remaining < 1:
            self.add_error("image_uploads", "E'lon uchun kamida bitta rasm yuklang.")
        elif remaining > 10:
            self.add_error("image_uploads", "Har bir e'lon uchun eng ko'p 10 ta rasm yuklash mumkin.")
        return cleaned

    def save(self, commit=True):
        listing = super().save(commit=False)
        listing.city = self.cleaned_data["district"].name_uz
        # Drop values that belong to the other listing type.
        if listing.kind == RentalListing.Kind.HOME:
            listing.brand = ""
            listing.transmission = RentalListing.Transmission.NOT_APPLICABLE
            listing.year = None
        else:
            listing.bedrooms = None
            listing.bathrooms = None
        if commit:
            listing.save()
            self.save_m2m()
        return listing


class HostOnboardingForm(forms.ModelForm):
    """Company profile of a provider: name, logo and phone are all required."""
    # Wider than the stored value: "+998 90 123 45 67" is normalized to "+998901234567".
    phone_number = forms.CharField(label="Kompaniya telefoni", max_length=24)

    class Meta:
        model = HostProfile
        fields = ("display_name", "logo", "phone_number")
        labels = {
            "display_name": "Kompaniya nomi",
            "logo": "Kompaniya logotipi",
            "phone_number": "Kompaniya telefoni",
        }
        widgets = {
            "display_name": forms.TextInput(attrs={"class": "form-input", "placeholder": "Masalan: Musulman Rent"}),
            "logo": forms.ClearableFileInput(attrs={"class": "form-input", "accept": "image/*"}),
            "phone_number": forms.TextInput(attrs={
                "class": "form-input", "placeholder": "+998 90 123 45 67", "autocomplete": "tel",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = True
        if self.instance.pk and self.instance.logo:
            self.fields["logo"].required = False
            self.fields["logo"].help_text = "Yangi logotip tanlamasangiz, avvalgisi qoladi."
        self.fields["logo"].widget = forms.FileInput(attrs={"class": "form-input", "accept": "image/*"})

    def clean_display_name(self):
        name = " ".join(self.cleaned_data["display_name"].split())
        if len(name) < 2:
            raise ValidationError("Kompaniya nomini kiriting.")
        return name

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if logo and hasattr(logo, "content_type"):  # A newly uploaded file, not the stored one.
            return validate_image_upload(logo, max_bytes=5 * 1024 * 1024, label="Logotip")
        return logo

    def clean_phone_number(self):
        return normalize_phone_number(self.cleaned_data["phone_number"])


class ProfileEditForm(forms.Form):
    first_name = forms.CharField(label="Ism", max_length=150, widget=forms.TextInput(attrs={"class": "form-input"}))
    last_name = forms.CharField(
        label="Familiya", max_length=150, required=False, widget=forms.TextInput(attrs={"class": "form-input"}),
    )
    avatar = forms.ImageField(
        label="Profil rasmi", required=False,
        widget=forms.FileInput(attrs={"class": "form-input", "accept": "image/*"}),
    )
    remove_avatar = forms.BooleanField(label="Rasmni o'chirish", required=False)

    def clean_first_name(self):
        name = " ".join(self.cleaned_data["first_name"].split())
        if not name:
            raise ValidationError("Ismingizni kiriting.")
        return name

    def clean_last_name(self):
        return " ".join(self.cleaned_data.get("last_name", "").split())

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar:
            return validate_image_upload(avatar, max_bytes=5 * 1024 * 1024, label="Rasm")
        return avatar


class ListingReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        label="Baho", coerce=int, choices=[(value, str(value)) for value in range(5, 0, -1)],
        widget=forms.RadioSelect,
    )

    class Meta:
        model = ListingReview
        fields = ("rating", "comment")
        labels = {"comment": "Izoh"}
        widgets = {"comment": forms.Textarea(attrs={
            "class": "form-input", "rows": 3, "maxlength": 2000, "placeholder": "Tajribangiz haqida yozing",
        })}

    def clean_comment(self):
        return self.cleaned_data.get("comment", "").strip()


class ContactMessageForm(forms.ModelForm):
    email = forms.EmailField(required=False, label="Elektron pochta")

    class Meta:
        model = ContactMessage
        fields = ("name", "email", "subject", "message")
        labels = {"name": "Ismingiz", "email": "Elektron pochta", "subject": "Mavzu", "message": "Xabar"}
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input"}),
            "email": forms.EmailInput(attrs={"class": "form-input"}),
            "subject": forms.TextInput(attrs={"class": "form-input"}),
            "message": forms.Textarea(attrs={"class": "form-input", "rows": 6}),
        }


class ListingAvailabilityForm(forms.Form):
    status = forms.ChoiceField(
        choices=RentalListing.AvailabilityStatus.choices,
        label="E'lon holati",
        widget=forms.Select(attrs={"class": "form-input"}),
    )


class ChatMessageForm(forms.ModelForm):
    attachment = forms.FileField(
        required=False,
        label="Rasm, video yoki ovozli xabar",
        widget=forms.ClearableFileInput(attrs={"class": "form-input", "accept": "image/*,video/*,audio/*"}),
    )
    # The voice recorder marks its .webm recordings as audio; other .webm files are videos.
    attachment_kind = forms.ChoiceField(
        required=False, choices=[("", ""), ("audio", "audio"), ("video", "video")], widget=forms.HiddenInput,
    )

    class Meta:
        model = ChatMessage
        fields = ("text",)
        labels = {"text": "Xabar"}
        widgets = {"text": forms.Textarea(attrs={
            "class": "form-input", "maxlength": 5000, "rows": 1, "placeholder": "Xabar yozing...",
        })}

    def clean(self):
        cleaned = super().clean()
        text = (cleaned.get("text") or "").strip()
        attachment = cleaned.get("attachment")
        if not text and not attachment:
            raise ValidationError("Xabar matni yoki rasm/video/ovozli fayl yuboring.")
        if attachment:
            limit = settings.CHAT_ATTACHMENT_MAX_BYTES
            if attachment.size > limit:
                raise ValidationError(f"Fayl hajmi {limit // (1024 * 1024)} MB dan oshmasligi kerak.")
            extension = attachment.name.rsplit(".", 1)[-1].lower() if "." in attachment.name else ""
            if extension in {"jpg", "jpeg", "png", "webp", "gif", "avif"}:
                try:
                    validate_image_upload(attachment, max_bytes=limit)
                except ValidationError:
                    raise ValidationError("Faqat haqiqiy rasm faylini yuboring.")
                cleaned["attachment_type"] = ChatMessage.AttachmentType.IMAGE
            else:
                kind = validate_media_upload(attachment, cleaned.get("attachment_kind", ""))
                cleaned["attachment_type"] = (
                    ChatMessage.AttachmentType.VIDEO if kind == "video" else ChatMessage.AttachmentType.AUDIO
                )
            # The model's own validation (run after this) must see the file too.
            self.instance.attachment = attachment
            self.instance.attachment_type = cleaned["attachment_type"]
        cleaned["text"] = text
        return cleaned


class HelperUserCreateForm(UserCreationForm):
    """Bosh admin creates a user or an admin from the helper panel."""
    first_name = forms.CharField(label="Ism", max_length=150, required=False)
    email = forms.EmailField(label="Elektron pochta", required=False)
    is_staff = forms.BooleanField(label="Admin (helper-admin paneliga kira oladi)", required=False)

    class Meta:
        model = User
        fields = ("username", "first_name", "email", "is_staff", "password1", "password2")
        labels = {"username": "Foydalanuvchi nomi"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-input")
            field.help_text = ""

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Bu elektron pochta allaqachon ro'yxatdan o'tgan.")
        return email


# Known BINs fill in the card type; co-branded cards (e.g. Humo-Visa 4073..., Uzcard-Mastercard) start
# with other digits, so the owner picks the type and any valid 16-digit card is accepted.
_CARD_PREFIXES = {"8600": "uzcard", "5614": "uzcard", "9860": "humo"}


def _luhn_ok(number):
    total = 0
    for index, digit in enumerate(reversed(number)):
        value = int(digit)
        if index % 2:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


class ProviderPaymentForm(forms.Form):
    """The provider's payout card. Only the last 4 digits are ever shown again."""

    card_number = forms.CharField(
        label="Karta raqami (Uzcard / Humo)", max_length=23, required=False,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "placeholder": "8600 0000 0000 0000"}),
    )
    card_brand = forms.ChoiceField(
        label="Karta turi", required=False,
        choices=[("", "Avtomatik aniqlash"), ("uzcard", "Uzcard"), ("humo", "Humo")],
    )
    card_holder = forms.CharField(label="Karta egasi (ism familiya)", max_length=80)
    accept_offer = forms.BooleanField(
        label="Ommaviy ofertaga roziman: Rentora mijoz to'lovini qabul qiladi va mahsulot topshirilgach, komissiyani ayirib, qolganini shu kartaga o'tkazadi.",
    )
    current_password = forms.CharField(
        label="Hisobingiz paroli", widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        help_text="Karta ma'lumotlarini o'zgartirish uchun parolingizni kiriting.",
    )

    def __init__(self, *args, account, user, **kwargs):
        self.account = account
        self.user = user
        kwargs.setdefault("initial", {}).update({
            "card_holder": account.card_holder, "card_brand": account.card_brand,
            "accept_offer": account.offer_accepted_at is not None,
        })
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-input")
        if account.has_card:
            self.fields["card_number"].help_text = f"Saqlangan karta: {account.masked_card}. O'zgartirish uchungina yangisini kiriting."

    def clean_card_number(self):
        number = re.sub(r"[\s-]", "", self.cleaned_data.get("card_number", ""))
        if not number:
            if not self.account.has_card:
                raise ValidationError("Karta raqamini kiriting.")
            return ""
        if not number.isdigit() or len(number) != 16:
            raise ValidationError("Karta raqami 16 ta raqamdan iborat bo'ladi.")
        if not _luhn_ok(number):
            raise ValidationError("Karta raqami noto'g'ri. Tekshirib qayta kiriting.")
        return number

    def clean(self):
        cleaned = super().clean()
        number, brand = cleaned.get("card_number"), cleaned.get("card_brand")
        if number and not brand:
            brand = _CARD_PREFIXES.get(number[:4], "")
            if not brand:
                self.add_error("card_brand", "Karta turini tanlang: Uzcard yoki Humo.")
        if not number and not brand:
            brand = self.account.card_brand
        cleaned["card_brand"] = brand
        return cleaned

    def clean_card_holder(self):
        holder = " ".join(self.cleaned_data["card_holder"].split())
        if len(holder) < 3:
            raise ValidationError("Karta egasining ism familiyasini kiriting.")
        return holder

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]
        if not self.user.check_password(password):
            raise ValidationError("Parol noto'g'ri.")
        return password

    def save(self):
        """Store the card. A new card or holder needs the head admin's approval again."""
        account, data = self.account, self.cleaned_data
        changed = False
        if data["card_number"]:
            account.card_number = data["card_number"]
            changed = True
        if data["card_brand"] and data["card_brand"] != account.card_brand:
            account.card_brand = data["card_brand"]
            changed = True
        if data["card_holder"] != account.card_holder:
            account.card_holder = data["card_holder"]
            changed = True
        if account.offer_accepted_at is None:
            account.offer_accepted_at = timezone.now()
        if changed:
            account.approved = False
        account.save()
        return changed


class GuestSupportForm(forms.Form):
    """First message from a visitor without an account (sign-up help, blocked account, ...)."""

    TOPICS = (
        ("register", "Ro'yxatdan o'tish"),
        ("blocked", "Akkauntim bloklangan"),
        ("login", "Kira olmayapman / parolni unutdim"),
        ("other", "Boshqa savol"),
    )
    name = forms.CharField(label="Ismingiz", max_length=80, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    phone_number = forms.CharField(
        label="Telefon raqamingiz", max_length=24, required=False,
        widget=forms.TextInput(attrs={"placeholder": "+998 90 123 45 67", "autocomplete": "tel"}),
        help_text="Ixtiyoriy. Akkauntingizni topishimizga yordam beradi.",
    )
    topic = forms.ChoiceField(label="Mavzu", choices=TOPICS)
    message = forms.CharField(label="Xabar", max_length=2000, widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-input")

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if len(name) < 2:
            raise ValidationError("Ismingizni kiriting.")
        return name

    def clean_phone_number(self):
        value = self.cleaned_data.get("phone_number", "").strip()
        return normalize_phone_number(value) if value else ""

    def clean_message(self):
        message = self.cleaned_data["message"].strip()
        if len(message) < 3:
            raise ValidationError("Xabarni yozing.")
        return message


class StartAppAuthenticationForm(AuthenticationForm):
    """Tells a blocked user why they cannot sign in, but only after the right password was given."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "blocked": "Akkauntingiz bloklangan. Ochish uchun quyidagi tugma orqali admin bilan yozishing.",
        "no_password": "Bu akkauntda parol yo'q (admin o'chirgan). Quyidagi \"Parolni tiklash\" orqali yangi parol o'rnating.",
    }

    def clean(self):
        try:
            return super().clean()
        except ValidationError:
            username, password = self.cleaned_data.get("username"), self.cleaned_data.get("password")
            user = get_user_model().objects.filter(username=username).first() if username else None
            if user is not None and user.is_active and not user.has_usable_password():
                raise ValidationError(self.error_messages["no_password"], code="no_password") from None
            if (
                user is not None and not user.is_active and password and user.check_password(password)
                and not getattr(getattr(user, "account", None), "is_guest", False)
            ):
                raise ValidationError(self.error_messages["blocked"], code="blocked") from None
            raise


class PasswordResetRequestForm(forms.Form):
    login = forms.CharField(
        label="Foydalanuvchi nomi yoki telefon raqami", max_length=150,
        widget=forms.TextInput(attrs={"class": "form-input", "autocomplete": "username", "placeholder": "Masalan: MusulmanM yoki +998 90 123 45 67"}),
    )


class PasswordResetCodeForm(SetPasswordForm):
    """The Telegram code plus the new password (checked by Django's password validators)."""

    code = forms.CharField(
        label="Telegram'dan kelgan kod", max_length=6, min_length=6,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code", "placeholder": "123456"}),
    )
    field_order = ["code", "new_password1", "new_password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = "Yangi parol"
        self.fields["new_password2"].label = "Yangi parolni takrorlang"
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-input")

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if not code.isdigit():
            raise ValidationError("Kod 6 ta raqamdan iborat.")
        return code
