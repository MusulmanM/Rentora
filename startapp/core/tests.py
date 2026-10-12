from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Booking, RentalListing

User = get_user_model()


class StartAppBaseTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="demo-user", password="SafePass123!", email="demo@example.com")
        today = timezone.localdate()
        self.tomorrow = today + timedelta(days=1)
        self.day_after = today + timedelta(days=3)
        self.home = RentalListing.objects.create(
            kind=RentalListing.Kind.HOME, title="Test apartment", city="Toshkent", address="Markaz",
            description="A nice test home", price_per_day=Decimal("250000"), capacity=4,
            bedrooms=2, bathrooms=1, is_active=True,
        )
        self.car = RentalListing.objects.create(
            kind=RentalListing.Kind.CAR, title="Test car", city="Samarqand", address="Aeroport",
            description="A reliable test car", price_per_day=Decimal("300000"), capacity=5,
            brand="Chevrolet", is_active=True,
        )


class WebsiteTests(StartAppBaseTest):
    def test_home_page_renders_listings(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rentora")
        self.assertNotContains(response, "StartApp")
        self.assertContains(response, "Keyingi manzilingiz")
        self.assertContains(response, "Test apartment")
        self.assertContains(response, "Test car")

    def test_language_switcher_offers_uzbek_russian_and_english(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-language-switcher')
        self.assertContains(response, '<option value="uz">UZ</option>', html=True)
        self.assertContains(response, '<option value="ru">RU</option>', html=True)
        self.assertContains(response, '<option value="en">EN</option>', html=True)
        self.assertContains(response, 'core/i18n.js')

    def test_home_filter_by_kind(self):
        response = self.client.get(reverse("home"), {"kind": "car"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test car")
        self.assertNotContains(response, "Test apartment")

    def test_listing_detail_page(self):
        response = self.client.get(reverse("listing-detail", args=[self.home.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tavsif")
        self.assertContains(response, "250 000")

    def test_health_endpoint(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["app"], "Rentora")

    def test_registration_creates_user_and_logs_in(self):
        response = self.client.post(reverse("register"), {
            "first_name": "Aziz", "username": "aziz-123", "email": "aziz@example.com",
            "password1": "some-long-safe-password-96", "password2": "some-long-safe-password-96",
        })
        self.assertRedirects(response, reverse("home"))
        self.assertTrue(User.objects.filter(username="aziz-123").exists())
        self.assertIn("_auth_user_id", self.client.session)


class BookingTests(StartAppBaseTest):
    def test_unauthenticated_booking_redirects_to_login(self):
        response = self.client.post(reverse("create-booking", args=[self.home.slug]), {
            "check_in": self.tomorrow.isoformat(), "check_out": self.day_after.isoformat(), "guests": 2,
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertEqual(Booking.objects.count(), 0)

    def test_user_can_create_booking_and_total_is_calculated(self):
        self.client.login(username="demo-user", password="SafePass123!")
        response = self.client.post(reverse("create-booking", args=[self.home.slug]), {
            "check_in": self.tomorrow.isoformat(), "check_out": self.day_after.isoformat(), "guests": 2, "payment_method": "card",
        })
        self.assertRedirects(response, reverse("my-bookings"))
        booking = Booking.objects.get(user=self.user, listing=self.home)
        self.assertEqual(booking.total_price, Decimal("500000"))
        self.assertEqual(booking.days, 2)
        self.assertEqual(booking.payment_method, Booking.PaymentMethod.CARD)

    def test_overlapping_booking_is_rejected(self):
        Booking.objects.create(
            user=self.user, listing=self.home, check_in=self.tomorrow,
            check_out=self.day_after, guests=2, status=Booking.Status.CONFIRMED,
        )
        other = User.objects.create_user(username="other", password="SafePass123!")
        self.client.login(username="other", password="SafePass123!")
        response = self.client.post(reverse("create-booking", args=[self.home.slug]), {
            "check_in": self.tomorrow.isoformat(), "check_out": self.day_after.isoformat(), "guests": 2,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.filter(listing=self.home).count(), 1)

    def test_booking_with_too_many_guests_is_rejected(self):
        self.client.login(username="demo-user", password="SafePass123!")
        response = self.client.post(reverse("create-booking", args=[self.home.slug]), {
            "check_in": self.tomorrow.isoformat(), "check_out": self.day_after.isoformat(), "guests": 8,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_checkout_must_be_after_checkin(self):
        self.client.login(username="demo-user", password="SafePass123!")
        response = self.client.post(reverse("create-booking", args=[self.home.slug]), {
            "check_in": self.tomorrow.isoformat(), "check_out": self.tomorrow.isoformat(), "guests": 2,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_owner_can_cancel_booking(self):
        booking = Booking.objects.create(
            user=self.user, listing=self.home, check_in=self.tomorrow,
            check_out=self.day_after, guests=2,
        )
        self.client.login(username="demo-user", password="SafePass123!")
        response = self.client.post(reverse("cancel-booking", args=[booking.pk]))
        self.assertRedirects(response, reverse("my-bookings"))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_user_cannot_cancel_someone_elses_booking(self):
        booking = Booking.objects.create(
            user=self.user, listing=self.home, check_in=self.tomorrow,
            check_out=self.day_after, guests=2,
        )
        other = User.objects.create_user(username="other", password="SafePass123!")
        self.client.login(username="other", password="SafePass123!")
        response = self.client.post(reverse("cancel-booking", args=[booking.pk]))
        self.assertEqual(response.status_code, 404)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)


class ApiTests(StartAppBaseTest):
    def setUp(self):
        super().setUp()
        self.api = APIClient()

    def test_listings_api_is_public(self):
        response = self.api.get(reverse("api-listings"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_listing_api_exposes_russian_and_english_copy(self):
        response = self.api.get(reverse("api-listings"))
        self.assertEqual(response.status_code, 200)
        listing = next(item for item in response.data if item["id"] == self.home.pk)
        self.assertIn("title_ru", listing)
        self.assertIn("title_en", listing)
        self.assertIn("description_ru", listing)
        self.assertIn("description_en", listing)

    def test_booking_api_requires_login(self):
        response = self.api.post(reverse("api-bookings"), {
            "listing": self.home.pk, "check_in": self.tomorrow.isoformat(),
            "check_out": self.day_after.isoformat(), "guests": 2,
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_authenticated_booking_api_creates_booking(self):
        self.api.force_authenticate(user=self.user)
        response = self.api.post(reverse("api-bookings"), {
            "listing": self.home.pk, "check_in": self.tomorrow.isoformat(),
            "check_out": self.day_after.isoformat(), "guests": 2, "payment_method": "click",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data["total_price"]), Decimal("500000.00"))
        self.assertEqual(response.data["payment_method"], "click")

    def test_booking_api_does_not_accept_inactive_listing(self):
        self.home.is_active = False
        self.home.save()
        self.api.force_authenticate(user=self.user)
        response = self.api.post(reverse("api-bookings"), {
            "listing": self.home.pk, "check_in": self.tomorrow.isoformat(),
            "check_out": self.day_after.isoformat(), "guests": 2,
        }, format="json")
        self.assertEqual(response.status_code, 400)
