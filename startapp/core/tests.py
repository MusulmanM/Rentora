from datetime import timedelta
from decimal import Decimal
import hashlib
from io import BytesIO
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.datastructures import MultiValueDict
from django.forms.models import inlineformset_factory
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from .admin import ListingImageForm, ListingImageInlineFormSet
from .ai_assistant import RentalAssistantError, _interpret_request
from .forms import RentalListingForm
from .models import (
    Booking, BookingOrder, ChatMessage, ContactMessage, Conversation, District,
    HostProfile, ListingImage, PendingRegistration, Region, RentalListing,
    TelegramAccount, UserProfile,
)
from .telegram import notify_booking_parties

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

    def test_chat_page_has_language_controls_and_dynamic_text_protection(self):
        provider = User.objects.create_user(username="provider", password="provider-password")
        self.home.owner = provider
        self.home.save(update_fields=["owner"])
        conversation = Conversation.objects.create(
            listing=self.home, customer=self.user, provider=provider,
        )
        ChatMessage.objects.create(
            conversation=conversation, sender=provider, text="Do not translate this message",
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("chat-room", args=[conversation.pk]))
        self.assertContains(response, "data-language-switcher")
        self.assertContains(response, "data-unread-indicator")
        self.assertContains(response, 'data-unread-endpoint="/chats/unread/"')
        self.assertContains(response, "data-no-translate")

    def test_localization_covers_navigation_chat_and_ai_dynamic_updates(self):
        localization = Path(__file__).parent / "static" / "core" / "i18n.js"
        source = localization.read_text(encoding="utf-8")
        self.assertIn('["Chatlar", "Чаты", "Chats"]', source)
        self.assertIn("data-no-translate", source)
        self.assertIn("new MutationObserver", source)
        self.assertIn("O'qilmagan yangi xabarlar", source)

    @override_settings(OPENAI_API_KEY="")
    def test_ai_chat_is_sitewide_and_explains_disabled_configuration(self):
        for path in (
            reverse("home"),
            reverse("listing-detail", args=[self.home.slug]),
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'data-ai-widget data-enabled="false"')
            self.assertContains(response, "AI yordamchi hozircha ishlamaydi")
            self.assertContains(response, "OPENAI_API_KEY")
        self.assertNotContains(self.client.get(reverse("home")), "data-ai-search")

    @override_settings(OPENAI_API_KEY="test-openai-key")
    def test_enabled_ai_chat_posts_to_existing_rental_endpoint(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-ai-widget data-enabled="true"')
        self.assertContains(response, f'action="{reverse("ai-rental-search")}"')
        self.assertContains(response, 'data-ai-conversation role="log"')
        self.assertContains(response, 'name="message"')

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
        self.assertContains(response, "data-gallery-dialog")
        self.assertContains(response, "core/listing-gallery.js")

    def test_repair_listing_is_hidden_from_home_api_and_detail(self):
        self.home.availability_status = RentalListing.AvailabilityStatus.REPAIR
        self.home.save(update_fields=["availability_status"])
        self.assertNotContains(self.client.get(reverse("home")), "Test apartment")
        api_response = self.client.get(reverse("api-listings"))
        self.assertEqual(api_response.status_code, 200)
        self.assertNotIn(self.home.pk, [item["id"] for item in api_response.json()])
        self.assertEqual(
            self.client.get(reverse("listing-detail", args=[self.home.slug])).status_code,
            404,
        )

    def test_health_endpoint(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["app"], "Rentora")

    @patch("core.ai_assistant._interpret_request")
    def test_ai_rental_search_filters_sorts_and_calculates_from_listing_price(self, interpret):
        interpret.return_value = {
            "task": "search_and_calculate",
            "kind": "home",
            "city": "Toshkent",
            "guests": 4,
            "bedrooms": None,
            "min_price": None,
            "max_price": 300000,
            "listing_search": None,
            "sort_by": "price_low",
            "rental_days": 3,
            "check_in": None,
            "check_out": None,
        }
        response = self.client.post(
            reverse("ai-rental-search"),
            data=json.dumps({
                "message": "Toshkentda 4 kishilik uy, 3 kun, arzonroq",
                "language": "ru",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["title"], "Test apartment")
        self.assertEqual(data["results"][0]["total_price"], "750000.00")
        interpret.assert_called_once_with(
            "Toshkentda 4 kishilik uy, 3 kun, arzonroq", language="ru",
        )

    @override_settings(OPENAI_API_KEY="test-openai-key")
    def test_ai_prompt_uses_the_selected_ui_language_for_assistant_replies(self):
        response_content = {"choices": [{"message": {"content": "{}"}}]}
        with patch(
            "core.ai_assistant.urlopen",
            return_value=BytesIO(json.dumps(response_content).encode("utf-8")),
        ) as openai_request:
            _interpret_request("Where can I rent?", language="ru")
        request_payload = json.loads(openai_request.call_args.args[0].data.decode("utf-8"))
        self.assertIn("language: ru", request_payload["messages"][0]["content"])

    def test_ai_rental_search_rejects_requests_outside_its_scope(self):
        with patch("core.ai_assistant._interpret_request", return_value={"task": "out_of_scope"}):
            response = self.client.post(
                reverse("ai-rental-search"),
                data=json.dumps({"message": "Tell me a joke"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])
        self.assertIn("faqat", response.json()["message"])

    def test_ai_support_answers_known_question_without_creating_admin_ticket(self):
        with patch("core.ai_assistant._interpret_request", return_value={
            "task": "support", "support_answer": "Bronni ijaraga beruvchi tasdiqlaydi.", "escalate": False,
        }):
            response = self.client.post(
                reverse("ai-rental-search"),
                data=json.dumps({"message": "Bronimni kim tasdiqlaydi?"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("tasdiqlaydi", response.json()["message"])
        self.assertFalse(response.json()["escalated"])
        self.assertFalse(ContactMessage.objects.exists())

    def test_ai_support_escalates_unknown_question_to_admin_inbox(self):
        with patch("core.ai_assistant._interpret_request", return_value={
            "task": "support", "support_answer": "Administrator ko'rib chiqadi.", "escalate": True,
        }):
            response = self.client.post(
                reverse("ai-rental-search"),
                data=json.dumps({"message": "To'lovim bo'yicha yordam kerak."}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["escalated"])
        ticket = ContactMessage.objects.get()
        self.assertEqual(ticket.subject, "AI yordam so'rovi")
        self.assertEqual(ticket.message, "To'lovim bo'yicha yordam kerak.")
        self.assertIsNone(ticket.user)

    @override_settings(OPENAI_API_KEY="test-openai-key")
    def test_ai_error_identifies_rate_limit_without_exposing_provider_payload(self):
        error = HTTPError("https://api.openai.com", 429, "Too Many Requests", {}, BytesIO(b"private response"))
        with patch("core.ai_assistant.urlopen", side_effect=error):
            with self.assertRaises(RentalAssistantError) as raised:
                _interpret_request("Toshkentda uy top")
        self.assertIn("billing", str(raised.exception))
        self.assertNotIn("private response", str(raised.exception))

    @override_settings(OPENAI_API_KEY="")
    def test_ai_rental_search_reports_missing_api_key(self):
        response = self.client.post(
            reverse("ai-rental-search"),
            data=json.dumps({"message": "Toshkentda uy top"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn("OPENAI_API_KEY", response.json()["detail"])

    def test_ai_rental_search_rejects_oversized_prompts(self):
        response = self.client.post(
            reverse("ai-rental-search"),
            data=json.dumps({"message": "uy " * 200}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("core.views.send_message")
    def test_registration_requires_and_completes_telegram_otp(self, send_telegram):
        TelegramAccount.objects.create(
            phone_number="+998901234567", telegram_user_id="70001", chat_id="70001",
        )
        response = self.client.post(reverse("register"), {
            "first_name": "Aziz", "username": "aziz-123", "email": "aziz@example.com",
            "phone_number": "+998 90 123 45 67",
            "password1": "some-long-safe-password-96", "password2": "some-long-safe-password-96",
        })
        self.assertRedirects(response, reverse("verify-registration"))
        pending = PendingRegistration.objects.get(phone_number="+998901234567")
        sent_code = send_telegram.call_args.args[1].split(": ")[1].splitlines()[0]
        response = self.client.post(reverse("verify-registration"), {"code": sent_code})
        self.assertRedirects(response, reverse("home"))
        user = User.objects.get(username="aziz-123")
        self.assertTrue(UserProfile.objects.filter(user=user, phone_number="+998901234567").exists())
        self.assertFalse(PendingRegistration.objects.filter(pk=pending.pk).exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_registration_requires_a_telegram_contact(self):
        response = self.client.post(reverse("register"), {
            "first_name": "Aziz", "username": "aziz-123", "email": "aziz@example.com",
            "phone_number": "+998 90 123 45 67",
            "password1": "some-long-safe-password-96", "password2": "some-long-safe-password-96",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Avval Telegram botga kirib")
        self.assertFalse(User.objects.filter(username="aziz-123").exists())

    @override_settings(TELEGRAM_BOT_USERNAME="rentora_example_bot")
    def test_registration_explains_telegram_contact_and_links_configured_bot(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Avval Telegram botga ulaning")
        self.assertContains(response, "Start")
        self.assertContains(response, "o'z kontaktingizni ulashing")
        self.assertContains(response, 'href="https://t.me/rentora_example_bot"')
        self.assertLess(
            response.content.index(b"Avval Telegram botga ulaning"),
            response.content.index(b'name="phone_number"'),
        )

    @override_settings(TELEGRAM_BOT_USERNAME="")
    def test_registration_explains_missing_telegram_bot_link(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bot havolasi hozircha mavjud emas")
        self.assertNotContains(response, "href=\"https://t.me/")


class ListingImageTests(StartAppBaseTest):
    def test_listing_admin_exposes_file_uploads(self):
        admin_user = User.objects.create_superuser(
            username="listing-admin", email="listing-admin@example.com", password="test-password-123",
        )
        self.client.force_login(admin_user)
        response = self.client.get(reverse("admin:core_rentallisting_add"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="images-0-image"')

    def test_uploaded_listing_photo_is_used_and_shown_in_gallery(self):
        image_data = BytesIO()
        Image.new("RGB", (2, 2), color="green").save(image_data, format="PNG")
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            uploaded_image = SimpleUploadedFile(
                "home.png",
                image_data.getvalue(),
                content_type="image/png",
            )
            photo = ListingImage.objects.create(listing=self.home, image=uploaded_image)
            self.assertEqual(self.home.image_url, photo.image.url)
            response = self.client.get(reverse("listing-detail", args=[self.home.slug]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, photo.image.url)

    def test_listing_photo_formset_rejects_more_than_ten_images(self):
        image_data = BytesIO()
        Image.new("RGB", (2, 2), color="blue").save(image_data, format="PNG")
        image_bytes = image_data.getvalue()
        formset_type = inlineformset_factory(
            RentalListing,
            ListingImage,
            form=ListingImageForm,
            formset=ListingImageInlineFormSet,
            fields=("image",),
            extra=0,
            max_num=10,
            fk_name="listing",
        )
        data = {
            "images-TOTAL_FORMS": "11",
            "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "10",
        }
        files = {
            f"images-{index}-image": SimpleUploadedFile(
                f"home-{index}.png", image_bytes, content_type="image/png",
            )
            for index in range(11)
        }
        formset = formset_type(data, files, instance=self.home, prefix="images")
        self.assertFalse(formset.is_valid())
        self.assertIn("10 ta rasm yuklash mumkin", str(formset.non_form_errors()))

    def test_admin_listing_page_shows_a_clickable_photo_preview(self):
        admin_user = User.objects.create_superuser(
            username="listing-preview-admin", email="listing-preview@example.com", password="test-password-123456",
        )
        image_data = BytesIO()
        Image.new("RGB", (2, 2), color="purple").save(image_data, format="PNG")
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            photo = ListingImage.objects.create(
                listing=self.home,
                image=SimpleUploadedFile("preview.png", image_data.getvalue(), content_type="image/png"),
            )
            self.client.force_login(admin_user)
            response = self.client.get(reverse("admin:core_rentallisting_change", args=[self.home.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "admin-image-preview")
            self.assertContains(response, photo.image.url)


class AccountLocationAndProviderTests(StartAppBaseTest):
    def _link_telegram_phone(self, phone_number="+998901234567", telegram_id="70001"):
        account = TelegramAccount.objects.create(
            phone_number=phone_number,
            telegram_user_id=telegram_id,
            chat_id=telegram_id,
        )
        UserProfile.objects.create(
            user=self.user,
            phone_number=phone_number,
            telegram_account=account,
        )
        return account

    def _png_upload(self, name="listing.png"):
        image_data = BytesIO()
        Image.new("RGB", (4, 4), color="green").save(image_data, format="PNG")
        return SimpleUploadedFile(name, image_data.getvalue(), content_type="image/png")

    def test_uzbekistan_reference_data_includes_all_regions_and_districts(self):
        self.assertEqual(Region.objects.count(), 14)
        self.assertEqual(District.objects.count(), 209)

    def test_demo_seed_assigns_region_and_district(self):
        call_command("seed_demo", stdout=StringIO())
        listing = RentalListing.objects.get(title="Yorug' va zamonaviy apartament")
        self.assertEqual(listing.region_id, 14)
        self.assertIsNotNone(listing.district_id)

    def test_district_api_filters_by_region(self):
        region = Region.objects.get(pk=14)
        expected = District.objects.filter(region=region).count()
        response = self.client.get(reverse("api-districts"), {"region_id": region.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), expected)
        self.assertTrue(all(row["region_id"] == region.pk for row in response.json()["results"]))

    def test_home_filters_listings_by_selected_region_and_district(self):
        region = Region.objects.get(pk=14)
        district = District.objects.filter(region=region).first()
        self.home.region = region
        self.home.district = district
        self.home.city = district.name_uz
        self.home.save()
        response = self.client.get(reverse("home"), {
            "region": region.pk, "district": district.pk,
        })
        self.assertContains(response, "Test apartment")
        self.assertNotContains(response, "Test car")
        self.assertContains(response, 'data-location-region')

    def test_telegram_webhook_links_only_the_sender_own_contact(self):
        update = {
            "update_id": 1,
            "message": {
                "from": {"id": 70001},
                "chat": {"id": 70001, "type": "private"},
                "contact": {"user_id": 70001, "phone_number": "+998 90 123 45 67"},
            },
        }
        with override_settings(TELEGRAM_WEBHOOK_SECRET="webhook-secret"), patch("core.views.send_message"):
            response = self.client.post(
                reverse("telegram-webhook"),
                data=json.dumps(update),
                content_type="application/json",
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="webhook-secret",
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(TelegramAccount.objects.filter(
            phone_number="+998901234567", telegram_user_id="70001",
        ).exists())

    @patch("core.telegram._call")
    def test_telegram_start_greets_user_and_requests_contact(self, telegram_call):
        update = {
            "message": {
                "text": "/start",
                "from": {"id": 70001},
                "chat": {"id": 70001, "type": "private"},
            },
        }
        with override_settings(TELEGRAM_WEBHOOK_SECRET="webhook-secret"):
            response = self.client.post(
                reverse("telegram-webhook"),
                data=json.dumps(update),
                content_type="application/json",
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="webhook-secret",
            )
        self.assertEqual(response.status_code, 200)
        telegram_call.assert_called_once()
        method, payload = telegram_call.call_args.args
        self.assertEqual(method, "sendMessage")
        self.assertEqual(payload["chat_id"], "70001")
        self.assertTrue(payload["text"].startswith("Hi!"))
        self.assertTrue(payload["reply_markup"]["keyboard"][0][0]["request_contact"])

    def test_telegram_webhook_rejects_wrong_secret_and_shared_contact(self):
        denied = self.client.post(
            reverse("telegram-webhook"), data="{}", content_type="application/json",
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="wrong",
        )
        self.assertEqual(denied.status_code, 403)
        update = {
            "message": {
                "from": {"id": 70001},
                "chat": {"id": 70001, "type": "private"},
                "contact": {"user_id": 99999, "phone_number": "+998 90 123 45 67"},
            },
        }
        with override_settings(TELEGRAM_WEBHOOK_SECRET="webhook-secret"):
            response = self.client.post(
                reverse("telegram-webhook"), data=json.dumps(update), content_type="application/json",
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="webhook-secret",
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TelegramAccount.objects.exists())

    @patch("core.views.send_message")
    def test_existing_user_can_verify_phone_then_become_provider(self, send_telegram):
        account = TelegramAccount.objects.create(
            phone_number="+998901234567", telegram_user_id="70001", chat_id="70001",
        )
        self.client.force_login(self.user)
        response = self.client.post(reverse("verify-profile-phone"), {
            "phone_number": "+998 90 123 45 67",
        })
        self.assertRedirects(response, reverse("confirm-profile-phone"))
        sent_code = send_telegram.call_args.args[1].split(": ")[1].splitlines()[0]
        response = self.client.post(reverse("confirm-profile-phone"), {"code": sent_code})
        self.assertRedirects(response, reverse("profile"))
        self.assertTrue(UserProfile.objects.filter(user=self.user, telegram_account=account).exists())

        response = self.client.post(reverse("provider-onboarding"), {"display_name": "Aziz uy ijarasi"})
        self.assertRedirects(response, reverse("provider-dashboard"))
        self.assertTrue(HostProfile.objects.filter(user=self.user).exists())

    def test_unverified_user_cannot_start_provider_onboarding(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("provider-onboarding"), {"display_name": "Aziz"})
        self.assertRedirects(response, reverse("profile"))
        self.assertFalse(HostProfile.objects.filter(user=self.user).exists())

    def test_provider_can_create_listing_with_location_and_uploaded_photo(self):
        self._link_telegram_phone()
        HostProfile.objects.create(user=self.user, display_name="Aziz ijarasi")
        self.client.force_login(self.user)
        region = Region.objects.get(pk=13)
        district = District.objects.filter(region=region).first()
        listing_data = {
            "kind": "home",
            "title": "Xorazmdagi yangi uy",
            "title_ru": "",
            "title_en": "",
            "region": region.pk,
            "district": district.pk,
            "address": "Markaziy ko'cha",
            "description": "Yangi e'lon uchun batafsil tavsif.",
            "description_ru": "",
            "description_en": "",
            "price_per_day": "180000",
            "capacity": "4",
            "bedrooms": "2",
            "bathrooms": "1",
            "brand": "",
            "transmission": "na",
            "year": "",
            "image_uploads": self._png_upload(),
        }
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(reverse("provider-create-listing"), listing_data)
            self.assertRedirects(response, reverse("provider-dashboard"))
            listing = RentalListing.objects.get(title="Xorazmdagi yangi uy")
            self.assertEqual(listing.owner, self.user)
            self.assertEqual(listing.region, region)
            self.assertEqual(listing.district, district)
            self.assertEqual(listing.city, district.name_uz)
            self.assertEqual(listing.images.count(), 1)
            self.assertTrue(listing.images.first().image.storage.exists(listing.images.first().image.name))

    def test_provider_listing_form_rejects_more_than_ten_photos(self):
        region = Region.objects.get(pk=14)
        district = District.objects.filter(region=region).first()
        upload = SimpleUploadedFile("photo.png", b"x", content_type="image/png")
        files = MultiValueDict({"image_uploads": [upload] * 11})
        form = RentalListingForm(
            data={
                "kind": "home", "title": "Ko'p rasm", "region": region.pk,
                "district": district.pk, "address": "Markaz",
                "description": "Batafsil tavsif.", "price_per_day": "100000",
            },
            files=files,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("10 ta rasm yuklash mumkin", str(form.errors["image_uploads"]))

    def test_contact_form_saves_message_for_admin(self):
        response = self.client.post(reverse("contact-admin"), {
            "name": "Aziz", "email": "aziz@example.com",
            "subject": "Yordam", "message": "Savolim bor.",
        })
        self.assertRedirects(response, reverse("contact-admin"))
        contact = ContactMessage.objects.get(subject="Yordam")
        self.assertEqual(contact.user, None)
        admin_user = User.objects.create_superuser(
            username="contact-admin", email="admin@example.com", password="test-password-123456",
        )
        self.client.force_login(admin_user)
        admin_response = self.client.get(reverse("admin:core_contactmessage_changelist"))
        self.assertEqual(admin_response.status_code, 200)
        self.assertContains(admin_response, "Yordam")


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
            "check_in": self.tomorrow.isoformat(), "check_out": self.day_after.isoformat(), "guests": 2, "payment_method": "cash",
        })
        self.assertRedirects(response, reverse("my-bookings"))
        booking = Booking.objects.get(user=self.user, listing=self.home)
        self.assertEqual(booking.total_price, Decimal("500000"))
        self.assertEqual(booking.days, 2)
        self.assertEqual(booking.payment_method, Booking.PaymentMethod.CASH)
        self.assertEqual(BookingOrder.objects.count(), 0)

    def test_listing_owner_cannot_book_own_listing(self):
        self.home.owner = self.user
        self.home.save(update_fields=["owner"])
        self.client.force_login(self.user)
        response = self.client.post(reverse("create-booking", args=[self.home.slug]), {
            "check_in": self.tomorrow.isoformat(), "check_out": self.day_after.isoformat(),
            "guests": 2, "payment_method": "cash",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(BookingOrder.objects.count(), 0)

    @override_settings(
        CLICK_SERVICE_ID="service-test",
        CLICK_MERCHANT_ID="merchant-test",
        CLICK_SECRET_KEY="secret-test",
        CLICK_CHECKOUT_BASE_URL="https://my.click.uz/services/pay",
    )
    def test_online_booking_starts_payment_automatically_without_admin(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("create-booking", args=[self.home.slug]), {
            "check_in": self.tomorrow.isoformat(), "check_out": self.day_after.isoformat(),
            "guests": 2, "payment_method": "click",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse(
            "pay-booking-order",
            args=[BookingOrder.objects.get().pk],
        ))
        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("service_id=service-test", response.url)
        order = BookingOrder.objects.get(user=self.user, listing=self.home)
        self.assertEqual(order.status, BookingOrder.Status.AWAITING_PAYMENT)
        self.assertEqual(order.total_price, Decimal("500000"))
        self.assertEqual(Booking.objects.count(), 0)
        response = self.client.get(reverse("home"), {
            "kind": "home",
            "check_in": self.tomorrow.isoformat(),
            "check_out": self.day_after.isoformat(),
        })
        self.assertNotContains(response, "Test apartment")

    def test_admin_cannot_approve_or_reject_online_orders(self):
        order = BookingOrder.objects.create(
            user=self.user, listing=self.home, check_in=self.tomorrow,
            check_out=self.day_after, guests=2, payment_method=Booking.PaymentMethod.PAYME,
        )
        admin_user = User.objects.create_superuser(
            username="site-admin", email="admin@example.com", password="admin-test-password-123",
        )
        self.client.force_login(admin_user)
        response = self.client.get(reverse("admin:core_bookingorder_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "accept_orders")
        order.refresh_from_db()
        self.assertEqual(order.status, BookingOrder.Status.AWAITING_PAYMENT)
        self.assertEqual(Booking.objects.count(), 0)

    def test_new_online_orders_are_ready_for_payment_without_admin(self):
        order = BookingOrder.objects.create(
            user=self.user, listing=self.home, check_in=self.tomorrow,
            check_out=self.day_after, guests=2, payment_method=Booking.PaymentMethod.CLICK,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("my-bookings"))
        self.assertEqual(order.status, BookingOrder.Status.AWAITING_PAYMENT)
        self.assertContains(response, "To'lash")
        self.assertEqual(Booking.objects.count(), 0)

    @override_settings(
        CLICK_SERVICE_ID="service-test",
        CLICK_MERCHANT_ID="merchant-test",
        CLICK_SECRET_KEY="secret-test",
        CLICK_CHECKOUT_BASE_URL="https://my.click.uz/services/pay",
    )
    def test_online_order_redirects_to_click_without_creating_booking(self):
        order = BookingOrder.objects.create(
            user=self.user, listing=self.home, check_in=self.tomorrow,
            check_out=self.day_after, guests=2, payment_method=Booking.PaymentMethod.CARD,
            status=BookingOrder.Status.AWAITING_PAYMENT,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("pay-booking-order", args=[order.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("service_id=service-test", response.url)
        self.assertIn(str(order.reference), response.url)
        self.assertEqual(Booking.objects.count(), 0)

    @override_settings(CLICK_SERVICE_ID="123", CLICK_SECRET_KEY="secret")
    def test_click_callbacks_create_booking_only_after_successful_payment(self):
        order = BookingOrder.objects.create(
            user=self.user, listing=self.home, check_in=self.tomorrow,
            check_out=self.day_after, guests=2, payment_method=Booking.PaymentMethod.CLICK,
            status=BookingOrder.Status.AWAITING_PAYMENT,
        )
        payload = {
            "click_trans_id": "click-transaction-1",
            "service_id": "123",
            "merchant_trans_id": str(order.reference),
            "amount": "500000",
            "action": "0",
            "sign_time": "2026-10-12 12:00:00",
        }
        payload["sign_string"] = hashlib.md5(
            f"{payload['click_trans_id']}{payload['service_id']}secret"
            f"{payload['merchant_trans_id']}{payload['amount']}{payload['action']}{payload['sign_time']}".encode()
        ).hexdigest()
        prepare = self.client.post(reverse("click-payment-callback"), payload)
        self.assertEqual(prepare.json()["error"], 0)
        self.assertEqual(Booking.objects.count(), 0)

        self.home.price_per_day = Decimal("400000")
        self.home.save(update_fields=["price_per_day"])
        payload.update({
            "action": "1",
            "merchant_prepare_id": prepare.json()["merchant_prepare_id"],
            "error": "0",
        })
        payload["sign_string"] = hashlib.md5(
            f"{payload['click_trans_id']}{payload['service_id']}secret"
            f"{payload['merchant_trans_id']}{payload['amount']}{payload['action']}{payload['sign_time']}".encode()
        ).hexdigest()
        complete = self.client.post(reverse("click-payment-callback"), payload)
        self.assertEqual(complete.json()["error"], 0)
        self.assertEqual(Booking.objects.count(), 1)
        order.refresh_from_db()
        self.assertEqual(order.status, BookingOrder.Status.PAID)
        self.assertEqual(order.booking.payment_method, Booking.PaymentMethod.CLICK)
        self.assertEqual(order.booking.total_price, Decimal("500000"))

    @override_settings(PAYME_MERCHANT_AUTHORIZATION="Basic test-key")
    def test_payme_callback_creates_booking_on_performed_transaction(self):
        order = BookingOrder.objects.create(
            user=self.user, listing=self.home, check_in=self.tomorrow,
            check_out=self.day_after, guests=2, payment_method=Booking.PaymentMethod.PAYME,
            status=BookingOrder.Status.AWAITING_PAYMENT,
        )

        def callback(method, params):
            return self.client.post(
                reverse("payme-payment-callback"),
                data=json.dumps({"id": 1, "method": method, "params": params}),
                content_type="application/json",
                HTTP_AUTHORIZATION="Basic test-key",
            )

        created = callback("CreateTransaction", {
            "id": "payme-transaction-1",
            "time": 1791806400000,
            "amount": 50000000,
            "account": {"order_id": str(order.reference)},
        })
        self.assertEqual(created.json()["result"]["state"], 1)
        self.assertEqual(Booking.objects.count(), 0)
        performed = callback("PerformTransaction", {"id": "payme-transaction-1"})
        self.assertEqual(performed.json()["result"]["state"], 2)
        self.assertEqual(Booking.objects.count(), 1)
        order.refresh_from_db()
        self.assertEqual(order.status, BookingOrder.Status.PAID)
        self.assertEqual(order.booking.payment_method, Booking.PaymentMethod.PAYME)

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


class ProviderWorkflowTests(StartAppBaseTest):
    def setUp(self):
        super().setUp()
        self.provider = User.objects.create_user(username="provider", password="test-pass")
        HostProfile.objects.create(user=self.provider, display_name="Provider")
        self.home.owner = self.provider
        self.home.save(update_fields=["owner"])
        self.booking = Booking.objects.create(
            user=self.user, listing=self.home, check_in=self.tomorrow,
            check_out=self.day_after, guests=2,
        )

    def test_provider_must_accept_before_marking_listing_handed_over(self):
        self.client.force_login(self.provider)
        confirm_url = reverse("provider-booking-action", args=[self.booking.pk, "confirm"])
        handover_url = reverse("provider-booking-action", args=[self.booking.pk, "handover"])
        response = self.client.post(handover_url)
        self.assertRedirects(response, reverse("provider-dashboard"))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PENDING)

        response = self.client.post(confirm_url)
        self.assertRedirects(response, reverse("provider-dashboard"))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

        response = self.client.post(handover_url)
        self.assertRedirects(response, reverse("provider-dashboard"))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.HANDED_OVER)

    def test_booking_is_hidden_from_other_users_but_visible_to_renter_and_owner(self):
        outsider = User.objects.create_user(username="other-user", password="test-pass")
        self.client.force_login(outsider)
        self.assertNotContains(self.client.get(reverse("home")), "Test apartment")
        self.assertEqual(
            self.client.get(reverse("listing-detail", args=[self.home.slug])).status_code,
            404,
        )
        public_listings = self.client.get(reverse("api-listings")).json()
        self.assertNotIn(self.home.pk, [item["id"] for item in public_listings])
        self.assertEqual(
            self.client.get(reverse("api-listing-detail", args=[self.home.pk])).status_code,
            404,
        )
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.get(reverse("listing-detail", args=[self.home.slug])).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("api-listing-detail", args=[self.home.pk])).status_code,
            200,
        )
        self.client.force_login(self.provider)
        self.assertEqual(
            self.client.get(reverse("listing-detail", args=[self.home.slug])).status_code,
            200,
        )

    def test_non_owner_cannot_change_listing_availability(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("provider-listing-availability", args=[self.home.pk]),
            {"status": RentalListing.AvailabilityStatus.REPAIR},
        )
        self.assertEqual(response.status_code, 404)
        self.home.refresh_from_db()
        self.assertEqual(self.home.availability_status, RentalListing.AvailabilityStatus.ACTIVE)

    def test_booking_telegram_notice_includes_listing_image_price_duration_total_and_link(self):
        self.home.legacy_image_url = "https://rentora.example/listing.jpg"
        self.home.save(update_fields=["legacy_image_url"])
        for user, phone, telegram_id in (
            (self.user, "+998901234567", "1001"),
            (self.provider, "+998901234568", "1002"),
        ):
            account = TelegramAccount.objects.create(
                phone_number=phone, telegram_user_id=telegram_id, chat_id=telegram_id,
            )
            UserProfile.objects.create(user=user, phone_number=phone, telegram_account=account)
        with patch("core.telegram._call") as telegram_call:
            notify_booking_parties(self.booking.pk, "requested", "https://rentora.example")
        self.assertEqual(telegram_call.call_count, 2)
        for call in telegram_call.call_args_list:
            method, payload = call.args
            self.assertEqual(method, "sendPhoto")
            self.assertIn("Test apartment", payload["caption"])
            self.assertIn("250,000 so'm / kun", payload["caption"])
            self.assertIn("2 kun", payload["caption"])
            self.assertIn("500,000 so'm", payload["caption"])
            self.assertIn("Bron so'rovi:", payload["caption"])
            self.assertIn("https://rentora.example/listing/test-apartment", payload["caption"])


class ChatTests(StartAppBaseTest):
    def setUp(self):
        super().setUp()
        self.provider = User.objects.create_user(username="provider", password="test-pass")
        HostProfile.objects.create(user=self.provider, display_name="Provider")
        self.home.owner = self.provider
        self.home.save(update_fields=["owner"])
        self.conversation = Conversation.objects.create(
            listing=self.home, customer=self.user, provider=self.provider,
        )

    def test_conversation_participants_can_exchange_text_messages(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("chat-room", args=[self.conversation.pk]), {
            "text": "Salom, e'lon hali bo'shmi?",
        })
        self.assertRedirects(response, reverse("chat-room", args=[self.conversation.pk]))
        self.assertEqual(ChatMessage.objects.get().text, "Salom, e'lon hali bo'shmi?")
        messages_response = self.client.get(
            reverse("chat-messages-api", args=[self.conversation.pk]), {"after": 0},
        )
        self.assertEqual(messages_response.status_code, 200)
        self.assertTrue(messages_response.json()["messages"][0]["mine"])
        self.client.force_login(self.provider)
        self.assertContains(self.client.get(reverse("chat-room", args=[self.conversation.pk])), "Salom")

    def test_non_participant_cannot_read_chat_or_media(self):
        message = ChatMessage.objects.create(
            conversation=self.conversation, sender=self.user, text="Private",
            attachment="chat/private/image.png", attachment_type=ChatMessage.AttachmentType.IMAGE,
        )
        outsider = User.objects.create_user(username="outsider", password="test-pass")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("chat-room", args=[self.conversation.pk])).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("chat-messages-api", args=[self.conversation.pk])).status_code,
            404,
        )
        self.assertEqual(self.client.get(reverse("chat-media", args=[message.pk])).status_code, 404)

    def test_unread_indicator_tracks_each_participant_and_excludes_own_messages(self):
        incoming = ChatMessage.objects.create(
            conversation=self.conversation, sender=self.provider, text="New details",
        )
        unread_url = reverse("chat-unread-status")
        self.client.force_login(self.user)
        self.assertTrue(self.client.get(unread_url).json()["has_unread"])
        inbox = self.client.get(reverse("chat-inbox"))
        markup = inbox.content.decode()
        self.assertRegex(markup, r'data-unread-indicator[^>]*aria-label="[^"]+"')
        self.assertNotRegex(markup, r'data-unread-indicator[^>]*\shidden')

        room = self.client.get(reverse("chat-room", args=[self.conversation.pk]))
        self.assertEqual(room.status_code, 200)
        self.conversation.refresh_from_db()
        self.assertGreaterEqual(self.conversation.customer_last_read_message_id, incoming.pk)
        self.assertFalse(self.client.get(unread_url).json()["has_unread"])

        own_message = ChatMessage.objects.create(
            conversation=self.conversation, sender=self.user, text="My reply",
        )
        self.assertFalse(self.client.get(unread_url).json()["has_unread"])
        self.client.force_login(self.provider)
        self.assertTrue(self.client.get(unread_url).json()["has_unread"])
        self.client.get(reverse("chat-room", args=[self.conversation.pk]))
        self.conversation.refresh_from_db()
        self.assertGreaterEqual(self.conversation.provider_last_read_message_id, own_message.pk)
        self.assertFalse(self.client.get(unread_url).json()["has_unread"])

    def test_polling_new_chat_messages_marks_them_read(self):
        ChatMessage.objects.create(
            conversation=self.conversation, sender=self.provider, text="Available tomorrow",
        )
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("chat-messages-api", args=[self.conversation.pk]), {"after": 0},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["messages"]), 1)
        self.assertFalse(self.client.get(reverse("chat-unread-status")).json()["has_unread"])


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

    def test_authenticated_online_booking_api_creates_payment_ready_order(self):
        self.api.force_authenticate(user=self.user)
        response = self.api.post(reverse("api-bookings"), {
            "listing": self.home.pk, "check_in": self.tomorrow.isoformat(),
            "check_out": self.day_after.isoformat(), "guests": 2, "payment_method": "click",
        }, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(Decimal(response.data["total_price"]), Decimal("500000.00"))
        self.assertEqual(response.data["payment_method"], "click")
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(BookingOrder.objects.get().status, BookingOrder.Status.AWAITING_PAYMENT)

    def test_bookings_api_serializes_online_order_statuses(self):
        order = BookingOrder.objects.create(
            user=self.user, listing=self.home, check_in=self.tomorrow,
            check_out=self.day_after, guests=2, payment_method=Booking.PaymentMethod.CLICK,
            status=BookingOrder.Status.AWAITING_PAYMENT,
        )
        self.api.force_authenticate(user=self.user)
        response = self.api.get(reverse("api-bookings"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["id"], order.pk)
        self.assertEqual(response.data[0]["status"], BookingOrder.Status.AWAITING_PAYMENT)

    def test_booking_api_does_not_accept_inactive_listing(self):
        self.home.is_active = False
        self.home.save()
        self.api.force_authenticate(user=self.user)
        response = self.api.post(reverse("api-bookings"), {
            "listing": self.home.pk, "check_in": self.tomorrow.isoformat(),
            "check_out": self.day_after.isoformat(), "guests": 2,
        }, format="json")
        self.assertEqual(response.status_code, 400)
