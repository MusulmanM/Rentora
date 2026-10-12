# Initial migration for StartApp's rental listings and reservations.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RentalListing",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("home", "Uylar"), ("car", "Avtomobillar")], max_length=10, verbose_name="Turi")),
                ("title", models.CharField(max_length=160, verbose_name="Nomi")),
                ("slug", models.SlugField(blank=True, max_length=180, unique=True)),
                ("city", models.CharField(max_length=80, verbose_name="Shahar")),
                ("address", models.CharField(max_length=220, verbose_name="Manzil")),
                ("description", models.TextField(verbose_name="Tavsif")),
                ("price_per_day", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="Kunlik narx (so'm)")),
                ("image_url", models.URLField(blank=True, max_length=600, verbose_name="Rasm URL")),
                ("capacity", models.PositiveSmallIntegerField(default=2, help_text="Uy uchun mehmonlar, mashina uchun o'rindiqlar.", verbose_name="Sig'im")),
                ("bedrooms", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Yotoq xonalari")),
                ("bathrooms", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Hammomlar")),
                ("brand", models.CharField(blank=True, max_length=80, verbose_name="Marka")),
                ("transmission", models.CharField(choices=[("automatic", "Avtomat"), ("manual", "Mexanika"), ("na", "Ko'rsatilmagan")], default="na", max_length=12, verbose_name="Uzatmalar qutisi")),
                ("year", models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Ishlab chiqarilgan yil")),
                ("is_featured", models.BooleanField(default=False, verbose_name="Tavsiya etilgan")),
                ("is_active", models.BooleanField(default=True, verbose_name="Faol")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "Ijara e'loni", "verbose_name_plural": "Ijara e'lonlari", "ordering": ["-is_featured", "-created_at"]},
        ),
        migrations.CreateModel(
            name="Booking",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("check_in", models.DateField(verbose_name="Boshlanish sanasi")),
                ("check_out", models.DateField(verbose_name="Tugash sanasi")),
                ("guests", models.PositiveSmallIntegerField(default=1, verbose_name="Mehmonlar / yo'lovchilar")),
                ("total_price", models.DecimalField(decimal_places=2, default=0, max_digits=14, verbose_name="Jami narx (so'm)")),
                ("status", models.CharField(choices=[("pending", "Kutilmoqda"), ("confirmed", "Tasdiqlangan"), ("cancelled", "Bekor qilingan")], default="pending", max_length=12, verbose_name="Holati")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("listing", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bookings", to="core.rentallisting", verbose_name="E'lon")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bookings", to=settings.AUTH_USER_MODEL, verbose_name="Foydalanuvchi")),
            ],
            options={"verbose_name": "Bron", "verbose_name_plural": "Bronlar", "ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="rentallisting",
            index=models.Index(fields=["kind", "city", "is_active"], name="core_rent_kind_city_active_idx"),
        ),
        migrations.AddIndex(
            model_name="booking",
            index=models.Index(fields=["listing", "check_in", "check_out", "status"], name="core_book_listing_dates_idx"),
        ),
    ]
