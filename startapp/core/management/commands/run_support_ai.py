import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from core.ai_agent import AgentError
from core.support_ai import answer_conversation, conversations_needing_ai

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Answer support chats on the admin team's behalf when no admin replied within SUPPORT_AI_DELAY_SECONDS."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process waiting chats once and exit.")
        parser.add_argument("--interval", type=int, default=15)

    def handle(self, *args, **options):
        if not settings.SUPPORT_AI_ENABLED:
            self.stdout.write("SUPPORT_AI_ENABLED=0: support AI is off.")
            if options["once"]:
                return
            while True:
                time.sleep(3600)
        self.stdout.write(self.style.SUCCESS("Support AI worker started."))
        while True:
            close_old_connections()
            pause = options["interval"]
            for conversation in conversations_needing_ai():
                try:
                    answer_conversation(conversation)
                    logger.info("Support AI answered conversation %s.", conversation.pk)
                except AgentError as exc:
                    logger.warning("Support AI could not answer conversation %s: %s", conversation.pk, exc)
                    if exc.quota_exhausted:
                        pause = 600  # No credits or no key: retry rarely instead of hammering the API.
                    break
                except Exception:  # One broken chat must not stop the worker.
                    logger.exception("Support AI failed on conversation %s.", conversation.pk)
            if options["once"]:
                return
            time.sleep(pause)
