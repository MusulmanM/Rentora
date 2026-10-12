from django.contrib import admin
from .models import Booking, RentalListing, home, car


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