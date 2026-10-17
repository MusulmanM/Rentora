"""Telegram reminders for rentals that end today or were not returned on time.

Run it hourly (systemd timer or `--every 3600`). Each booking gets the "ends today" notice once,
and at most one overdue warning per day, so running it more often never sends duplicates.
"""
import logging
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import Booking
from core.telegram import notify_booking_parties

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send Telegram reminders for rentals ending today and for late returns (with the debt so far)."

    def add_arguments(self, parser):
        parser.add_argument("--every", type=int, default=0, help="Repeat every N seconds instead of running once.")

    def handle(self, *args, every, **options):
        while True:
            ending, overdue = self.run_once()
            self.stdout.write(f"Rental reminders: {ending} ending today, {overdue} overdue warnings.")
            if not every:
                return
            time.sleep(every)

    def run_once(self):
        today = timezone.localdate()
        ending = overdue = 0
        rentals = Booking.objects.filter(status=Booking.Status.HANDED_OVER, check_out__lte=today)
        for booking_id in rentals.values_list("pk", flat=True):
            with transaction.atomic():
                booking = Booking.objects.select_for_update().filter(
                    pk=booking_id, status=Booking.Status.HANDED_OVER,
                ).first()
                if booking is None:
                    continue
                if booking.check_out == today and booking.end_notice_sent_on != today:
                    event, field = "ending", "end_notice_sent_on"
                elif booking.check_out < today and booking.overdue_notice_sent_on != today:
                    event, field = "overdue", "overdue_notice_sent_on"
                else:
                    continue
                # Mark first: a crash after sending must not re-send the same notice in a loop.
                setattr(booking, field, today)
                booking.save(update_fields=[field])
            try:
                notify_booking_parties(booking.pk, event)
            except Exception:  # noqa: BLE001 - one failing chat must not stop the other reminders
                logger.exception("Rental reminder %s failed for booking %s.", event, booking.pk)
                continue
            if event == "ending":
                ending += 1
            else:
                overdue += 1
        self.remind_installments(today)
        return ending, overdue

    def remind_installments(self, today):
        """The day before and on the due date, then every day while a part stays unpaid."""
        from core.models import Installment
        from core.telegram import notify_installment

        active = (Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.HANDED_OVER)
        waiting = Installment.objects.filter(
            status=Installment.Status.PENDING, booking__status__in=active, due_date__lte=today + timedelta(days=1),
        ).exclude(reminded_on=today)
        for installment_id, due_date in waiting.values_list("pk", "due_date"):
            if not Installment.objects.filter(pk=installment_id).exclude(reminded_on=today).update(reminded_on=today):
                continue  # another run took it
            try:
                notify_installment(installment_id, "overdue" if due_date < today else "due")
            except Exception:  # noqa: BLE001 - one failing chat must not stop the other reminders
                logger.exception("Instalment reminder failed for %s.", installment_id)
