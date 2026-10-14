import uuid

from django.conf import settings
from django.db import migrations


def create_accounts(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    UserAccount = apps.get_model("core", "UserAccount")
    existing = set(UserAccount.objects.values_list("user_id", flat=True))
    UserAccount.objects.bulk_create([
        UserAccount(user_id=user_id, uid=uuid.uuid4())
        for user_id in User.objects.exclude(pk__in=existing).values_list("pk", flat=True)
    ])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_accounts_company_reviews_support"),
    ]

    operations = [
        migrations.RunPython(create_accounts, migrations.RunPython.noop),
    ]
