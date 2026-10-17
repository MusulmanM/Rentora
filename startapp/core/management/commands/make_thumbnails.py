from django.core.management.base import BaseCommand

from core.models import ListingImage
from core.thumbnails import make_thumbnail


class Command(BaseCommand):
    help = "Create the small WebP card thumbnails for listing photos that do not have one yet."

    def handle(self, *args, **options):
        made = 0
        for item in ListingImage.objects.exclude(image="").iterator():
            if make_thumbnail(item.image):
                made += 1
        self.stdout.write(f"Thumbnails ready for {made} photos.")
