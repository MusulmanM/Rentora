from urllib.parse import urlparse

from django.core.management.base import BaseCommand, CommandError

from core.telegram import TelegramError, _call
from django.conf import settings


class Command(BaseCommand):
    help = "Configure the Telegram bot webhook using Django's environment settings."

    def add_arguments(self, parser):
        parser.add_argument("url", help="Public HTTPS URL ending in /telegram/webhook/")

    def handle(self, *args, **options):
        url = options["url"].strip()
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path.rstrip("/") != "/telegram/webhook":
            raise CommandError("URL HTTPS bo'lishi va /telegram/webhook/ bilan tugashi kerak.")
        if not getattr(settings, "TELEGRAM_WEBHOOK_SECRET", ""):
            raise CommandError("TELEGRAM_WEBHOOK_SECRET .env faylida sozlanmagan.")
        try:
            _call("setWebhook", {
                "url": url,
                "secret_token": settings.TELEGRAM_WEBHOOK_SECRET,
            })
        except TelegramError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Telegram webhook muvaffaqiyatli sozlandi."))
