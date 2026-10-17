from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.http import Http404
from django.shortcuts import redirect
from django.utils.html import format_html

from .models import (
    Booking, BookingOrder, ContactMessage, District, HostProfile, Installment, ListingImage, PaymentTransaction,
    Payout, ProviderPaymentAccount, RentalListing, UserProfile, Conversation,
)
from .payouts import mark_payout_paid, mark_refunded
from .forms import DistrictSelect
from .uploads import validate_image_upload


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
        if image and not getattr(image, "_committed", False):
            return validate_image_upload(image)
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
    list_display = ("title", "kind", "city", "region", "district", "owner", "price_per_day", "availability_status", "is_featured", "is_active")
    list_filter = ("kind", "region", "district", "availability_status", "is_featured", "is_active")
    search_fields = ("title", "title_ru", "title_en", "city", "address", "description", "description_ru", "description_en", "brand")
    fieldsets = (
        ("E'lon (o'zbekcha)", {"fields": ("kind", "title", "owner", "region", "district", "city", "address", "description")} ),
        ("Translations / Tarjimalar", {"fields": ("title_ru", "description_ru", "title_en", "description_en"), "classes": ("collapse",)}),
        ("Ijara shartlari", {"fields": ("price_per_day", "capacity", "bedrooms", "bathrooms", "brand", "transmission", "year")} ),
        ("Holat", {"fields": ("slug", "availability_status", "is_featured", "is_active")} ),
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


class InstallmentInline(admin.TabularInline):
    model = Installment
    extra = 0
    can_delete = False
    fields = ("number", "due_date", "amount", "status", "method", "paid_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "listing", "user", "check_in", "check_out", "rental_unit", "payment_plan", "total_price", "status", "created_at")
    list_filter = ("status", "rental_unit", "payment_plan", "listing__kind", "created_at")
    search_fields = ("listing__title", "user__username", "user__email")
    readonly_fields = ("total_price", "created_at", "updated_at")
    list_editable = ("status",)
    inlines = (InstallmentInline,)


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

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("listing", "customer", "provider", "updated_at")
    search_fields = ("listing__title", "customer__username", "provider__username")
    readonly_fields = tuple(field.name for field in Conversation._meta.fields)



@admin.register(ProviderPaymentAccount)
class ProviderPaymentAccountAdmin(admin.ModelAdmin):
    """The head admin checks a provider's payout card and approves it."""

    list_display = ("user", "card_brand", "masked_card", "card_holder", "offer_accepted_at", "approved", "updated_at")
    list_filter = ("approved", "card_brand")
    search_fields = ("user__username", "user__host_profile__display_name", "card_last4", "card_holder")
    fields = ("user", "card_brand", "full_card_number", "card_holder", "offer_accepted_at", "approved", "updated_at")
    readonly_fields = ("user", "card_brand", "full_card_number", "card_holder", "offer_accepted_at", "updated_at")

    @admin.display(description="Karta")
    def masked_card(self, obj):
        return obj.masked_card

    @admin.display(description="Karta raqami (to'liq)")
    def full_card_number(self, obj):
        number = obj.card_number
        return " ".join(number[i:i + 4] for i in range(0, len(number), 4)) if number else "—"

    def has_add_permission(self, request):
        return False  # providers add their own card in /provider/payments/

    def save_model(self, request, obj, form, change):
        obj.approved = obj.approved and obj.has_card and obj.offer_accepted_at is not None
        super().save_model(request, obj, form, change)


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    """Queue of money to send: provider shares after the hand-over, refunds after cancellations."""

    list_display = ("booking", "provider", "status", "gross_amount", "commission_amount", "net_amount", "card", "ready_at", "completed_at")
    list_filter = ("status",)
    search_fields = ("booking__id", "provider__username", "provider__host_profile__display_name", "reference")
    readonly_fields = (
        "booking", "provider", "payment", "gross_amount", "commission_percent", "commission_amount", "net_amount",
        "status", "card_last4", "payout_card", "created_at", "ready_at", "completed_at",
    )
    fields = readonly_fields + ("reference",)
    actions = ("mark_paid", "mark_refunded")

    @admin.display(description="Karta")
    def card(self, obj):
        return f"•••• {obj.card_last4}" if obj.card_last4 else "—"

    @admin.display(description="Ijara beruvchi kartasi (to'liq)")
    def payout_card(self, obj):
        account = ProviderPaymentAccount.objects.filter(user_id=obj.provider_id).first()
        if not account or not account.has_card or obj.status != Payout.Status.READY:
            return "—"
        number = account.card_number
        return f"{' '.join(number[i:i + 4] for i in range(0, len(number), 4))} — {account.card_holder}"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Ijara beruvchiga o'tkazildi deb belgilash")
    def mark_paid(self, request, queryset):
        done = sum(1 for payout in queryset if mark_payout_paid(payout, payout.reference))
        self.message_user(request, f"{done} ta o'tkazma \"o'tkazildi\" deb belgilandi.")

    @admin.action(description="Mijozga qaytarildi deb belgilash")
    def mark_refunded(self, request, queryset):
        done = sum(1 for payout in queryset if mark_refunded(payout, payout.reference))
        self.message_user(request, f"{done} ta qaytarish belgilandi.")

# The Django admin is for the head admin only; helper admins work in /helper/.
# It has no login form of its own: core.security.SecurityMiddleware sends visitors to the
# site's rate-limited login page and answers 404 to signed-in users who are not superusers.
admin.site.site_header = "Rentora — bosh admin"
admin.site.site_title = "Rentora bosh admin"
admin.site.index_title = "Boshqaruv"


def _superuser_only(request):
    return request.user.is_active and request.user.is_superuser


def _admin_login(request, extra_context=None):
    if _superuser_only(request):
        return redirect("admin:index")
    raise Http404


admin.site.has_permission = _superuser_only
admin.site.login = _admin_login
