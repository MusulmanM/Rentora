# Rentora — uy va avtomobil ijarasi
Rentora — uy va avtomobillarni qidirish hamda bron qilish uchun full-stack veb-ilova. Frontend Django templates, CSS va JavaScript bilan, backend Django + Django REST Framework bilan ishlaydi. SQLite standart baza sifatida ishlatiladi, alohida PostgreSQL yoki Docker o'rnatish shart emas.

## Til tanlash

Interfeys o'zbek (`UZ`), rus (`RU`) va ingliz (`EN`) tillarida mavjud. Yuqori qismdagi til tanlagich orqali tilni almashtirish mumkin; tanlov brauzerda saqlanadi va sahifalar o'rtasida saqlanib qoladi. Har bir e'lon uchun nom va tavsifning o'zbekcha, ruscha hamda inglizcha variantlarini admin paneldan kiritish mumkin. Tarjimasi kiritilmagan yangi e'lon matni asl kiritilgan tilda qoladi.

## Imkoniyatlar

- Uy va avtomobillar katalogi: shahar, turi, mehmon/yo'lovchi soni va sanalar bo'yicha qidiruv.
- E'lon tafsilotlari, kunlik narx va sanalarga qarab jami summani avtomatik hisoblash.
- Ro'yxatdan o'tish, tizimga kirish va shaxsiy bronlar sahifasi.
- Telefon raqamini Telegram orqali OTP bilan tasdiqlash; telefon raqami foydalanuvchilar orasida yagona bo'ladi.
- Viloyat va shahar/tuman bo'yicha O'zbekistonning barcha hududlarini qidirish; tanlangan viloyat shahar/tuman ro'yxatini avtomatik cheklaydi.
- Profil ichidan ijara beruvchi sifatida alohida yoqilish va shu hisob bilan e'lon joylash.
- Saytdagi admin bilan bog'lanish formasi; yuborilgan xabarlar Django admin panelida saqlanadi.
- Naqd bronni darhol saqlash; Click/karta yoki Payme tanlanganda mijozni buyurtmadan so'ng darhol onlayn to'lovga yo'naltirish.
- Onlayn to'lov tasdiqlanmaguncha bron so'rovi yaratilmaydi; muvaffaqiyatli callback provayder tasdig'ini kutayotgan bronni yaratadi va sanalarni band qiladi.
- Bron va buyurtmalarni bekor qilish; kutilayotgan buyurtmalar sanalarni boshqa mijozlardan vaqtincha band qiladi.
- Bron holatlari: kutilmoqda, tasdiqlangan, mijozga topshirilgan yoki bekor qilingan.
- Django admin orqali e'lonlar, bronlar va to'lov yozuvlarini ko'rish hamda nom va tavsiflarning ruscha/inglizcha versiyalarini saqlash.
- E'lon yaratishda 10 tagacha rasm faylini yuklash, admin panelda preview ko'rish va e'lon sahifasida galereyani modal oynada ko'rish.
- Rentora AI ijara so'rovlarini filtrlash, saralash va narx hisoblash bilan birga Rentora bo'yicha savollarga ham javob beradi.
- Ijara beruvchi bron so'rovlarini tasdiqlaydi, mahsulotni topshirilgan deb belgilaydi va e'lonni Faol/Remont holatiga o'tkazadi.
- Mijoz va ijaraga beruvchi saytdagi chatda matn, rasm va ovozli xabar yuborishi mumkin.
- JSON REST API va `/health/` health endpoint.
- Telefon, planshet va desktop ekranlariga mos dizayn.
- Demo uchun 8 ta uy/avtomobil e'lonini yaratadigan seed buyrug'i.

> Click va Payme merchant API oqimlari tayyor; haqiqiy to'lovlar uchun merchant hisoblari, callback URL'lari va maxfiy environment sozlamalari talab qilinadi. Telegram OTP uchun bot tokeni va HTTPS webhook sozlanishi kerak. Xarita API va real vaqt bildirishnomalari ulanmagan. Namuna rasmlari internet orqali yuklanadi.

## Talablar

- Python 3.11, 3.12 yoki 3.13
- Paketlarni o'rnatish va onlayn namuna rasmlarini ko'rsatish uchun internet kerak.

## Windows'da ishga tushirish

PowerShell terminalini repository root papkasida oching va `manage.py` joylashgan Django loyiha papkasiga kiring. Quyidagi buyruqlar bilan qo'lda ishga tushirish yoki `startapp\start_windows.bat` faylini ochib avtomatik sozlash mumkin:

```powershell
Set-Location .\startapp
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
cd startapp
py -3.12 -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

Ixtiyoriy ravishda `startapp` ichida `Copy-Item .env.example .env` buyrug'i bilan `.env` nusxa oling va qiymatlarni o'zgartiring.

### Telegram OTP va telefonni tasdiqlash

BotFather orqali Telegram bot yarating va `startapp\.env` fayliga quyidagi o'zgaruvchilarni kiriting (`startapp` ichidagi `.env` bo'lmasa, repository rootidagi `.env` ham o'qiladi):

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
TELEGRAM_WEBHOOK_SECRET=
```

`TELEGRAM_WEBHOOK_SECRET` uchun 32 yoki undan uzun tasodifiy harf-raqamli qiymat ishlating. Sayt ommaviy HTTPS domenida bo'lishi shart. `.env` ichidagi `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` va `PUBLIC_SITE_URL` qiymatlarida domeningizni ko'rsating. Repository root papkasidan webhook'ni sozlang:

```powershell
Set-Location .\startapp
python manage.py set_telegram_webhook https://<ngrok-yoki-sayt-domeni>/telegram/webhook/
```

Webhook buyrug'i bot tokeni va secret'ni Django sozlamalaridan oladi; ularni terminal buyrug'iga yoki chatga yozmang. PowerShell'da vaqtinchalik environment o'zgaruvchisi kerak bo'lsa, sintaksis `$env:DJANGO_ALLOWED_HOSTS = "127.0.0.1,localhost,<domen>"`; `DJANGO_ALLOWED_HOSTS=...` ko'rinishidagi oddiy yozuv PowerShell buyrug'i emas. `.env` o'zgargach Django serverini qayta ishga tushiring; ngrok domeni o'zgarsa webhook'ni ham qayta sozlang.

`TELEGRAM_BOT_USERNAME` bot havolasidagi `@` belgisiz nomdir. Foydalanuvchi avval botni ochib `/start` yuboradi va bot so'ragan Telegram kontaktini o'zi ulashadi. Saytdagi ro'yxatdan o'tish shu kontakt bilan bog'langan raqamga 10 daqiqalik, 5 urinishli OTP kod yuboradi; kodni qayta so'rash 60 soniyada bir martadan cheklangan. Telegram webhook xususiy chatdagi va jo'natuvchining o'ziga tegishli kontaktlarni qabul qiladi. Mavjud akkaunt egalari profilidan telefonini shu usulda tasdiqlashi mumkin. Bron yuborilganda, tasdiqlanganda, bekor qilinganda va mahsulot topshirilganda mijoz hamda ijaraga beruvchiga rasm (ommaviy HTTPS manzili bo'lsa), nom, narx, muddat, jami summa va so'rov vaqti yuboriladi. Xabar olish uchun ikkala tomon ham oldin botga `/start` yuborgan bo'lishi kerak.

### Hudud filtrlari va ijara beruvchi kabineti

Viloyat, shahar va tumanlar ro'yxati migratsiya orqali bazaga yuklanadi; ma'lumotlar 14 ta viloyat/respublika/shahar va 209 ta shahar/tuman yozuvini o'z ichiga oladi. Manba: [`Ibratbek/regions-districts-json`](https://github.com/Ibratbek/regions-districts-json). Eski e'lonlardagi taniladigan shahar qiymatlari migratsiyada mos hududga bog'lanadi.

Telefon tasdiqlangan foydalanuvchi profilidagi **Ijara beruvchi sifatida ro'yxatdan o'tish** tugmasini tanlab, shu akkauntini ijara beruvchi profiliga aylantiradi. Qayta foydalanuvchi akkaunti yaratilmaydi. Keyin e'lon turini, hududini, manzil va shartlarini to'ldirib, 10 tagacha rasmni yuklashi mumkin. Ijara beruvchi kabinetidan e'lonni **Faol** yoki **Remont** holatiga o'tkazish mumkin; remontdagi e'lon katalogda ko'rinmaydi. E'lon egasi o'z mahsulotini bron qila olmaydi.

Bron so'rovida bosilgan sana/vaqt va narx saqlanadi. Naqd buyurtma ijaraga beruvchiga darhol so'rov bo'lib boradi; online buyurtma to'lovdan keyin so'rovga aylanadi. Ijaraga beruvchi avval **Tasdiqlayman**, keyin mijozga topshirganda **Mahsulot ijaraga topshirildi** tugmasini bosadi. Faol bron qilingan e'lon boshqa foydalanuvchilardan yashiriladi; bekor qilinsa yoki `check_out` muddati o'tsa qayta ko'rinadi.

Foydalanuvchilar e'lon sahifasidan telefon, Telegram yoki sayt chat orqali bog'lanishi mumkin. Chat matn, rasm, audio fayl va brauzer/mikrofon qo'llasa yozib olingan ovozli xabarni qo'llaydi. Chat fayllari `CHAT_MEDIA_ROOT` da (standart: `startapp/private-chat-media`) saqlanadi va faqat chat qatnashchilariga ko'rinadi; bu papkani web-serverda ommaviy media sifatida nashr qilmang.

**Admin bilan bog'lanish** formasi va AI eskalatsiya qilgan savollar `Admin → Bog'lanish xabarlari` bo'limida saqlanadi. Yangi xabarlar `Ko'rildi` belgisi bilan boshqariladi.

### Rentora AI va e'lon rasmlari

AI yordamchini yoqish uchun OpenAI API kalitini `.env` fayliga kiriting:

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

AI barcha sahifalarda past-o'ng burchakdagi suzuvchi chat orqali ochiladi; u ijara qidiruvi/saralashi, narx hisob-kitobi va Rentora yordam savollariga javob beradi, murakkab savolni administratorlar navbatiga yuboradi. Ijara narxi serverda bazadagi narx asosida hisoblanadi. HTTP 401, 403, 404, 429 va so'rov xatolari foydalanuvchiga alohida tushuntiriladi. `.env` `startapp` papkasidan yoki repository rootidan yuklanadi. `OPENAI_API_KEY` bo'lmasa yoki yaroqsiz bo'lsa, yordamchi sozlash/xato ko'rsatmasini beradi. Kalitni repoga qo'shmang.

Admin yangi e'lonida yoki ijara beruvchi kabinetida 10 tagacha haqiqiy rasm faylini yuklang (har biri 10 MB gacha). E'lon sahifasidagi asosiy rasm yoki kichik rasmlarni bosib, klaviaturadagi chap/o'ng tugmalarda galereyani ko'ring. Admin paneldagi rasm preview'ini bosib faylni alohida ochish mumkin. Mahalliy ishlab chiqishda rasmlar `startapp/media/` ichida saqlanadi. Production'da `MEDIA_ROOT` uchun doimiy disk yoki Django storage-compatible object storage sozlang.

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
| GET | `/api/locations/districts/?region_id=<id>` | Tanlangan viloyat shahar/tumanlari | Ochiq |
| GET | `/api/bookings/` | Joriy foydalanuvchining bronlari | Login kerak |
| POST | `/api/bookings/` | Bron yaratish | Login kerak |
| POST | `/api/bookings/<id>/cancel/` | O'z bronini bekor qilish | Login kerak |

E'lon filtrlari: `kind=home` yoki `kind=car`, `city=Toshkent`, `region=<id>`, `district=<id>`, `q=...`, `check_in=YYYY-MM-DD`, `check_out=YYYY-MM-DD`. Masalan: `/api/listings/?kind=car&region=14` yoki `/api/listings/?region=14&district=218`.

API Django session autentifikatsiyasi va CSRF himoyasidan foydalanadi.

## Production oldidan

Development `SECRET_KEY` va `DEBUG=True` qiymatlarini production uchun ishlatmang. `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0` va `DJANGO_ALLOWED_HOSTS` environment o'zgaruvchilarini sozlang, HTTPS va xavfsiz cookie parametrlarini hosting muhitiga moslang. Real ijara biznesiga chiqarishdan oldin to'lov provayderi, shartlar, shaxsni tasdiqlash, nizolarni ko'rib chiqish va maxfiylik siyosatini alohida amalga oshirish kerak.
