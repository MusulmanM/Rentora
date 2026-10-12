import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from .models import (
    Booking, BookingOrder, ContactMessage, District, HostProfile, PendingPhoneVerification,
    PendingRegistration, Region, RentalListing, UserProfile, home, car,
)

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
    class Meta:
        model = Booking
        fields = ("check_in", "check_out", "guests", "payment_method")
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

    def clean(self):
        cleaned = super().clean()
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
                status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
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
            try:
                with Image.open(cleaned_file) as image:
                    if image.width * image.height > 40_000_000:
                        raise ValidationError("Rasm o'lchami juda katta.")
                    image.verify()
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
                raise ValidationError("Faqat haqiqiy rasm fayllarini yuklang.")
            finally:
                cleaned_file.seek(0)
            cleaned_files.append(cleaned_file)
        return cleaned_files


class DistrictSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        district = getattr(value, "instance", None)
        if district:
            option["attrs"]["data-region"] = str(district.region_id)
        return option


class RentalListingForm(forms.ModelForm):
    image_uploads = MultipleFileField(
        label="Rasmlar (10 tagacha, har biri 10 MB gacha)",
        widget=MultipleFileInput(attrs={"class": "form-input", "accept": "image/*"}),
    )

    class Meta:
        model = RentalListing
        fields = (
            "kind", "title", "title_ru", "title_en", "region", "district", "address",
            "description", "description_ru", "description_en", "price_per_day", "capacity",
            "bedrooms", "bathrooms", "brand", "transmission", "year",
        )
        labels = {
            "kind": "E'lon turi", "title": "Nomi", "title_ru": "Nomi (RU)", "title_en": "Nomi (EN)",
            "region": "Viloyat", "district": "Shahar / tuman", "address": "Manzil",
            "description": "Tavsif", "description_ru": "Tavsif (RU)", "description_en": "Tavsif (EN)",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "district": DistrictSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["district"].queryset = District.objects.select_related("region").all()
        self.fields["region"].queryset = Region.objects.all()
        region_id = self.data.get("region") or self.initial.get("region") or self.instance.region_id
        if region_id:
            self.fields["district"].queryset = District.objects.filter(region_id=region_id)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "form-input")
        self.fields["region"].widget.attrs["data-location-region"] = ""
        self.fields["district"].widget.attrs.update({"data-location-district": "", "data-placeholder": "Avval viloyatni tanlang"})

    def clean(self):
        cleaned = super().clean()
        region = cleaned.get("region")
        district = cleaned.get("district")
        if region and district and district.region_id != region.pk:
            self.add_error("district", "Tanlangan shahar yoki tuman viloyatga mos kelmaydi.")
        if not cleaned.get("image_uploads"):
            self.add_error("image_uploads", "E'lon uchun kamida bitta rasm yuklang.")
        return cleaned

    def save(self, commit=True):
        listing = super().save(commit=False)
        listing.city = self.cleaned_data["district"].name_uz
        if commit:
            listing.save()
            self.save_m2m()
        return listing


class HostOnboardingForm(forms.ModelForm):
    class Meta:
        model = HostProfile
        fields = ("display_name",)
        labels = {"display_name": "Ijara beruvchi nomi"}
        widgets = {"display_name": forms.TextInput(attrs={"class": "form-input", "placeholder": "Ismingiz yoki biznes nomi"})}


class ContactMessageForm(forms.ModelForm):
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


class homeForm(forms.ModelForm):
    class Meta:
        model = home
        fields = ["title", "city", "address", "description", "price_per_day", "capacity", "bedrooms", "bathrooms", "image_url"]
        labels = {
            "title": "Nomi", 
            "city": "Shahar", 
            "address": "Manzil", 
            "price_per_day": "Kunlik narx", 
            "description": "Tavsif"
        }



class carForm(forms.ModelForm):
    class Meta:
        model = car
        fields = ("name", "brand", "year", "price", "description")
        labels = {"name": "Nomi", "brand": "Brend", "year": "Yil", "price": "Narx", "description": "Tavsif"}