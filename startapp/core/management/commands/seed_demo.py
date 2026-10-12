from django.core.management.base import BaseCommand
from core.models import District, Region, RentalListing


LISTINGS = [
    {
        "kind": "home", "title": "Yorug' va zamonaviy apartament", "title_ru": "Светлые современные апартаменты", "title_en": "Bright modern apartment", "city": "Toshkent",
        "address": "Yunusobod tumani", "price_per_day": "480000", "capacity": 4,
        "bedrooms": 2, "bathrooms": 1, "is_featured": True,
        "legacy_image_url": "https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=1200&q=85",
        "description": "Toshkent markaziga qulay masofadagi yorug' va zamonaviy apartament. Toza xonalar, qulay oshxona va dam olish uchun barcha zarur sharoitlar mavjud. Oilaviy sayohat va xizmat safari uchun mos.", "description_ru": "Светлые современные апартаменты недалеко от центра Ташкента. Чистые комнаты, удобная кухня и всё необходимое для отдыха. Подходят для семейной поездки и командировки.", "description_en": "A bright, modern apartment a convenient distance from central Tashkent. Clean rooms, a well-equipped kitchen and everything needed to relax. Ideal for family trips and business travel.",
    },
    {
        "kind": "home", "title": "Shinam hovlili dam olish uyi", "title_ru": "Уютный дом с двориком для отдыха", "title_en": "Cozy holiday home with a courtyard", "city": "Samarqand",
        "address": "Shahar markazidan 10 daqiqa", "price_per_day": "650000", "capacity": 6,
        "bedrooms": 3, "bathrooms": 2, "is_featured": True,
        "legacy_image_url": "https://images.unsplash.com/photo-1600607687920-4e2a09cf159d?auto=format&fit=crop&w=1200&q=85",
        "description": "Samarqandda oila yoki do'stlar bilan dam olish uchun shinam uy. Keng mehmonxona, jihozlangan oshxona va hovli mavjud. Tarixiy joylarga borish uchun qulay joylashuv.", "description_ru": "Уютный дом в Самарканде для отдыха с семьёй или друзьями. Просторная гостиная, оборудованная кухня и двор. Удобное расположение для посещения исторических достопримечательностей.", "description_en": "A cozy home in Samarkand for a stay with family or friends. It has a spacious living room, a fully equipped kitchen and a courtyard, with easy access to historic attractions.",
    },
    {
        "kind": "home", "title": "Minimalistik shahar studiyasi", "title_ru": "Минималистичная городская студия", "title_en": "Minimalist city studio", "city": "Toshkent",
        "address": "Mirzo Ulug'bek tumani", "price_per_day": "320000", "capacity": 2,
        "bedrooms": 1, "bathrooms": 1, "is_featured": False,
        "legacy_image_url": "https://images.unsplash.com/photo-1600566753086-00f18fb6b3ea?auto=format&fit=crop&w=1200&q=85",
        "description": "Yolg'iz sayohatchi yoki juftlik uchun ixcham, ozoda va did bilan jihozlangan studiya. Tez internet, qulay ish stoli va transportga yaqin manzil.", "description_ru": "Компактная, чистая и со вкусом оформленная студия для одного путешественника или пары. Быстрый интернет, удобный рабочий стол и близость к транспорту.", "description_en": "A compact, clean and tastefully furnished studio for a solo traveller or couple. It offers fast internet, a convenient desk and easy access to transport.",
    },
    {
        "kind": "home", "title": "Eski shahar yaqinidagi mehmon uyi", "title_ru": "Гостевой дом рядом со Старым городом", "title_en": "Guesthouse near the Old City", "city": "Buxoro",
        "address": "Eski shahar hududi", "price_per_day": "390000", "capacity": 3,
        "bedrooms": 2, "bathrooms": 1, "is_featured": False,
        "legacy_image_url": "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=1200&q=85",
        "description": "Buxoroning tarixiy maskanlarini piyoda kashf etish uchun qulay mehmon uyi. Sokkin muhit, milliy bezaklar va kundalik ehtiyojlar uchun sharoitlar.", "description_ru": "Удобный гостевой дом для пеших прогулок по историческим местам Бухары. Тихая атмосфера, национальный декор и всё необходимое на каждый день.", "description_en": "A convenient guesthouse for exploring Bukhara's historic sites on foot. It offers a peaceful atmosphere, traditional decor and everyday essentials.",
    },
    {
        "kind": "car", "title": "Chevrolet Cobalt", "title_ru": "Chevrolet Cobalt", "title_en": "Chevrolet Cobalt", "city": "Toshkent",
        "address": "Toshkent shahri, olib ketish punkti", "price_per_day": "350000", "capacity": 5,
        "brand": "Chevrolet", "transmission": "automatic", "year": 2023, "is_featured": True,
        "legacy_image_url": "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?auto=format&fit=crop&w=1200&q=85",
        "description": "Shahar ichida va viloyatlarga safar qilish uchun tejamkor, qulay avtomobil. Avtomat uzatmalar qutisi, konditsioner va keng yukxona. Avtomobilni topshirish va qaytarish vaqti oldindan kelishiladi.", "description_ru": "Экономичный и комфортный автомобиль для поездок по городу и регионам. Автоматическая коробка передач, кондиционер и вместительный багажник. Время получения и возврата согласовывается заранее.", "description_en": "An economical, comfortable car for city drives and trips to other regions. It has an automatic transmission, air conditioning and a spacious trunk. Pickup and return times are agreed in advance.",
    },
    {
        "kind": "car", "title": "Hyundai Elantra", "title_ru": "Hyundai Elantra", "title_en": "Hyundai Elantra", "city": "Toshkent",
        "address": "Toshkent shahri, Chilonzor", "price_per_day": "520000", "capacity": 5,
        "brand": "Hyundai", "transmission": "automatic", "year": 2024, "is_featured": True,
        "legacy_image_url": "https://images.unsplash.com/photo-1619767886558-efdc259cde1a?auto=format&fit=crop&w=1200&q=85",
        "description": "Biznes va oilaviy safarlar uchun zamonaviy sedan. Qulay salon, avtomat uzatmalar qutisi va zamonaviy xavfsizlik imkoniyatlari. Yoqilg'i sarfi tejamkor.", "description_ru": "Современный седан для деловых и семейных поездок. Комфортный салон, автоматическая коробка передач и современные системы безопасности. Экономичный расход топлива.", "description_en": "A modern sedan for business and family trips. It features a comfortable cabin, automatic transmission, modern safety features and efficient fuel consumption.",
    },
    {
        "kind": "car", "title": "Chevrolet Tracker", "title_ru": "Chevrolet Tracker", "title_en": "Chevrolet Tracker", "city": "Samarqand",
        "address": "Samarqand shahri, markaz", "price_per_day": "600000", "capacity": 5,
        "brand": "Chevrolet", "transmission": "automatic", "year": 2024, "is_featured": False,
        "legacy_image_url": "https://images.unsplash.com/photo-1519641471654-76ce0107ad1b?auto=format&fit=crop&w=1200&q=85",
        "description": "Shahar va uzoqroq sayohatlar uchun qulay krossover. Baland o'tirish holati va keng salon tufayli kundalik foydalanish hamda oilaviy yo'l safarlariga mos.", "description_ru": "Удобный кроссовер для города и дальних поездок. Высокая посадка и просторный салон делают его подходящим для повседневных дел и семейных путешествий.", "description_en": "A versatile crossover for city driving and longer trips. Its higher seating position and spacious cabin make it ideal for everyday use and family travel.",
    },
    {
        "kind": "car", "title": "Kia K5", "title_ru": "Kia K5", "title_en": "Kia K5", "city": "Buxoro",
        "address": "Buxoro shahri, aeroport yaqinida", "price_per_day": "720000", "capacity": 5,
        "brand": "Kia", "transmission": "automatic", "year": 2023, "is_featured": False,
        "legacy_image_url": "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1200&q=85",
        "description": "Zamonaviy va qulay sedan. Ish uchrashuvlari, tantanali tadbirlar yoki shahar tashqarisiga safar uchun mos. Avtomobil topshirish vaqti bron tasdiqlangach kelishiladi.", "description_ru": "Современный и комфортный седан для деловых встреч, торжественных мероприятий и поездок за город. Время передачи автомобиля согласовывается после подтверждения бронирования.", "description_en": "A modern, comfortable sedan for business meetings, special occasions or trips out of town. Vehicle handover time is arranged after the booking is confirmed.",
    },
]


class Command(BaseCommand):
    help = "Rentora uchun namuna uy va avtomobil e'lonlarini yaratadi."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for item in LISTINGS:
            defaults = item.copy()
            kind = defaults.pop("kind")
            title = defaults.pop("title")
            region_code = {"Toshkent": 14, "Samarqand": 8, "Buxoro": 3}.get(defaults["city"])
            region = Region.objects.filter(pk=region_code).first() if region_code else None
            district = None
            if region:
                district = next(
                    (
                        candidate for candidate in District.objects.filter(region=region)
                        if candidate.name_uz.lower() in defaults["address"].lower()
                    ),
                    None,
                )
                if district is None:
                    district = District.objects.filter(
                        region=region, name_uz__iexact=f"{defaults['city']} shahri",
                    ).first()
            if region:
                defaults["region"] = region
            if district:
                defaults["district"] = district
                defaults["city"] = district.name_uz
            _, was_created = RentalListing.objects.update_or_create(
                title=title, defaults={"kind": kind, "title": title, **defaults}
            )
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Demo e'lonlar tayyor. Yangi: {created}, yangilangan: {updated}."))
