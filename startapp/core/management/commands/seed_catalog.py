"""Fill the catalog with realistic homes and cars (uz/ru/en) for one provider.

    python manage.py seed_catalog --owner mmmm --count 150 --photos /path/to/photos [--wipe]

`--photos` must contain `home/` and `car/` folders with .jpg files. Car photos are matched to the
car model they show (see CAR_MODELS), so a listing is always titled after the car in its photo.
`--wipe` first deletes all listings, bookings, orders, payments, chats, reviews and contact
messages, keeping only user data (accounts, profiles, Telegram links, company profiles).
"""
import random
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (
    Booking, BookingOrder, ChatMessage, ContactMessage, Conversation, District, HostProfile, ListingImage,
    ListingReview, PaymentTransaction, PendingPhoneVerification, PendingRegistration, RentalListing,
)

User = get_user_model()

# District code -> weight. Tashkent city dominates, then the big tourist and regional cities.
LOCATIONS = {
    198: 2, 199: 4, 200: 4, 201: 2, 202: 2, 203: 2, 204: 3, 205: 4, 206: 3, 207: 4, 208: 4, 218: 1,
    122: 5, 47: 4, 216: 3, 185: 2, 100: 2, 30: 2, 23: 1, 154: 4, 68: 1, 77: 1, 135: 1, 92: 1, 191: 2,
    165: 1, 175: 1, 177: 1, 224: 1,
}
STREETS = [
    ("Amir Temur ko'chasi", "улица Амира Темура", "Amir Temur street"),
    ("Navoiy ko'chasi", "улица Навои", "Navoi street"),
    ("Bobur ko'chasi", "улица Бабура", "Bobur street"),
    ("Mustaqillik ko'chasi", "улица Мустакиллик", "Mustaqillik street"),
    ("Shota Rustaveli ko'chasi", "улица Шота Руставели", "Shota Rustaveli street"),
    ("Buyuk Ipak Yo'li ko'chasi", "улица Буюк Ипак Йули", "Buyuk Ipak Yoli street"),
    ("Mirzo Ulug'bek ko'chasi", "улица Мирзо Улугбека", "Mirzo Ulugbek street"),
    ("Bunyodkor shoh ko'chasi", "проспект Бунёдкор", "Bunyodkor avenue"),
    ("Ibn Sino ko'chasi", "улица Ибн Сины", "Ibn Sino street"),
    ("Registon ko'chasi", "улица Регистан", "Registon street"),
]

# Home photos that show a pool or a big house outside; the rest are interiors.
EXTERIOR_PHOTOS = {
    "1512917774080-9991f1c4c750", "1558036117-15d82a90b9b1", "1564013799919-ab600027ffc6",
    "1567496898669-ee935f5f647a", "1568605114967-8130f3a36994", "1570129477492-45c003edd2be",
    "1576941089067-2de3c901e126", "1580587771525-78b9dba3b914", "1600047509807-ba8f99d2cdde",
    "1600566753190-17f0baa2a6c3", "1600585154340-be6161a56a0c", "1600596542815-ffad4c1539a9",
    "1602343168117-bb8ffe3e2e9f", "1613490493576-7fde63acd811",
}
POOL_PHOTOS = {
    "1512917774080-9991f1c4c750", "1564013799919-ab600027ffc6", "1580587771525-78b9dba3b914",
    "1600596542815-ffad4c1539a9", "1602343168117-bb8ffe3e2e9f", "1613490493576-7fde63acd811",
}

# Photo id prefix -> (brand, model, seats, transmission, price per day, base year, colour uz/ru/en, body uz/ru/en)
CAR_MODELS = {
    "1494976388531": ("Ford", "Mustang GT", 4, "automatic", 2_500_000, 2021, ("qora", "чёрный", "black"), ("sport kupe", "спорткупе", "sports coupe")),
    "1502877338535": ("BMW", "430i Coupe", 4, "automatic", 1_800_000, 2022, ("ko'k", "синий", "blue"), ("kupe", "купе", "coupe")),
    "1503376780353": ("Porsche", "Panamera 4S", 4, "automatic", 4_000_000, 2022, ("qora", "чёрный", "black"), ("biznes sedan", "бизнес-седан", "executive sedan")),
    "1511919884226": ("Lamborghini", "Huracán", 2, "automatic", 12_000_000, 2021, ("sariq", "жёлтый", "yellow"), ("superkar", "суперкар", "supercar")),
    "1525609004556": ("Lamborghini", "Aventador", 2, "automatic", 15_000_000, 2020, ("to'q sariq", "оранжевый", "orange"), ("superkar", "суперкар", "supercar")),
    "1533473359331": ("Ford", "Expedition", 7, "automatic", 2_200_000, 2021, ("oq", "белый", "white"), ("katta SUV", "большой внедорожник", "full-size SUV")),
    "1541899481282": ("Volkswagen", "Polo", 5, "manual", 450_000, 2019, ("ko'k", "синий", "blue"), ("xetchbek", "хэтчбек", "hatchback")),
    "1542362567": ("McLaren", "720S", 2, "automatic", 14_000_000, 2021, ("oq", "белый", "white"), ("superkar", "суперкар", "supercar")),
    "1544636331": ("Bugatti", "Chiron", 2, "automatic", 40_000_000, 2020, ("kumush", "серебристый", "silver"), ("giperkar", "гиперкар", "hypercar")),
    "1549317661": ("Fiat", "500", 4, "automatic", 400_000, 2020, ("havorang", "голубой", "light blue"), ("shahar avtomobili", "городской автомобиль", "city car")),
    "1552519507": ("Chevrolet", "Camaro", 4, "automatic", 2_000_000, 2020, ("ko'k", "синий", "blue"), ("sport kupe", "спорткупе", "sports coupe")),
    "1555215695": ("BMW", "M5", 5, "automatic", 3_500_000, 2022, ("oq", "белый", "white"), ("sport sedan", "спортивный седан", "sports sedan")),
    "1563720223185": ("Land Rover", "Range Rover Sport", 5, "automatic", 3_800_000, 2022, ("qora", "чёрный", "black"), ("premium SUV", "премиальный внедорожник", "luxury SUV")),
    "1568605117036": ("Nissan", "GT-R", 4, "automatic", 5_000_000, 2020, ("kumush", "серебристый", "silver"), ("sport kupe", "спорткупе", "sports coupe")),
    "1580273916550": ("BMW", "M4", 4, "automatic", 3_000_000, 2021, ("kulrang", "серый", "grey"), ("sport kupe", "спорткупе", "sports coupe")),
    "1580274455191": ("Porsche", "911 GT3 RS", 2, "automatic", 8_000_000, 2022, ("qora", "чёрный", "black"), ("sport kupe", "спорткупе", "sports coupe")),
    "1583121274602": ("Ferrari", "LaFerrari", 2, "automatic", 30_000_000, 2019, ("qizil", "красный", "red"), ("giperkar", "гиперкар", "hypercar")),
    "1590362891991": ("Mercedes-Benz", "GLC Coupe", 5, "automatic", 2_800_000, 2021, ("oq", "белый", "white"), ("krossover-kupe", "кроссовер-купе", "coupe SUV")),
    "1605559424843": ("Mercedes-AMG", "GT", 2, "automatic", 6_000_000, 2020, ("sariq", "жёлтый", "yellow"), ("sport kupe", "спорткупе", "sports coupe")),
    "1606016159991": ("Tesla", "Model 3", 5, "automatic", 1_500_000, 2022, ("oq", "белый", "white"), ("elektr sedan", "электроседан", "electric sedan")),
    "1606664515524": ("Audi", "RS6 Avant", 5, "automatic", 3_500_000, 2021, ("qora", "чёрный", "black"), ("sport universal", "спортивный универсал", "performance estate")),
    "1609521263047": ("Nissan", "Juke", 5, "automatic", 600_000, 2020, ("kulrang", "серый", "grey"), ("ixcham krossover", "компактный кроссовер", "compact crossover")),
    "1612825173281": ("Lamborghini", "Huracán EVO", 2, "automatic", 12_500_000, 2022, ("to'q sariq", "оранжевый", "orange"), ("superkar", "суперкар", "supercar")),
    "1614162692292": ("Porsche", "911 Carrera", 4, "automatic", 7_000_000, 2021, ("oq", "белый", "white"), ("sport kupe", "спорткупе", "sports coupe")),
    "1616422285623": ("Audi", "A7 Sportback", 5, "automatic", 2_500_000, 2022, ("oq", "белый", "white"), ("biznes liftbek", "бизнес-лифтбек", "executive liftback")),
    "1617469767053": ("Toyota", "RAV4", 5, "automatic", 900_000, 2021, ("kulrang", "серый", "grey"), ("krossover", "кроссовер", "crossover")),
    "1617814076367": ("Mercedes-AMG", "GT 63", 4, "automatic", 6_500_000, 2022, ("to'q kulrang", "тёмно-серый", "dark grey"), ("sport sedan", "спортивный седан", "sports sedan")),
    "1618843479313": ("Mercedes-AMG", "GT R", 2, "automatic", 7_000_000, 2021, ("kumush", "серебристый", "silver"), ("sport kupe", "спорткупе", "sports coupe")),
    "1619767886558": ("Hyundai", "Elantra", 5, "automatic", 650_000, 2021, ("qora", "чёрный", "black"), ("sedan", "седан", "sedan")),
    "1621007947382": ("Toyota", "Camry", 5, "automatic", 1_000_000, 2021, ("kulrang", "серый", "grey"), ("biznes sedan", "бизнес-седан", "business sedan")),
}
EVERYDAY_CARS = ["1621007947382", "1619767886558", "1617469767053", "1541899481282", "1549317661", "1606016159991",
                 "1609521263047", "1502877338535", "1533473359331", "1563720223185", "1590362891991",
                 "1616422285623", "1555215695", "1606664515524", "1503376780353"]


def _short(name):
    for suffix in (" tumani", " shahri", " район", " district", " city"):
        name = name.replace(suffix, "")
    return name.replace("город ", "").strip()


def _short_ru(name):
    """"город Бухара" -> "Бухара"; district names keep "район" ("Сергелийский район")."""
    return name.replace("город ", "").strip()


def _round(value, step=10_000):
    return Decimal(int(round(value / step)) * step)


class Command(BaseCommand):
    help = "Create realistic home and car listings for a provider (optionally wiping non-user data first)."

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True, help="Username of the provider who owns the listings.")
        parser.add_argument("--count", type=int, default=150)
        parser.add_argument("--photos", required=True, help="Folder with home/ and car/ photo subfolders.")
        parser.add_argument("--wipe", action="store_true", help="Delete all listings, bookings, chats and reviews first.")
        parser.add_argument("--seed", type=int, default=2026)

    def handle(self, *args, **options):
        owner = User.objects.filter(username=options["owner"]).first()
        if owner is None:
            raise CommandError(f"Foydalanuvchi topilmadi: {options['owner']}")
        if not HostProfile.objects.filter(user=owner).exists():
            raise CommandError("Bu foydalanuvchi ijara beruvchi emas (HostProfile yo'q).")
        photos = Path(options["photos"])
        home_photos = sorted((photos / "home").glob("*.jpg"))
        car_photos = {path.stem: path for path in (photos / "car").glob("*.jpg")}
        if not home_photos or not car_photos:
            raise CommandError("home/ yoki car/ papkasida rasm yo'q.")
        rng = random.Random(options["seed"])

        if options["wipe"]:
            self._wipe()

        districts = list(District.objects.filter(code__in=LOCATIONS).select_related("region"))
        weights = [LOCATIONS[district.code] for district in districts]
        home_total = options["count"] // 2
        car_total = options["count"] - home_total
        created = 0
        with transaction.atomic():
            for index in range(home_total):
                self._create_home(owner, rng, rng.choices(districts, weights)[0], home_photos, index)
                created += 1
            car_order = list(CAR_MODELS) * 2 + EVERYDAY_CARS
            for index in range(car_total):
                key = car_order[index % len(car_order)]
                photo = next(path for stem, path in car_photos.items() if stem.startswith(key))
                self._create_car(owner, rng, rng.choices(districts, weights)[0], key, photo, repeat=index // len(CAR_MODELS))
                created += 1
        self.stdout.write(self.style.SUCCESS(f"{created} ta e'lon yaratildi ({home_total} uy, {car_total} avtomobil)."))

    def _wipe(self):
        deleted = {}
        for message in ChatMessage.objects.exclude(attachment=""):
            message.attachment.delete(save=False)
        for image in ListingImage.objects.all():
            image.image.delete(save=False)
        for model in (PaymentTransaction, BookingOrder, Booking, ChatMessage, Conversation, ListingReview,
                      ListingImage, RentalListing, ContactMessage, PendingRegistration, PendingPhoneVerification):
            deleted[model.__name__], _ = model.objects.all().delete()
        self.stdout.write("O'chirildi: " + ", ".join(f"{name}={count}" for name, count in deleted.items()))

    def _address(self, rng):
        uz, ru, en = rng.choice(STREETS)
        number = rng.randint(1, 140)
        return f"{uz}, {number}-uy", f"{ru}, {number}", f"{number} {en}"

    def _attach(self, listing, paths):
        for path in paths:
            with path.open("rb") as handle:
                ListingImage.objects.create(listing=listing, image=File(handle, name=path.name))

    def _create_home(self, owner, rng, district, photos, index):
        exterior = [path for path in photos if path.stem in EXTERIOR_PHOTOS] or list(photos)
        interior = [path for path in photos if path.stem not in EXTERIOR_PHOTOS] or list(photos)
        place_uz, place_ru, place_en = _short(district.name_uz), _short_ru(district.name_ru), _short(district.name_en)
        dacha_area = district.code in (154, 68)
        roll = rng.random()
        if dacha_area or roll < 0.12:
            kind = "villa" if rng.random() < 0.5 else "dacha"
        elif roll < 0.25:
            kind = "house"
        elif roll < 0.35:
            kind = "studio"
        else:
            kind = "apartment"
        rooms = rng.choice([1, 2, 2, 3, 3, 4])
        wifi = ("tezkor Wi-Fi", "быстрый Wi-Fi", "fast Wi-Fi")
        if kind == "apartment":
            main = rng.choice(interior)
            title = (f"{rooms} xonali kvartira, {place_uz}", f"{rooms}-комнатная квартира, {place_ru}", f"{rooms}-room apartment in {place_en}")
            body = (
                f"{place_uz}dagi {rooms} xonali shinam kvartira. To'liq jihozlangan oshxona, konditsioner, {wifi[0]}, "
                "kir yuvish mashinasi va toza choyshablar bor. Do'konlar va jamoat transporti yaqin.",
                f"Уютная {rooms}-комнатная квартира, {place_ru}. Полностью оборудованная кухня, кондиционер, {wifi[1]}, "
                "стиральная машина и свежее постельное бельё. Рядом магазины и общественный транспорт.",
                f"A cosy {rooms}-room apartment in {place_en}. Fully equipped kitchen, air conditioning, {wifi[2]}, "
                "washing machine and fresh linen. Shops and public transport are nearby.",
            )
            price = 220_000 + rooms * rng.randint(90_000, 160_000)
            capacity, bedrooms, bathrooms = rooms * 2, rooms, 1 if rooms < 3 else 2
            others = [path for path in interior if path != main]
            extra = [rng.choice(others)] if others else []
        elif kind == "studio":
            main = rng.choice(interior)
            title = (f"Zamonaviy studiya, {place_uz}", f"Современная студия, {place_ru}", f"Modern studio in {place_en}")
            body = (
                f"Yolg'iz sayohatchi yoki juftlik uchun ixcham studiya. Ish stoli, {wifi[0]}, mini-oshxona va qulay karavot.",
                f"Компактная студия для одного путешественника или пары. Рабочий стол, {wifi[1]}, мини-кухня и удобная кровать.",
                f"A compact studio for a solo traveller or a couple. Desk, {wifi[2]}, kitchenette and a comfy bed.",
            )
            price = rng.randint(180_000, 330_000)
            capacity, bedrooms, bathrooms = 2, 1, 1
            extra = []
        elif kind == "house":
            main = rng.choice([path for path in exterior if path.stem not in POOL_PHOTOS] or exterior)
            title = (f"Hovli uy, {place_uz}", f"Дом с двором, {place_ru}", f"House with a courtyard in {place_en}")
            body = (
                f"Oila yoki do'stlar bilan dam olish uchun keng hovli uy. {rooms + 1} ta yotoqxona, katta mehmonxona, "
                "jihozlangan oshxona, hovlida so'ri va avtomobil uchun joy.",
                f"Просторный дом с двором для отдыха семьёй или с друзьями. {rooms + 1} спальни, большая гостиная, "
                "оборудованная кухня, топчан во дворе и парковка.",
                f"A spacious house with a courtyard for families or friends. {rooms + 1} bedrooms, a large living room, "
                "an equipped kitchen, a courtyard seating area and parking.",
            )
            price = rng.randint(650_000, 1_500_000)
            capacity, bedrooms, bathrooms = 6 + rooms, rooms + 1, 2
            extra = [rng.choice(interior)]
        else:
            pool = kind == "villa"
            candidates = [path for path in exterior if (path.stem in POOL_PHOTOS) == pool] or exterior
            main = rng.choice(candidates)
            if pool:
                title = (f"Basseynli villa, {place_uz}", f"Вилла с бассейном, {place_ru}", f"Villa with a pool in {place_en}")
                feature = ("basseyn, barbekyu zonasi", "бассейн, зона барбекю", "a pool, a barbecue area")
                price = rng.randint(1_800_000, 4_500_000)
            else:
                title = (f"Dala hovli, {place_uz}", f"Дача, {place_ru}", f"Country house in {place_en}")
                feature = ("katta bog', barbekyu zonasi", "большой сад, зона барбекю", "a large garden, a barbecue area")
                price = rng.randint(900_000, 2_200_000)
            body = (
                f"Shahar shovqinidan uzoqda dam olish uchun zamonaviy {('villa' if pool else 'dala hovli')}: {feature[0]}, "
                f"{rooms + 2} ta yotoqxona, keng ayvon va tog' manzarasi.",
                f"Современная {('вилла' if pool else 'дача')} для отдыха вдали от городского шума: {feature[1]}, "
                f"{rooms + 2} спальни, просторная терраса и вид на горы.",
                f"A modern {('villa' if pool else 'country house')} away from the city noise: {feature[2]}, "
                f"{rooms + 2} bedrooms, a wide terrace and mountain views.",
            )
            capacity, bedrooms, bathrooms = 8 + rooms, rooms + 2, rng.choice([2, 3])
            extra = [rng.choice(interior)]
        address_uz, _, _ = self._address(rng)
        listing = RentalListing.objects.create(
            kind=RentalListing.Kind.HOME, owner=owner, region=district.region, district=district, city=district.name_uz,
            title=title[0], title_ru=title[1], title_en=title[2],
            description=body[0], description_ru=body[1], description_en=body[2],
            address=address_uz, price_per_day=_round(price), capacity=capacity, bedrooms=bedrooms, bathrooms=bathrooms,
            is_featured=index % 9 == 0, is_active=True,
        )
        self._attach(listing, [main, *extra])

    def _create_car(self, owner, rng, district, key, photo, repeat):
        brand, model, seats, transmission, price, base_year, colour, body = CAR_MODELS[key]
        year = min(2026, base_year + repeat)
        with_driver = repeat == 1 and price < 5_000_000
        place_uz, place_ru, place_en = _short(district.name_uz), _short_ru(district.name_ru), _short(district.name_en)
        title_suffix = (", haydovchi bilan", ", с водителем", " with a driver") if with_driver else ("", "", "")
        gearbox = ("avtomat", "автомат", "automatic") if transmission == "automatic" else ("mexanika", "механика", "manual")
        driver = (
            (" Tajribali haydovchi bilan beriladi.", " Предоставляется с опытным водителем.", " Comes with an experienced driver.")
            if with_driver else
            (" Haydovchilik guvohnomasi va pasport talab qilinadi.", " Нужны водительское удостоверение и паспорт.",
             " A driving licence and passport are required.")
        )
        listing = RentalListing.objects.create(
            kind=RentalListing.Kind.CAR, owner=owner, region=district.region, district=district, city=district.name_uz,
            title=f"{brand} {model} {year}{title_suffix[0]}",
            title_ru=f"{brand} {model} {year}{title_suffix[1]}",
            title_en=f"{brand} {model} {year}{title_suffix[2]}",
            description=(
                f"{colour[0].capitalize()} {brand} {model} ({body[0]}), {year}-yil, uzatmalar qutisi — {gearbox[0]}, "
                f"{seats} o'rindiq. Avtomobil toza va texnik ko'rikdan o'tgan; {place_uz} bo'ylab yetkazib berish mumkin."
                + driver[0]
            ),
            description_ru=(
                f"{colour[1].capitalize()} {brand} {model} ({body[1]}), {year} год, коробка — {gearbox[1]}, "
                f"{seats} мест. Автомобиль чистый и прошёл техосмотр; возможна доставка: {place_ru}." + driver[1]
            ),
            description_en=(
                f"A {colour[2]} {brand} {model} ({body[2]}), {year}, {gearbox[2]} transmission, {seats} seats. "
                f"Clean and fully serviced; delivery within {place_en} is available." + driver[2]
            ),
            address=self._address(rng)[0], price_per_day=_round(price * (1.25 if with_driver else 1) * rng.uniform(0.92, 1.08)),
            capacity=seats, brand=brand, transmission=transmission, year=year,
            is_featured=rng.random() < 0.1, is_active=True,
        )
        self._attach(listing, [photo])
