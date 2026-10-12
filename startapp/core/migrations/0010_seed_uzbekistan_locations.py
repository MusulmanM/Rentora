import json
from pathlib import Path

from django.db import migrations


def _normalize(value):
    normalized = value.strip().lower().replace("ʻ", "'").replace("‘", "'").replace("’", "'")
    for suffix in (" viloyati", " shahri", " tumani", " region", " city", " district", " republic"):
        normalized = normalized.removesuffix(suffix)
    return normalized.strip()


def load_locations(apps, schema_editor):
    region_model = apps.get_model("core", "Region")
    district_model = apps.get_model("core", "District")
    listing_model = apps.get_model("core", "RentalListing")
    database = schema_editor.connection.alias
    data_path = Path(__file__).resolve().parent.parent / "data" / "uzbekistan_locations.json"
    with data_path.open(encoding="utf-8") as location_file:
        data = json.load(location_file)

    regions = {
        int(item["id"]): item for item in data["regions"]
    }
    region_model.objects.using(database).bulk_create([
        region_model(
            code=code,
            name_uz=item["name_uz"],
            name_en=item["name_en"],
            name_ru=item["name_ru"],
        )
        for code, item in regions.items()
    ])
    district_model.objects.using(database).bulk_create([
        district_model(
            code=int(item["id"]),
            region_id=int(item["region_id"]),
            name_uz=item["name_uz"],
            name_en=item["name_en"],
            name_ru=item["name_ru"],
        )
        for item in data["districts"]
    ])

    location_rows = list(district_model.objects.using(database).values(
        "code", "region_id", "name_uz", "name_en",
    ))
    region_names = {
        code: (_normalize(item["name_uz"]), _normalize(item["name_en"]))
        for code, item in regions.items()
    }
    for listing in listing_model.objects.using(database).filter(region__isnull=True).iterator():
        city = _normalize(listing.city)
        if city in ("toshkent", "tashkent") and 14 in regions:
            listing.region_id = 14
            listing.save(update_fields=["region"])
            continue
        district_matches = [
            row for row in location_rows
            if city in (_normalize(row["name_uz"]), _normalize(row["name_en"]))
        ]
        if district_matches:
            match = next(
                (row for row in district_matches if "shahri" in row["name_uz"].lower()),
                district_matches[0],
            )
            listing.region_id = match["region_id"]
            listing.district_id = match["code"]
        else:
            region_matches = [
                code for code, names in region_names.items() if city in names
            ]
            if region_matches:
                listing.region_id = region_matches[0]
        if listing.region_id:
            listing.save(update_fields=["region", "district"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_district_region_telegramaccount_rentallisting_owner_and_more"),
    ]

    operations = [
        migrations.RunPython(load_locations, migrations.RunPython.noop),
    ]
