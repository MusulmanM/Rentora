from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from .models import Booking, BookingOrder, ListingImage, PaymentTransaction, RentalListing, home, car


class ListingImageInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        image_count = sum(
            1 for form in self.forms
            if form.cleaned_data
            and not form.cleaned_data.get("DELETE", False)
            and (form.cleaned_data.get("image") or form.instance.pk)
        )
        if image_count > 10:
            raise ValidationError("Har bir e'lon uchun eng ko'p 10 ta rasm yuklash mumkin.")


class ListingImageForm(forms.ModelForm):
    class Meta:
        model = ListingImage
        fields = ("image",)

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and not getattr(image, "_committed", False) and image.size > 10 * 1024 * 1024:
            raise ValidationError("Har bir rasm hajmi 10 MB dan oshmasligi kerak.")
        return image


class ListingImageInline(admin.TabularInline):
    model = ListingImage
    form = ListingImageForm
    formset = ListingImageInlineFormSet
    extra = 1
    max_num = 10
    fields = ("image",)
    verbose_name = "Rasm (10 tagacha)"
    verbose_name_plural = "E'lon rasmlari (10 tagacha)"


@admin.register(RentalListing)
class RentalListingAdmin(admin.ModelAdmin):
    inlines = (ListingImageInline,)
    list_display = ("title", "kind", "city", "price_per_day", "is_featured", "is_active")
    list_filter = ("kind", "city", "is_featured", "is_active")
    search_fields = ("title", "title_ru", "title_en", "city", "address", "description", "description_ru", "description_en", "brand")
    fieldsets = (
        ("E'lon (o'zbekcha)", {"fields": ("kind", "title", "city", "address", "description")} ),
        ("Translations / Tarjimalar", {"fields": ("title_ru", "description_ru", "title_en", "description_en"), "classes": ("collapse",)}),
        ("Ijara shartlari", {"fields": ("price_per_day", "capacity", "bedrooms", "bathrooms", "brand", "transmission", "year")} ),
        ("Holat", {"fields": ("slug", "is_featured", "is_active")} ),
    )
    list_editable = ("is_featured", "is_active")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "listing", "user", "check_in", "check_out", "total_price", "status", "created_at")
    list_filter = ("status", "listing__kind", "created_at")
    search_fields = ("listing__title", "user__username", "user__email")
    readonly_fields = ("total_price", "created_at", "updated_at")
    list_editable = ("status",)


@admin.register(BookingOrder)
class BookingOrderAdmin(admin.ModelAdmin):
    list_display = ("reference", "listing", "user", "check_in", "check_out", "total_price", "payment_method", "status", "created_at")
    list_filter = ("status", "payment_method", "listing__kind", "created_at")
    search_fields = ("reference", "listing__title", "user__username", "user__email")
    readonly_fields = tuple(field.name for field in BookingOrder._meta.fields)


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ("provider", "provider_transaction_id", "booking_order", "amount", "state", "created_at", "performed_at")
    list_filter = ("provider", "state", "created_at")
    search_fields = ("provider_transaction_id", "booking_order__reference", "booking_order__user__username")
    readonly_fields = tuple(field.name for field in PaymentTransaction._meta.fields)



@admin.register(home)
class HomeAdmin(admin.ModelAdmin):
    list_display = ("title", "city", "price_per_day", "is_featured", "is_active")
    list_filter = ("city", "is_featured", "is_active")
    search_fields = ("title", "description", "city", "address")
    fieldsets = (
        ("E'lon (o'zbekcha)", {"fields": ("title", "city", "address", "description")} ),
        ("Ijara shartlari", {"fields": ("price_per_day", "capacity", "bedrooms", "bathrooms", "image_url")} ),
        ("Holat", {"fields": ("slug", "is_featured", "is_active")} ),
    )
    list_editable = ("is_featured", "is_active")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(car)
class CarAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "year", "price")
    list_filter = ("brand", "year")
    search_fields = ("name", "brand", "description")
    fieldsets = (
        ("Avtomobil (o'zbekcha)", {"fields": ("name", "brand", "year", "description")} ),
        ("Narx va holat", {"fields": ("price",)} ),
    )