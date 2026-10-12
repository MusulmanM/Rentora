# Rentora — uy va avtomobil ijarasi
Rentora — uy va avtomobillarni qidirish hamda bron qilish uchun full-stack veb-ilova. Frontend Django templates, CSS va JavaScript bilan, backend Django + Django REST Framework bilan ishlaydi. SQLite standart baza sifatida ishlatiladi, alohida PostgreSQL yoki Docker o'rnatish shart emas.

## Til tanlash

Interfeys o'zbek (`UZ`), rus (`RU`) va ingliz (`EN`) tillarida mavjud. Yuqori qismdagi til tanlagich orqali tilni almashtirish mumkin; tanlov brauzerda saqlanadi va sahifalar o'rtasida saqlanib qoladi. Har bir e'lon uchun nom va tavsifning o'zbekcha, ruscha hamda inglizcha variantlarini admin paneldan kiritish mumkin. Tarjimasi kiritilmagan yangi e'lon matni asl kiritilgan tilda qoladi.

## Imkoniyatlar

- Uy va avtomobillar katalogi: shahar, turi, mehmon/yo'lovchi soni va sanalar bo'yicha qidiruv.
- E'lon tafsilotlari, kunlik narx va sanalarga qarab jami summani avtomatik hisoblash.
- Ro'yxatdan o'tish, tizimga kirish va shaxsiy bronlar sahifasi.
- Bron yaratish va bekor qilish; bir e'lon uchun ustma-ust sanalarga bron qo'yish cheklovi.
- Bron holatlari: kutilmoqda, tasdiqlangan yoki bekor qilingan.
- Django admin orqali e'lonlar va bronlarni boshqarish, nom va tavsiflarning ruscha/inglizcha versiyalarini saqlash.
- JSON REST API va `/health/` health endpoint.
- Telefon, planshet va desktop ekranlariga mos dizayn.
- Demo uchun 8 ta uy/avtomobil e'lonini yaratadigan seed buyrug'i.

> Demo versiyada onlayn to'lov, SMS tasdiqlash, xarita API va real vaqt bildirishnomalari ulanmagan. Bron ma'lumotlar bazasida saqlanadi va boshlang'ich holati `Pending` (kutilmoqda); admin paneldan tasdiqlash mumkin. Namuna rasmlari internet orqali yuklanadi.

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

## Testlar

Kutubxonalarni o'rnatgandan so'ng:

```bash
python manage.py test core
```

Testlar bosh sahifa va til tanlagichni, filtrlarni, ro'yxatdan o'tishni, bron summasini, sanalar to'qnashuvini, bekor qilish huquqlarini va API ruxsatlarini tekshiradi. Kod sintaksisi va frontend skriptlari uchun statik tekshiruv ham qo'shilgan. Joriy build muhitida Django o'rnatilmagan va paket indeksiga ulanish cheklangan; shuning uchun Django integratsion testlari bu yerda ishga tushmagan. Tafsilotlar `TEST_REPORT.md` faylida.

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
