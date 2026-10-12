from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Booking, BookingOrder, RentalListing, home, car

User = get_user_model()


class RegistrationForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, label="Ism", widget=forms.TextInput(attrs={"placeholder": "Ismingiz"}))
    email = forms.EmailField(label="Elektron pochta", widget=forms.EmailInput(attrs={"placeholder": "siz@example.com"}))

    class Meta:
        model = User
        fields = ("first_name", "username", "email", "password1", "password2")
        labels = {"username": "Foydalanuvchi nomi", "password1": "Parol", "password2": "Parolni takrorlang"}

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