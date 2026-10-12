# Rentora — uy va avtomobil ijarasi
Rentora — uy va avtomobillarni qidirish hamda bron qilish uchun full-stack veb-ilova. Frontend Django templates, CSS va JavaScript bilan, backend Django + Django REST Framework bilan ishlaydi. SQLite standart baza sifatida ishlatiladi, alohida PostgreSQL yoki Docker o'rnatish shart emas.

## Til tanlash

Interfeys o'zbek (`UZ`), rus (`RU`) va ingliz (`EN`) tillarida mavjud. Yuqori qismdagi til tanlagich orqali tilni almashtirish mumkin; tanlov brauzerda saqlanadi va sahifalar o'rtasida saqlanib qoladi. Har bir e'lon uchun nom va tavsifning o'zbekcha, ruscha hamda inglizcha variantlarini admin paneldan kiritish mumkin. Tarjimasi kiritilmagan yangi e'lon matni asl kiritilgan tilda qoladi.

## Imkoniyatlar

- Uy va avtomobillar katalogi: shahar, turi, mehmon/yo'lovchi soni va sanalar bo'yicha qidiruv.
- E'lon tafsilotlari, kunlik narx va sanalarga qarab jami summani avtomatik hisoblash.
- Ro'yxatdan o'tish, tizimga kirish va shaxsiy bronlar sahifasi.
- Naqd bronni darhol saqlash; Click/karta yoki Payme tanlanganda mijozni buyurtmadan so'ng darhol onlayn to'lovga yo'naltirish.
- Provayder to'lovi tasdiqlanmaguncha bron yozilmaydi; muvaffaqiyatli callback bronni tasdiqlaydi va sanalarni band qiladi.
- Bron va buyurtmalarni bekor qilish; kutilayotgan buyurtmalar sanalarni boshqa mijozlardan vaqtincha band qiladi.
- Bron holatlari: kutilmoqda, tasdiqlangan yoki bekor qilingan.
- Django admin orqali e'lonlar, bronlar va to'lov yozuvlarini ko'rish hamda nom va tavsiflarning ruscha/inglizcha versiyalarini saqlash.
- E'lon yaratishda admin paneldan 10 tagacha oddiy rasm faylini yuklash va galereyada ko'rsatish.
- Rentora AI tabiiy tildagi ijara so'rovlarini filtrlash, saralash va muddat bo'yicha ijara narxini hisoblash bilan cheklanadi.
- JSON REST API va `/health/` health endpoint.
- Telefon, planshet va desktop ekranlariga mos dizayn.
- Demo uchun 8 ta uy/avtomobil e'lonini yaratadigan seed buyrug'i.

> Click va Payme merchant API oqimlari tayyor; haqiqiy to'lovlar uchun merchant hisoblari, callback URL'lari va maxfiy environment sozlamalari talab qilinadi. SMS tasdiqlash, xarita API va real vaqt bildirishnomalari ulanmagan. Namuna rasmlari internet orqali yuklanadi.

## Talablar

- Python 3.11, 3.12 yoki 3.13
- Paketlarni o'rnatish va onlayn namuna rasmlarini ko'rsatish uchun internet kerak.

## Windows'da ishga tushirish

PowerShell terminalini loyiha papkasida oching. Quyidagi buyruqlar bilan qo'lda ishga tushirish yoki `start_windows.bat` faylini ochib avtomatik sozlash mumkin:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

Agar Python 3.12 o'rnatilmagan bo'lsa, `py -3.13` yoki mos o'rnatilgan Python versiyasidan foydalaning. `start_windows.bat` mavjud Python versiyalaridan mosini tanlaydi va demo e'lonlarni qo'shadi; skript admin foydalanuvchi yaratishni ham taklif qiladi. Keyin brauzerda `http://127.0.0.1:8000/` manzilini oching. Admin: `http://127.0.0.1:8000/admin/`.

### Git Bash terminali

```bash
py -3.12 -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

Ixtiyoriy ravishda `.env.example` faylidan `.env` nusxa oling va qiymatlarni o'zgartiring.

### Rentora AI va e'lon rasmlari

AI yordamchini yoqish uchun OpenAI API kalitini `.env` fayliga kiriting:

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

AI faqat ijara e'lonlarini filtrlash/saralash va narxdan muddat bo'yicha jami summani hisoblashga mo'ljallangan. So'rov matni mezonlarni aniqlash uchun OpenAI API'ga yuboriladi; ijara narxi serverda bazadagi narx asosida hisoblanadi. Kalitni repoga qo'shmang.

Yangi e'lon qo'shishda admin paneldagi "E'lon rasmlari" bo'limidan 10 tagacha rasm faylini yuklang (har biri 10 MB gacha). Mahalliy ishlab chiqishda rasmlar `startapp/media/` ichida saqlanadi. Production'da `MEDIA_ROOT` uchun doimiy disk yoki Django storage-compatible object storage sozlang.

### Onlayn to'lov

Click merchant kabinetida callback URL sifatida `https://<sayt-domeni>/payments/click/callback/` manzilini sozlang. Payme Business Merchant API URL'i `https://<sayt-domeni>/payments/payme/callback/` bo'ladi. Merchant ma'lumotlarini `.env` fayliga yoki hosting environment'iga kiriting; secret'larni repoga qo'shmang:

```dotenv
CLICK_SERVICE_ID=
CLICK_MERCHANT_ID=
CLICK_SECRET_KEY=
PAYME_MERCHANT_ID=
PAYME_MERCHANT_KEY=
```

Buyurtma yuborilgach mijoz darhol tanlangan provayderning to'lov sahifasiga yo'naltiriladi; admin yoki mezbon tasdig'i talab qilinmaydi. Django faqat provayder imzosi va muvaffaqiyatli callback tekshirilgach `Booking` yozuvini yaratadi. Karta va Click tanlovlari Click checkout'iga, Payme tanlovi Payme Business checkout'iga yo'naltiriladi. Test/sandbox uchun provider bergan test checkout URL va merchant credential'larini `CLICK_CHECKOUT_BASE_URL` hamda `PAYME_CHECKOUT_BASE_URL` orqali belgilang. Callback'lar ommaviy internetdan HTTPS orqali ochiq bo'lishi kerak.

Integratsiya protokollari: [Click hujjatlari](https://docs.click.uz/) va [Payme Business Merchant API](https://developer.help.paycom.uz/).

## Testlar

Kutubxonalarni o'rnatgandan so'ng:

```bash
python manage.py test core
```

Testlar bosh sahifa va til tanlagichni, filtrlarni, ro'yxatdan o'tishni, naqd bron, admin aralashuvisiz onlayn to'lov oqimi, Click/Payme callback'lari, sanalar to'qnashuvi, bekor qilish huquqlari va API ruxsatlarini tekshiradi. Python va frontend skriptlari sintaksisi ham alohida tekshiriladi. Tafsilotlar `TEST_REPORT.md` faylida.

## API yo'llari

| Method | Endpoint | Vazifasi | Kirish |
|---|---|---|---|
| GET | `/health/` | Server holati | Ochiq |
| GET | `/api/listings/` | E'lonlar ro'yxati | Ochiq |
| GET | `/api/listings/<id>/` | E'lon tafsiloti | Ochiq |
| GET | `/api/bookings/` | Joriy foydalanuvchining bronlari | Login kerak |
| POST | `/api/bookings/` | Bron yaratish | Login kerak |
| POST | `/api/bookings/<id>/cancel/` | O'z bronini bekor qilish | Login kerak |

E'lon filtrlari: `kind=home` yoki `kind=car`, `city=Toshkent`, `q=...`, `check_in=YYYY-MM-DD`, `check_out=YYYY-MM-DD`. Masalan: `/api/listings/?kind=car&city=Toshkent`.

API Django session autentifikatsiyasi va CSRF himoyasidan foydalanadi.

## Production oldidan

Development `SECRET_KEY` va `DEBUG=True` qiymatlarini production uchun ishlatmang. `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0` va `DJANGO_ALLOWED_HOSTS` environment o'zgaruvchilarini sozlang, HTTPS va xavfsiz cookie parametrlarini hosting muhitiga moslang. Real ijara biznesiga chiqarishdan oldin to'lov provayderi, shartlar, shaxsni tasdiqlash, nizolarni ko'rib chiqish va maxfiylik siyosatini alohida amalga oshirish kerak.
