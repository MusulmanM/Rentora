from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Booking, BookingOrder, PaymentTransaction, RentalListing, home, car


@admin.register(RentalListing)
class RentalListingAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "city", "price_per_day", "is_featured", "is_active")
    list_filter = ("kind", "city", "is_featured", "is_active")
    search_fields = ("title", "title_ru", "title_en", "city", "address", "description", "description_ru", "description_en", "brand")
    fieldsets = (
        ("E'lon (o'zbekcha)", {"fields": ("kind", "title", "city", "address", "description")} ),
        ("Translations / Tarjimalar", {"fields": ("title_ru", "description_ru", "title_en", "description_en"), "classes": ("collapse",)}),
        ("Ijara shartlari", {"fields": ("price_per_day", "capacity", "bedrooms", "bathrooms", "brand", "transmission", "year", "image_url")} ),
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
    actions = ("accept_orders", "reject_orders", "cancel_unpaid_orders")

    @admin.action(description="Tanlangan buyurtmalarni qabul qilish va to'lovga chiqarish")
    def accept_orders(self, request, queryset):
        accepted = 0
        for order in queryset.filter(status=BookingOrder.Status.PENDING).select_related("listing"):
            try:
                order.full_clean()
            except ValidationError:
                self.message_user(
                    request,
                    f"{order.reference} buyurtmasini qabul qilib bo'lmadi: sanalar band yoki buyurtma yaroqsiz.",
                    level=messages.ERROR,
                )
                continue
            order.status = BookingOrder.Status.AWAITING_PAYMENT
            order.accepted_at = timezone.now()
            order.save(update_fields=["status", "accepted_at"])
            accepted += 1
        if accepted:
            self.message_user(request, f"{accepted} ta buyurtma qabul qilindi; mijozga to'lov ochildi.")

    @admin.action(description="Tanlangan buyurtmalarni rad etish")
    def reject_orders(self, request, queryset):
        rejected = queryset.filter(status=BookingOrder.Status.PENDING).update(status=BookingOrder.Status.REJECTED)
        self.message_user(request, f"{rejected} ta buyurtma rad etildi.")

    @admin.action(description="To'lov boshlanmagan buyurtmalarni bekor qilish")
    def cancel_unpaid_orders(self, request, queryset):
        cancelled = 0
        for order in queryset.filter(status__in=[
            BookingOrder.Status.PENDING,
            BookingOrder.Status.AWAITING_PAYMENT,
        ]):
            if order.payments.filter(state=1).exists():
                continue
            order.status = BookingOrder.Status.CANCELLED
            order.save(update_fields=["status"])
            cancelled += 1
        self.message_user(request, f"{cancelled} ta buyurtma bekor qilindi.")


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