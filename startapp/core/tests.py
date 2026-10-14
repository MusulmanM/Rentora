from datetime import timedelta
from decimal import Decimal
import hashlib
from io import BytesIO
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.core.cache import cache
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
    HostProfile, ListingImage, ListingReview, PendingRegistration, Region, RentalListing,
    TelegramAccount, UserProfile,
)
from .telegram import notify_booking_parties

User = get_user_model()


# Keep tests offline and independent of a developer's local .env secrets.
@override_settings(TELEGRAM_BOT_TOKEN="", GEMINI_API_KEY="", PUBLIC_SITE_URL="")
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

    @override_settings(GEMINI_API_KEY="")
    def test_ai_chat_is_sitewide_and_explains_disabled_configuration(self):
        for path in (
            reverse("home"),
            reverse("listing-detail", args=[self.home.slug]),
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'data-ai-widget data-enabled="false"')
            self.assertContains(response, "AI yordamchi hozircha ishlamaydi")
            self.assertContains(response, "GEMINI_API_KEY")
        self.assertNotContains(self.client.get(reverse("home")), "data-ai-search")

    @override_settings(GEMINI_API_KEY="test-gemini-key")
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

    @override_settings(GEMINI_API_KEY="test-gemini-key")
    def test_ai_prompt_uses_the_selected_ui_language_for_assistant_replies(self):
        response_content = {"choices": [{"message": {"content": "{}"}}]}
        with patch(
            "core.gemini.urlopen",
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

    @override_settings(GEMINI_API_KEY="test-gemini-key")
    def test_ai_error_identifies_rate_limit_without_exposing_provider_payload(self):
        error = HTTPError("https://generativelanguage.googleapis.com", 429, "Too Many Requests", {}, BytesIO(b"private response"))
        with patch("core.gemini.urlopen", side_effect=error):
            with self.assertRaises(RentalAssistantError) as raised:
                _interpret_request("Toshkentda uy top")
        self.assertIn("limiti", str(raised.exception))
        self.assertNotIn("private response", str(raised.exception))

    @override_settings(GEMINI_API_KEY="test-gemini-key", GEMINI_MODEL="main-model", GEMINI_FALLBACK_MODELS=["backup-model"])
    def test_gemini_falls_back_to_next_model_and_remembers_exhausted_quota(self):
        cache.clear()
        ok = {"choices": [{"message": {"content": "{}"}}]}
        quota = HTTPError(
            "https://generativelanguage.googleapis.com", 429, "Too Many Requests", {},
            BytesIO(b"Quota exceeded. Please retry in 14h49m53.7s."),
        )
        with patch("core.gemini.urlopen", side_effect=[quota, BytesIO(json.dumps(ok).encode())]) as request:
            _interpret_request("Toshkentda uy top")
        used = [json.loads(call.args[0].data)["model"] for call in request.call_args_list]
        self.assertEqual(used, ["main-model", "backup-model"])

        # The exhausted model is skipped until its quota resets.
        with patch("core.gemini.urlopen", return_value=BytesIO(json.dumps(ok).encode())) as request:
            _interpret_request("Toshkentda uy top")
        self.assertEqual(json.loads(request.call_args.args[0].data)["model"], "backup-model")
        cache.clear()

    @override_settings(GEMINI_API_KEY="")
    def test_ai_rental_search_reports_missing_api_key(self):
        response = self.client.post(
            reverse("ai-rental-search"),
            data=json.dumps({"message": "Toshkentda uy top"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.json()["detail"])

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
        self.assertEqual(response.status_code, 200)  # Logo and company phone are required.
        self.assertFalse(HostProfile.objects.filter(user=self.user).exists())
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(reverse("provider-onboarding"), {
                "display_name": "Aziz uy ijarasi", "phone_number": "90 111 22 33", "logo": self._png_upload("aziz-logo.png"),
            })
            self.assertRedirects(response, reverse("provider-dashboard"))
            host = HostProfile.objects.get(user=self.user)
            self.assertEqual(host.phone_number, "+998901112233")
            # The uploaded name is never kept: files get a random name.
            self.assertTrue(host.logo.name.startswith("host-logos/"))
            self.assertNotIn("aziz", host.logo.name)

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

    @override_settings(PUBLIC_SITE_URL="")
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


    def _link_both_telegrams(self):
        for user, phone, telegram_id in (
            (self.user, "+998901234567", "1001"),
            (self.provider, "+998901234568", "1002"),
        ):
            account = TelegramAccount.objects.create(
                phone_number=phone, telegram_user_id=telegram_id, chat_id=telegram_id,
            )
            UserProfile.objects.create(user=user, phone_number=phone, telegram_account=account)

    def _add_photo(self, fmt="PNG", name="photo.png"):
        data = BytesIO()
        Image.new("RGB", (40, 30), color="blue").save(data, format=fmt)
        return ListingImage.objects.create(
            listing=self.home, image=SimpleUploadedFile(name, data.getvalue()),
        )

    @override_settings(PUBLIC_SITE_URL="")
    def test_uploaded_photo_is_uploaded_to_telegram_as_jpeg_instead_of_a_url(self):
        self._link_both_telegrams()
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            self._add_photo()
            with patch("core.telegram._call_multipart") as upload, patch("core.telegram._call") as call:
                notify_booking_parties(self.booking.pk, "requested", "http://127.0.0.1:8000")
        self.assertEqual(upload.call_count, 2)
        call.assert_not_called()
        method, fields, file_field, filename, content = upload.call_args.args
        self.assertEqual((method, file_field, filename), ("sendPhoto", "photo", "listing.jpg"))
        self.assertTrue(content.startswith(b"\xff\xd8"))  # JPEG magic bytes
        self.assertIn("Test apartment", fields["caption"])

    @override_settings(PUBLIC_SITE_URL="")
    def test_failed_photo_upload_still_delivers_the_text_notice(self):
        from .telegram import TelegramError
        self._link_both_telegrams()
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            self._add_photo()
            with patch("core.telegram._call_multipart", side_effect=TelegramError("rejected")), \
                    patch("core.telegram._call") as call:
                notify_booking_parties(self.booking.pk, "requested")
        self.assertEqual(call.call_count, 2)
        texts = {sent.args[1]["chat_id"]: sent.args[1]["text"] for sent in call.call_args_list}
        self.assertTrue(all(sent.args[0] == "sendMessage" for sent in call.call_args_list))
        self.assertIn("Yangi bron so'rovi", texts["1002"])
        self.assertIn("ijaraga beruvchiga yuborildi", texts["1001"])

    def test_provider_can_reject_a_pending_booking_and_both_sides_are_notified(self):
        self.client.force_login(self.provider)
        with patch("core.views.notify_booking_parties") as notify, self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("provider-booking-action", args=[self.booking.pk, "reject"]))
        self.assertRedirects(response, reverse("provider-dashboard"))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)
        self.assertEqual(notify.call_args.args[:2], (self.booking.pk, "rejected"))

    def test_customer_cannot_reject_through_provider_action(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("provider-booking-action", args=[self.booking.pk, "reject"]))
        self.assertEqual(response.status_code, 404)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PENDING)

    def test_cash_booking_without_linked_telegram_warns_the_customer(self):
        self.client.force_login(self.user)
        self.booking.delete()
        with patch("core.views.notify_booking_parties"):
            response = self.client.post(reverse("create-booking", args=[self.home.slug]), {
                "check_in": self.tomorrow, "check_out": self.day_after, "guests": 1, "payment_method": "cash",
            }, follow=True)
        self.assertContains(response, "Telegram xabarlarini olish uchun")


class ProviderListingFormTests(StartAppBaseTest):
    def setUp(self):
        super().setUp()
        self.provider = User.objects.create_user(username="host", password="test-pass")
        HostProfile.objects.create(user=self.provider, display_name="Host")
        self.client.force_login(self.provider)
        self.region = Region.objects.get(pk=14)
        self.district = District.objects.filter(region=self.region).first()
        self.media = TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media.name, GEMINI_API_KEY="")
        self.media_override.enable()

    def tearDown(self):
        self.media_override.disable()
        self.media.cleanup()
        super().tearDown()

    def _png(self, name="p.png"):
        data = BytesIO()
        Image.new("RGB", (4, 4), color="red").save(data, format="PNG")
        return SimpleUploadedFile(name, data.getvalue(), content_type="image/png")

    def _common(self, kind):
        return {
            "kind": kind, "title": "Yangi e'lon", "title_ru": "", "title_en": "",
            "region": self.region.pk, "district": self.district.pk, "address": "Markaz",
            "description": "Tavsif", "description_ru": "", "description_en": "",
            "price_per_day": "200000", "capacity": "4", "image_uploads": self._png(),
        }

    def test_listing_type_is_chosen_before_any_field_is_shown(self):
        response = self.client.get(reverse("provider-create-listing"))
        self.assertContains(response, "Nimani ijaraga berasiz?")
        self.assertContains(response, "?kind=home")
        self.assertContains(response, "?kind=car")
        self.assertNotContains(response, 'name="title"')

    def test_home_form_shows_only_home_fields(self):
        response = self.client.get(reverse("provider-create-listing"), {"kind": "home"})
        self.assertContains(response, 'name="bedrooms"')
        self.assertContains(response, 'name="bathrooms"')
        self.assertNotContains(response, 'name="brand"')
        self.assertNotContains(response, 'name="transmission"')
        self.assertContains(response, "Mehmonlar soni")

    def test_car_form_shows_only_car_fields(self):
        response = self.client.get(reverse("provider-create-listing"), {"kind": "car"})
        self.assertContains(response, 'name="brand"')
        self.assertContains(response, 'name="year"')
        self.assertNotContains(response, 'name="bedrooms"')
        self.assertContains(response, "O&#x27;rindiqlar soni")
        self.assertNotContains(response, 'value="na"')

    def test_car_listing_requires_car_details_and_ignores_home_fields(self):
        response = self.client.post(reverse("provider-create-listing"), self._common("car"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RentalListing.objects.filter(title="Yangi e'lon").exists())
        data = {**self._common("car"), "brand": "Chevrolet", "transmission": "automatic", "year": "2022", "bedrooms": "3"}
        response = self.client.post(reverse("provider-create-listing"), data)
        self.assertRedirects(response, reverse("provider-dashboard"))
        listing = RentalListing.objects.get(title="Yangi e'lon")
        self.assertEqual((listing.kind, listing.brand, listing.year, listing.bedrooms), ("car", "Chevrolet", 2022, None))

    def test_home_listing_clears_car_fields(self):
        data = {**self._common("home"), "bedrooms": "2", "bathrooms": "1", "brand": "BMW", "year": "2020"}
        self.assertRedirects(self.client.post(reverse("provider-create-listing"), data), reverse("provider-dashboard"))
        listing = RentalListing.objects.get(title="Yangi e'lon")
        self.assertEqual((listing.brand, listing.year, listing.transmission), ("", None, "na"))

    def test_owner_can_edit_listing_and_remove_a_photo_but_others_cannot(self):
        data = {**self._common("home"), "bedrooms": "2", "bathrooms": "1"}
        self.client.post(reverse("provider-create-listing"), data)
        listing = RentalListing.objects.get(title="Yangi e'lon")
        ListingImage.objects.create(listing=listing, image=self._png("second.png"))
        first_photo = listing.images.first()
        edit_url = reverse("provider-edit-listing", args=[listing.pk])
        self.assertContains(self.client.get(edit_url), 'name="remove_images"')
        data.pop("image_uploads")
        response = self.client.post(edit_url, {**data, "title": "Yangilangan uy", "remove_images": [first_photo.pk]})
        self.assertRedirects(response, reverse("provider-dashboard"))
        listing.refresh_from_db()
        self.assertEqual(listing.title, "Yangilangan uy")
        self.assertEqual(listing.images.count(), 1)
        self.assertFalse(ListingImage.objects.filter(pk=first_photo.pk).exists())

        self.client.force_login(self.user)
        self.assertEqual(self.client.get(edit_url).status_code, 404)

    def test_cannot_remove_the_last_photo(self):
        data = {**self._common("home"), "bedrooms": "2", "bathrooms": "1"}
        self.client.post(reverse("provider-create-listing"), data)
        listing = RentalListing.objects.get(title="Yangi e'lon")
        data.pop("image_uploads")
        response = self.client.post(reverse("provider-edit-listing", args=[listing.pk]), {
            **data, "remove_images": [listing.images.first().pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(listing.images.count(), 1)

    def test_missing_translations_are_filled_automatically(self):
        translated = {
            "title_ru": "Новое объявление", "title_en": "New listing",
            "description_ru": "Описание", "description_en": "Description",
        }
        with override_settings(GEMINI_API_KEY="test-key"), \
                patch("core.listing_translation._request_translations", return_value=translated) as request:
            data = {**self._common("home"), "bedrooms": "2", "bathrooms": "1", "title_en": "My own title"}
            self.client.post(reverse("provider-create-listing"), data)
        request.assert_called_once_with("Yangi e'lon", "Tavsif")
        listing = RentalListing.objects.get(title="Yangi e'lon")
        self.assertEqual(listing.title_ru, "Новое объявление")
        self.assertEqual(listing.title_en, "My own title")  # Provider-entered text is never overwritten.
        self.assertEqual(listing.description_en, "Description")

    def test_translation_failure_does_not_block_listing_creation(self):
        with override_settings(GEMINI_API_KEY="test-key"), \
                patch("core.gemini.urlopen", side_effect=URLError("offline")):
            data = {**self._common("home"), "bedrooms": "2", "bathrooms": "1"}
            response = self.client.post(reverse("provider-create-listing"), data)
        self.assertRedirects(response, reverse("provider-dashboard"))
        self.assertEqual(RentalListing.objects.get(title="Yangi e'lon").title_ru, "")


class LocalizedNameTests(StartAppBaseTest):
    def test_region_and_district_options_carry_all_three_languages(self):
        response = self.client.get(reverse("home"))
        region = Region.objects.get(pk=14)
        self.assertContains(
            response,
            f'data-localized-text data-uz="{region.name_uz}" data-ru="{region.name_ru}" data-en="{region.name_en}"',
        )

    def test_listing_location_and_title_are_localized(self):
        region = Region.objects.get(pk=14)
        district = District.objects.filter(region=region).first()
        self.home.region, self.home.district = region, district
        self.home.title_ru, self.home.title_en = "Тестовая квартира", "Test flat"
        self.home.save()
        response = self.client.get(reverse("listing-detail", args=[self.home.slug]))
        self.assertContains(response, f'data-ru="{district.name_ru}"')
        self.assertContains(response, 'data-ru="Тестовая квартира"')

    def test_new_interface_texts_have_translation_entries(self):
        source = (Path(__file__).resolve().parent / "static/core/i18n.js").read_text(encoding="utf-8")
        for text in ("Nimani ijaraga berasiz?", "Bron so'rovlari", "Rad etish", "Hisob ma'lumotlari",
                     "Avval viloyatni tanlang", "Ushbu maydon to'ldirilishi shart."):
            self.assertIn(f'["{text}"', source)


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

    def test_polling_messages_with_an_attachment_returns_its_media_url(self):
        message = ChatMessage.objects.create(
            conversation=self.conversation, sender=self.provider, text="",
            attachment="chat/2026/10/photo.png", attachment_type=ChatMessage.AttachmentType.IMAGE,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("chat-messages-api", args=[self.conversation.pk]), {"after": 0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["messages"][0]["attachment_url"], reverse("chat-media", args=[message.pk]))


class TelegramPollingTests(StartAppBaseTest):
    def test_polling_command_removes_webhook_and_handles_updates(self):
        update = {"update_id": 7, "message": {
            "text": "/start", "from": {"id": 555}, "chat": {"id": 555, "type": "private"},
        }}
        calls = []

        def fake_call(method, payload, timeout=20):
            calls.append(method)
            if method == "getUpdates":
                if payload.get("offset") == 8:
                    raise KeyboardInterrupt  # Stop the endless loop after the first batch.
                return [update]
            return True

        with patch("core.management.commands.run_telegram_bot._call", side_effect=fake_call), \
                patch("core.telegram._call", side_effect=fake_call):
            with self.assertRaises(KeyboardInterrupt):
                call_command("run_telegram_bot", stdout=StringIO())
        self.assertEqual(calls[0], "deleteWebhook")
        self.assertIn("sendMessage", calls)  # /start asked the user for their contact.


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



def _png_file(name="photo.png", size=(8, 8)):
    data = BytesIO()
    Image.new("RGB", size, color="green").save(data, format="PNG")
    return SimpleUploadedFile(name, data.getvalue(), content_type="image/png")


class AccountAndProfileTests(StartAppBaseTest):
    def test_every_user_gets_a_uid_and_profile_shows_id_uid_and_logout(self):
        self.assertTrue(self.user.account.uid)
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile"))
        self.assertContains(response, str(self.user.account.uid))
        self.assertContains(response, f"ID: <b data-no-translate=\"true\">{self.user.pk}</b>")
        self.assertContains(response, reverse("logout"))
        self.assertContains(response, reverse("profile-edit"))

    def test_user_can_change_name_and_avatar(self):
        self.client.force_login(self.user)
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(reverse("profile-edit"), {
                "first_name": "  Aziz ", "last_name": "Karimov", "avatar": _png_file("me.png"),
            })
            self.assertRedirects(response, reverse("profile"))
            self.user.refresh_from_db()
            self.assertEqual((self.user.first_name, self.user.last_name), ("Aziz", "Karimov"))
            self.assertTrue(self.user.account.avatar.name.startswith("avatars/"))
            response = self.client.post(reverse("profile-edit"), {"first_name": "Aziz", "remove_avatar": "on"})
            self.user.account.refresh_from_db()
            self.assertFalse(self.user.account.avatar)

    def test_avatar_must_be_a_real_image(self):
        self.client.force_login(self.user)
        fake = SimpleUploadedFile("evil.png", b"<script>alert(1)</script>", content_type="image/png")
        response = self.client.post(reverse("profile-edit"), {"first_name": "Aziz", "avatar": fake})
        self.assertEqual(response.status_code, 200)
        self.assertIn("avatar", response.context["form"].errors)
        self.assertFalse(self.user.account.avatar)


class CompanyReviewAndSimilarTests(StartAppBaseTest):
    def setUp(self):
        super().setUp()
        self.provider = User.objects.create_user(username="host", password="test-pass")
        self.host = HostProfile.objects.create(user=self.provider, display_name="Musulman Rent", phone_number="+998901112233")
        self.home.owner = self.provider
        self.home.save(update_fields=["owner"])
        self.other_home = RentalListing.objects.create(
            kind=RentalListing.Kind.HOME, title="Second home", city="Toshkent", address="Yunusobod",
            description="Another home", price_per_day=Decimal("260000"), capacity=4, owner=self.provider,
        )

    def test_listing_shows_company_card_and_similar_listings(self):
        response = self.client.get(reverse("listing-detail", args=[self.home.slug]))
        self.assertContains(response, "Musulman Rent")
        self.assertContains(response, "tel:+998901112233")
        self.assertContains(response, "O'xshash e'lonlar")
        self.assertContains(response, "Second home")
        self.assertNotContains(response, "Test car")  # Similar = same kind only.

    def test_user_can_rate_and_comment_once_and_update(self):
        self.client.force_login(self.user)
        url = reverse("listing-review", args=[self.home.slug])
        self.assertRedirects(self.client.post(url, {"rating": "4", "comment": "Juda yaxshi"}),
                             reverse("listing-detail", args=[self.home.slug]) + "#reviews", fetch_redirect_response=False)
        self.client.post(url, {"rating": "5", "comment": "Zo'r"})
        review = ListingReview.objects.get(listing=self.home, user=self.user)
        self.assertEqual((review.rating, review.comment), (5, "Zo'r"))
        response = self.client.get(reverse("listing-detail", args=[self.home.slug]))
        self.assertContains(response, "Zo&#x27;r")
        self.assertContains(response, "★★★★★")

    def test_rating_must_be_between_one_and_five_and_owner_cannot_review(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("listing-review", args=[self.home.slug]), {"rating": "9"})
        self.assertEqual(response.status_code, 400)
        self.client.force_login(self.provider)
        self.client.post(reverse("listing-review", args=[self.home.slug]), {"rating": "5"})
        self.assertFalse(ListingReview.objects.exists())

    def test_provider_dashboard_search_and_filters(self):
        self.client.force_login(self.provider)
        response = self.client.get(reverse("provider-dashboard"), {"q": "Second"})
        self.assertContains(response, "Second home")
        self.assertNotContains(response, ">Test apartment<")
        response = self.client.get(reverse("provider-dashboard"), {"kind": "car"})
        self.assertNotContains(response, "Second home")

    def test_provider_can_update_company_details(self):
        self.client.force_login(self.provider)
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(reverse("provider-company"), {
                "display_name": "New Name", "phone_number": "+998 90 999 88 77", "logo": _png_file(),
            })
        self.assertRedirects(response, reverse("provider-dashboard"))
        self.host.refresh_from_db()
        self.assertEqual((self.host.display_name, self.host.phone_number), ("New Name", "+998909998877"))


class SupportChatTests(StartAppBaseTest):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="helper", password="test-pass", is_staff=True)

    def test_contact_admin_opens_the_users_support_chat(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("contact-admin"))
        conversation = Conversation.objects.get(kind=Conversation.Kind.SUPPORT, customer=self.user)
        self.assertRedirects(response, reverse("chat-room", args=[conversation.pk]))
        self.assertContains(self.client.get(reverse("chat-room", args=[conversation.pk])), "Rentora Admin")
        # Opening it again reuses the same chat.
        self.client.get(reverse("contact-admin"))
        self.assertEqual(Conversation.objects.filter(kind=Conversation.Kind.SUPPORT).count(), 1)

    def test_admin_reply_shows_as_rentora_admin_with_read_receipts(self):
        self.client.force_login(self.user)
        conversation = Conversation.objects.get(pk=self.client.get(reverse("contact-admin")).url.strip("/").split("/")[-1])
        response = self.client.post(reverse("chat-room", args=[conversation.pk]), {"text": "Salom, yordam kerak"},
                                    HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 201)
        sent = response.json()["message"]
        self.assertTrue(sent["mine"])
        self.assertFalse(sent["read"])
        conversation.refresh_from_db()
        self.assertEqual(conversation.support_status, Conversation.SupportStatus.WAITING)

        self.client.force_login(self.admin)
        thread = self.client.get(reverse("helper-support-thread", args=[conversation.pk]))
        self.assertContains(thread, "Salom, yordam kerak")
        self.client.post(reverse("chat-room", args=[conversation.pk]), {"text": "Albatta, yordam beramiz"})
        conversation.refresh_from_db()
        self.assertEqual(conversation.support_status, Conversation.SupportStatus.ANSWERED)

        self.client.force_login(self.user)
        data = self.client.get(reverse("chat-messages-api", args=[conversation.pk]), {"after": 0}).json()
        reply = data["messages"][-1]
        self.assertEqual(reply["sender"], "Rentora Admin")  # The admin's own name stays private.
        self.assertFalse(reply["mine"])
        self.assertTrue(data["messages"][0]["read"])  # The admin has read the user's message.

    def test_other_users_cannot_open_someone_elses_support_chat(self):
        conversation = Conversation.objects.create(kind=Conversation.Kind.SUPPORT, customer=self.user)
        outsider = User.objects.create_user(username="outsider", password="test-pass")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("chat-room", args=[conversation.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("helper-support")).status_code, 404)

    def test_inbox_shows_per_chat_unread_badge(self):
        provider = User.objects.create_user(username="prov", password="test-pass")
        self.home.owner = provider
        self.home.save(update_fields=["owner"])
        conversation = Conversation.objects.create(listing=self.home, customer=self.user, provider=provider)
        ChatMessage.objects.create(conversation=conversation, sender=provider, text="Bir")
        ChatMessage.objects.create(conversation=conversation, sender=provider, text="Ikki")
        self.client.force_login(self.user)
        response = self.client.get(reverse("chat-inbox"))
        self.assertContains(response, 'class="tg-badge" aria-label="O\'qilmagan xabarlar: 2">2</span>')
        self.assertEqual(self.client.get(reverse("chat-unread-status")).json()["count"], 2)

    def test_video_upload_and_range_requests(self):
        conversation = Conversation.objects.create(kind=Conversation.Kind.SUPPORT, customer=self.user)
        video = SimpleUploadedFile("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2000, content_type="video/mp4")
        self.client.force_login(self.user)
        with TemporaryDirectory() as chat_root, override_settings(CHAT_MEDIA_ROOT=chat_root):
            from .models import chat_media_storage
            chat_media_storage.location = chat_root
            chat_media_storage.__dict__.pop("base_location", None)
            chat_media_storage.__dict__.pop("location", None)
            response = self.client.post(reverse("chat-room", args=[conversation.pk]), {"attachment": video},
                                        HTTP_ACCEPT="application/json")
            self.assertEqual(response.status_code, 201, response.content)
            message = response.json()["message"]
            self.assertEqual(message["attachment_type"], "video")
            media = self.client.get(message["attachment_url"], HTTP_RANGE="bytes=0-99")
            self.assertEqual(media.status_code, 206)
            self.assertEqual(media["Content-Range"], "bytes 0-99/2012")
            self.assertEqual(len(b"".join(media.streaming_content)), 100)
            self.assertIn("sandbox", media["Content-Security-Policy"])

    def test_disguised_file_is_rejected(self):
        conversation = Conversation.objects.create(kind=Conversation.Kind.SUPPORT, customer=self.user)
        self.client.force_login(self.user)
        fake = SimpleUploadedFile("movie.mp4", b"<html><script>alert(1)</script></html>", content_type="video/mp4")
        response = self.client.post(reverse("chat-room", args=[conversation.pk]), {"attachment": fake},
                                    HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ChatMessage.objects.exists())


class SupportAITests(StartAppBaseTest):
    def test_ai_tools_only_expose_the_asking_users_own_bookings(self):
        from .support_ai import build_tools
        other = User.objects.create_user(username="other", password="test-pass", email="secret@example.com")
        Booking.objects.create(user=other, listing=self.car, check_in=self.tomorrow, check_out=self.day_after)
        Booking.objects.create(user=self.user, listing=self.home, check_in=self.tomorrow, check_out=self.day_after)
        tools = {tool.name: tool for tool in build_tools(self.user, {"escalated": False})}
        self.assertEqual(set(tools), {"search_listings", "get_listing", "my_bookings", "escalate_to_admin"})
        mine = tools["my_bookings"].function()
        self.assertEqual([row["listing"] for row in mine["bookings"]], ["Test apartment"])
        dumped = json.dumps(tools["search_listings"].function(), default=str)
        self.assertNotIn("secret@example.com", dumped)
        self.assertNotIn("other", dumped)

    @override_settings(SUPPORT_AI_DELAY_SECONDS=0)
    def test_worker_answers_unanswered_chats_as_rentora_admin(self):
        from .chat import post_message
        from .support_ai import answer_conversation, conversations_needing_ai
        conversation = Conversation.objects.create(kind=Conversation.Kind.SUPPORT, customer=self.user)
        post_message(conversation, self.user, text="Toshkentda uy bormi?")
        self.assertEqual(conversations_needing_ai(), [conversation])
        with patch("core.support_ai.run_agent", return_value="Ha, bor: Test apartment."):
            answer_conversation(conversation)
        conversation.refresh_from_db()
        self.assertEqual(conversation.support_status, Conversation.SupportStatus.AI)
        reply = conversation.messages.order_by("-pk").first()
        self.assertTrue(reply.is_ai)
        self.assertEqual(reply.display_sender(self.user), "Rentora Admin")
        self.assertEqual(conversations_needing_ai(), [])

    @override_settings(SUPPORT_AI_DELAY_SECONDS=3600)
    def test_ai_waits_for_admins_first(self):
        from .chat import post_message
        from .support_ai import conversations_needing_ai
        conversation = Conversation.objects.create(kind=Conversation.Kind.SUPPORT, customer=self.user)
        post_message(conversation, self.user, text="Savol")
        self.assertEqual(conversations_needing_ai(), [])

    def test_admin_ai_is_read_only_and_staff_only(self):
        from .admin_ai import build_tools
        names = {tool.name for tool in build_tools()}
        self.assertFalse(any(word in name for name in names for word in ("create", "delete", "update", "block")))
        self.client.force_login(self.user)
        response = self.client.post(reverse("helper-ai"), data=json.dumps({"message": "hi"}), content_type="application/json")
        self.assertEqual(response.status_code, 404)


class HelperPanelTests(StartAppBaseTest):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(username="helper", password="test-pass", is_staff=True)
        self.boss = User.objects.create_superuser(username="boss", password="test-pass")
        self.booking = Booking.objects.create(user=self.user, listing=self.home, check_in=self.tomorrow, check_out=self.day_after)

    def test_regular_users_cannot_open_the_panel(self):
        self.client.force_login(self.user)
        for name in ("helper-dashboard", "helper-support", "helper-bookings", "helper-users", "helper-products", "helper-chats"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 404, name)

    def test_staff_can_search_and_filter_every_section(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("helper-dashboard")), "AI yordamchi")
        self.assertContains(self.client.get(reverse("helper-bookings"), {"q": f"#{self.booking.pk}"}), "Test apartment")
        self.assertNotContains(self.client.get(reverse("helper-bookings"), {"status": "cancelled"}), "Test apartment")
        self.assertContains(self.client.get(reverse("helper-users"), {"q": "demo-user"}), "demo@example.com")
        self.assertContains(self.client.get(reverse("helper-users"), {"q": str(self.user.account.uid)}), "demo-user")
        self.assertContains(self.client.get(reverse("helper-products"), {"kind": "car"}), "Test car")
        self.assertNotContains(self.client.get(reverse("helper-products"), {"kind": "car"}), "Test apartment")

    def test_staff_can_cancel_a_booking_and_hide_a_listing(self):
        self.client.force_login(self.admin)
        with patch("core.helper_views.notify_booking_parties"), self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("helper-booking-cancel", args=[self.booking.pk]))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)
        self.client.post(reverse("helper-product-toggle", args=[self.car.pk]))
        self.car.refresh_from_db()
        self.assertFalse(self.car.is_active)

    def test_only_the_superuser_adds_or_deletes_users_and_admins(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("helper-user-create"), {
            "username": "newbie", "password1": "Strong-Pass-123", "password2": "Strong-Pass-123",
        })
        self.assertFalse(User.objects.filter(username="newbie").exists())
        victim = User.objects.create_user(username="victim", password="test-pass")
        self.client.post(reverse("helper-user-action", args=[victim.pk, "delete"]))
        self.assertTrue(User.objects.filter(pk=victim.pk).exists())

        self.client.force_login(self.boss)
        self.client.post(reverse("helper-user-create"), {
            "username": "newadmin", "password1": "Strong-Pass-123", "password2": "Strong-Pass-123", "is_staff": "on",
        })
        self.assertTrue(User.objects.get(username="newadmin").is_staff)
        self.client.post(reverse("helper-user-action", args=[victim.pk, "delete"]))
        self.assertFalse(User.objects.filter(pk=victim.pk).exists())
        self.client.post(reverse("helper-user-action", args=[self.boss.pk, "delete"]))
        self.assertTrue(User.objects.filter(pk=self.boss.pk).exists())

    def test_listing_chats_are_read_only_for_staff(self):
        provider = User.objects.create_user(username="prov", password="test-pass")
        conversation = Conversation.objects.create(listing=self.home, customer=self.user, provider=provider)
        ChatMessage.objects.create(conversation=conversation, sender=provider, text="Narxi qancha?")
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("helper-chat-view", args=[conversation.pk])), "Narxi qancha?")
        conversation.refresh_from_db()
        self.assertEqual(conversation.customer_last_read_message_id, 0)
        self.assertEqual(self.client.get(reverse("chat-room", args=[conversation.pk])).status_code, 404)


class SecurityTests(StartAppBaseTest):
    def test_login_is_blocked_after_repeated_failures(self):
        for _ in range(8):
            self.client.post(reverse("login"), {"username": "demo-user", "password": "wrong"})
        response = self.client.post(reverse("login"), {"username": "demo-user", "password": "SafePass123!"})
        self.assertEqual(response.status_code, 429)

    def test_pages_send_a_content_security_policy(self):
        response = self.client.get(reverse("home"))
        self.assertIn("script-src 'self'", response["Content-Security-Policy"])
        self.assertEqual(response["X-Frame-Options"], "DENY")

    def test_listing_photo_names_are_randomized(self):
        listing_image = ListingImage(listing=self.home)
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            listing_image.image = _png_file("../../evil.html")
            listing_image.save()
            self.assertRegex(listing_image.image.name, r"^listing-images/\d{4}/\d{2}/[0-9a-f]{32}\.jpg$")
        from .uploads import validate_image_upload
        upload = validate_image_upload(_png_file("evil.html"))
        self.assertEqual(upload.name, "upload.png")


class SeedCatalogTests(StartAppBaseTest):
    def test_wipe_keeps_users_and_creates_homes_and_cars_for_the_provider(self):
        from .management.commands.seed_catalog import CAR_MODELS
        provider = User.objects.create_user(username="mmmm", password="test-pass")
        HostProfile.objects.create(user=provider, display_name="musulman")
        Booking.objects.create(user=self.user, listing=self.home, check_in=self.tomorrow, check_out=self.day_after)
        with TemporaryDirectory() as photos, TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            for folder, names in (("home", ["1600607687939-ce8a6c25118c", "1564013799919-ab600027ffc6"]), ("car", list(CAR_MODELS))):
                (Path(photos) / folder).mkdir()
                for name in names:
                    Image.new("RGB", (8, 8)).save(Path(photos) / folder / f"{name}.jpg")
            call_command("seed_catalog", owner="mmmm", count=6, photos=photos, wipe=True, stdout=StringIO())
            self.assertEqual(Booking.objects.count(), 0)
            self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
            self.assertEqual(RentalListing.objects.filter(owner=provider, kind="home").count(), 3)
            self.assertEqual(RentalListing.objects.filter(owner=provider, kind="car").count(), 3)
            self.assertTrue(all(listing.title_ru and listing.title_en for listing in RentalListing.objects.all()))
            self.assertTrue(all(listing.images.exists() for listing in RentalListing.objects.all()))


class DjangoAdminHardeningTests(TestCase):
    def setUp(self):
        self.admin_index = reverse("admin:index")

    def test_anonymous_admin_visit_goes_to_site_login(self):
        response = self.client.get(self.admin_index)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login") + "?next="))
        login_page = self.client.get(reverse("admin:login"))
        self.assertEqual(login_page.status_code, 302)
        self.assertTrue(login_page["Location"].startswith(reverse("login")))

    def test_helper_admin_and_regular_user_get_not_found(self):
        for is_staff in (True, False):
            user = get_user_model().objects.create_user(f"user{is_staff}", password="pass-12345", is_staff=is_staff)
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.admin_index).status_code, 404)
            self.client.logout()

    def test_head_admin_opens_admin_without_caching(self):
        boss = get_user_model().objects.create_superuser("boss", password="pass-12345")
        self.client.force_login(boss)
        response = self.client.get(self.admin_index)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rentora — bosh admin")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("noindex", response["X-Robots-Tag"])
