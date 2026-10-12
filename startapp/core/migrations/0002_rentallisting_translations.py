from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="rentallisting", name="title",
            field=models.CharField(max_length=160, verbose_name="Nomi (UZ)"),
        ),
        migrations.AlterField(
            model_name="rentallisting", name="description",
            field=models.TextField(verbose_name="Tavsif (UZ)"),
        ),
        migrations.AddField(
            model_name="rentallisting", name="title_ru",
            field=models.CharField(blank=True, max_length=160, verbose_name="Название (RU)"),
        ),
        migrations.AddField(
            model_name="rentallisting", name="title_en",
            field=models.CharField(blank=True, max_length=160, verbose_name="Title (EN)"),
        ),
        migrations.AddField(
            model_name="rentallisting", name="description_ru",
            field=models.TextField(blank=True, verbose_name="Описание (RU)"),
        ),
        migrations.AddField(
            model_name="rentallisting", name="description_en",
            field=models.TextField(blank=True, verbose_name="Description (EN)"),
        ),
    ]
