from django.core.management.base import BaseCommand, CommandError

from core.listing_translation import missing_translation_fields, translate_listing, translation_enabled
from core.models import RentalListing


class Command(BaseCommand):
    help = "Fill missing Russian/English listing titles and descriptions with Gemini."

    def handle(self, *args, **options):
        if not translation_enabled():
            raise CommandError("GEMINI_API_KEY sozlanmagan.")
        listings = [listing for listing in RentalListing.objects.all() if missing_translation_fields(listing)]
        if not listings:
            self.stdout.write("Barcha e'lonlar tarjima qilingan.")
            return
        for listing in listings:
            filled = translate_listing(listing)
            status = ", ".join(filled) if filled else "tarjima qilinmadi (logni tekshiring)"
            self.stdout.write(f"#{listing.pk} {listing.title}: {status}")
