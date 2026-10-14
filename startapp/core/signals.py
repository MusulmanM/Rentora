from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_account(sender, instance, created, **kwargs):
    """Every user gets a UID (and an avatar slot) as soon as the account exists."""
    if created:
        from .models import UserAccount

        UserAccount.objects.get_or_create(user=instance)
