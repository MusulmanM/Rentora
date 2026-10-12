from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.utils.html import format_html

from .models import (
    Booking, BookingOrder, ContactMessage, District, HostProfile, ListingImage, PaymentTransaction,
    RentalListing, UserProfile, home, car,
)
from .forms import DistrictSelect


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
    fields = ("image_preview", "image")
    readonly_fields = ("image_preview",)
    verbose_name = "Rasm (10 tagacha)"
    verbose_name_plural = "E'lon rasmlari (10 tagacha)"

    class Media:
        css = {"all": ("core/listing-images.css",)}

    @admin.display(description="Ko'rinish")
    def image_preview(self, obj):
        if not obj or not obj.pk or not obj.image:
            return "Rasm yuklangandan keyin ko'rinadi"
        return format_html(
            '<a class="admin-image-preview-link" href="{}" target="_blank" rel="noopener">'
            '<img class="admin-image-preview" src="{}" alt="E’lon rasmi"></a>',
            obj.image.url, obj.image.url,
        )


class RentalListingAdminForm(forms.ModelForm):
    class Meta:
        model = RentalListing
        fields = "__all__"
        widgets = {"district": DistrictSelect()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        region_id = self.data.get("region") or self.instance.region_id
        if region_id:
            self.fields["district"].queryset = District.objects.filter(region_id=region_id)
        self.fields["region"].widget.attrs["data-location-region"] = ""
        self.fields["district"].widget.attrs["data-location-district"] = ""


@admin.register(RentalListing)
class RentalListingAdmin(admin.ModelAdmin):
    form = RentalListingAdminForm
    inlines = (ListingImageInline,)
    list_display = ("title", "kind", "city", "region", "district", "owner", "price_per_day", "is_featured", "is_active")
    list_filter = ("kind", "region", "district", "is_featured", "is_active")
    search_fields = ("title", "title_ru", "title_en", "city", "address", "description", "description_ru", "description_en", "brand")
    fieldsets = (
        ("E'lon (o'zbekcha)", {"fields": ("kind", "title", "owner", "region", "district", "city", "address", "description")} ),
        ("Translations / Tarjimalar", {"fields": ("title_ru", "description_ru", "title_en", "description_en"), "classes": ("collapse",)}),
        ("Ijara shartlari", {"fields": ("price_per_day", "capacity", "bedrooms", "bathrooms", "brand", "transmission", "year")} ),
        ("Holat", {"fields": ("slug", "is_featured", "is_active")} ),
    )
    list_editable = ("is_featured", "is_active")
    prepopulated_fields = {"slug": ("title",)}

    class Media:
        js = ("core/location-select.js",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone_number", "created_at")
    search_fields = ("user__username", "user__email", "phone_number")
    readonly_fields = ("user", "phone_number", "telegram_account", "created_at")


@admin.register(HostProfile)
class HostProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "created_at")
    search_fields = ("display_name", "user__username", "user__email")
    readonly_fields = ("user", "created_at")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "email", "user", "created_at", "is_read")
    list_filter = ("is_read", "created_at")
    search_fields = ("subject", "name", "email", "message", "user__username")
    list_editable = ("is_read",)
    readonly_fields = ("user", "name", "email", "subject", "message", "created_at")


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