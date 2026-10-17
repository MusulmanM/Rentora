from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_account(sender, instance, created, **kwargs):
    """Every user gets a UID (and an avatar slot) as soon as the account exists."""
    if created:
        from .models import UserAccount

        UserAccount.objects.get_or_create(user=instance)


@receiver(post_save, sender="core.ListingImage")
def make_listing_thumbnail(sender, instance, created, **kwargs):
    """A light WebP copy for listing cards (see core/thumbnails.py)."""
    if instance.image:
        from .thumbnails import make_thumbnail

        make_thumbnail(instance.image)
