import logging
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from core.telegram import TelegramError, _call, handle_telegram_update, set_bot_commands

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Receive Telegram bot updates by long polling. Use this when the site has no public HTTPS URL "
        "for a webhook. It removes any configured webhook, because Telegram allows only one of the two."
    )

    def handle(self, *args, **options):
        try:
            _call("deleteWebhook", {"drop_pending_updates": False})
        except TelegramError as exc:
            raise CommandError(str(exc)) from exc
        try:
            set_bot_commands()  # the "/" menu in Uzbek, Russian and English
        except TelegramError:
            logger.warning("Telegram bot commands could not be set.")
        self.stdout.write(self.style.SUCCESS("Telegram bot long polling started."))
        offset = None
        while True:
            payload = {"timeout": 50, "allowed_updates": ["message"]}
            if offset is not None:
                payload["offset"] = offset
            try:
                updates = _call("getUpdates", payload, timeout=65) or []
            except TelegramError:
                time.sleep(1)  # a dropped long poll: reconnect almost at once
                continue
            for update in updates:
                offset = update.get("update_id", 0) + 1
                close_old_connections()
                try:
                    handle_telegram_update(update)
                except Exception:  # One bad update must not stop the bot.
                    logger.exception("Telegram update %s could not be processed.", update.get("update_id"))
