/* Lightweight client-side localization for the StartApp interface. */
(() => {
  'use strict';

  const entries = [
    ["O'zingizga mos joy", "Место для вас", "A place that fits you"],
    ["Yaxshi safar kichik tanlovdan boshlanadi", "Хорошая поездка начинается с правильного выбора", "A great trip starts with the right choice"],
    ["Safaringizni rejalashtiring", "Спланируйте поездку", "Plan your trip"],
    ["Sanalarni tanlang — umumiy narx avtomatik hisoblanadi.", "Выберите даты — общая стоимость рассчитаетcя автоматически.", "Choose dates — the total price is calculated automatically."],
    ["Ortiqcha qo'ng'iroqlar va chalkashliklarsiz, kerakli variantni topish uchun barcha muhim ma'lumot bir joyda.", "Без лишних звонков и путаницы: вся важная информация для выбора — в одном месте.", "No unnecessary calls or confusion — all the details you need in one place."],
    ["Safar uchun qulay uy yoki yo'l uchun ishonchli avtomobil. Barchasini bir joyda toping va bir necha qadamda bron qiling.", "Уютное жильё для поездки или надёжный автомобиль в дорогу. Найдите всё в одном месте и забронируйте за несколько шагов.", "A comfortable home for your trip or a reliable car for the road. Find everything in one place and book in a few steps."],
    ["Salom, ", "Здравствуйте, ", "Hello, "],
    ["Safar rejalaringiz shu yerda saqlanadi.", "Здесь хранятся планы ваших поездок.", "Your trip plans are saved here."],
    ["Keyingi manzilingiz", "Ваше следующее направление", "Your next destination"],
    ["shu yerdan", "начинается", "starts here"],
    ["boshlanadi.", "здесь.", "here."],
    ["IJARA QILISHNING YANGI USULI", "НОВЫЙ СПОСОБ АРЕНДЫ", "A NEW WAY TO RENT"],
    ["Oson. Qulay. Ishonchli.", "Просто. Удобно. Надёжно.", "Easy. Convenient. Reliable."],
    ["Rejangizga mos variantni toping.", "Найдите вариант под ваши планы.", "Find an option that fits your plans."],
    ["SAYOHATINGIZNI REJALASHTIRING", "ПЛАНИРУЙТЕ СВОЮ ПОЕЗДКУ", "PLAN YOUR JOURNEY"],
    ["Bosh sahifa", "Главная", "Home"],
    ["Ijara topish", "Найти аренду", "Find a rental"],
    ["Qanday ishlaydi?", "Как это работает?", "How it works"],
    ["Bronlarim", "Мои бронирования", "My bookings"],
    ["Chiqish", "Выйти", "Log out"],
    ["Kirish", "Войти", "Log in"],
    ["Ro'yxatdan o'tish", "Регистрация", "Sign up"],
    ["Tilni tanlang", "Выберите язык", "Choose language"],
    ["Til", "Язык", "Language"],
    ["Uy ijarasi", "Аренда жилья", "Home rental"],
    ["Avtomobil ijarasi", "Аренда автомобиля", "Car rental"],
    ["Avtomobillar", "Автомобили", "Cars"],
    ["Avtomobil", "Автомобиль", "Car"],
    ["Uylar", "Жильё", "Homes"],
    ["Uy", "Жильё", "Home"],
    ["Qayerga?", "Куда?", "Where to?"],
    ["Barcha shaharlar", "Все города", "All cities"],
    ["Kelish", "Заезд", "Check-in"],
    ["Ketish", "Выезд", "Check-out"],
    ["Yo'lovchilar", "Пассажиры", "Passengers"],
    ["Mehmonlar", "Гости", "Guests"],
    ["Odamlar soni", "Количество человек", "Number of people"],
    ["kishi", "чел.", "people"],
    ["Qidirish", "Поиск", "Search"],
    ["Ijara variantlari", "Варианты аренды", "Rental options"],
    ["Qulay uylar", "Удобное жильё", "Comfortable homes"],
    ["Tayyor avtomobillar", "Готовые к поездке автомобили", "Cars ready to go"],
    ["Bronlaringiz", "Ваши бронирования", "Your bookings"],
    ["bir joyda", "в одном месте", "in one place"],
    ["SIZ UCHUN TANLADIK", "МЫ ВЫБРАЛИ ДЛЯ ВАС", "PICKED FOR YOU"],
    ["Safarga tayyor avtomobillar", "Автомобили для поездок", "Cars ready for your trip"],
    ["Yashash uchun qulay uylar", "Уютное жильё для проживания", "Comfortable homes to stay in"],
    ["Ommabop ijara variantlari", "Популярные варианты аренды", "Popular rental options"],
    ["Talabingizga mos variantni toping, narxini ko'ring va sanalarni belgilang.", "Найдите подходящий вариант, узнайте цену и выберите даты.", "Find an option that suits you, check the price and choose your dates."],
    ["Barchasi", "Все", "All"],
    ["Sizning qidiruvingizga mos natijalar", "Результаты по вашему запросу", "Results matching your search"],
    ["Qidiruv bo'yicha mos variant topilmadi", "По вашему запросу ничего не найдено", "No results match your search"],
    ["Filtrlarni tozalash", "Сбросить фильтры", "Clear filters"],
    ["Tavsiya etiladi", "Рекомендуем", "Featured"],
    ["mehmon", "гостей", "guests"],
    ["yotoqxona", "спальня", "bedroom"],
    ["hammom", "ванная", "bathroom"],
    ["o'rindiq", "мест", "seats"],
    ["kun", "дн.", "days"],
    ["so'm", "сум", "UZS"],
    ["so‘m", "сум", "UZS"],
    ["Hozircha mos variant yo'q", "Пока нет подходящих вариантов", "No matching options yet"],
    ["Shahar yoki sanalarni o'zgartirib ko'ring.", "Попробуйте изменить город или даты.", "Try changing the city or dates."],
    ["Barcha variantlarni ko'rish", "Посмотреть все варианты", "View all options"],
    ["Ko'rsatilmoqda:", "Показано:", "Showing:"],
    ["ta ijara varianti", "вариантов аренды", "rental options"],
    ["UCHTA ODDIY QADAM", "ТРИ ПРОСТЫХ ШАГА", "THREE SIMPLE STEPS"],
    ["Rejadan bron qilishgacha —", "От планов до бронирования —", "From planning to booking —"],
    ["juda oson.", "это просто.", "it's easy."],
    ["Hozir qidirishni boshlash", "Начать поиск", "Start searching"],
    ["Qidiring", "Ищите", "Search"],
    ["Uy yoki avtomobilni tanlang, shahar va sanalarni belgilang.", "Выберите жильё или автомобиль, укажите город и даты.", "Choose a home or car, then select the city and dates."],
    ["Bron qiling", "Бронируйте", "Book"],
    ["Narx va shartlarni ko'ring, mos sanalarni tanlab bron yuboring.", "Проверьте цену и условия, выберите даты и отправьте запрос на бронирование.", "Review the price and terms, choose dates and send a booking request."],
    ["Yo'lga chiqing", "Отправляйтесь в путь", "Hit the road"],
    ["Shaxsiy kabinetingizda bron holatini kuzatib boring.", "Следите за статусом бронирования в личном кабинете.", "Track your booking status in your account."],
    ["O'zbekistonda qulay ijara — uylar va avtomobillar bir joyda.", "Удобная аренда в Узбекистане — жильё и автомобили в одном месте.", "Convenient rentals in Uzbekistan — homes and cars in one place."],
    ["Yangi ijara topish", "Найти новую аренду", "Find a new rental"],
    ["Barcha rejalaringiz bir joyda.", "Все ваши планы в одном месте.", "All your plans in one place."],
    ["Safaringiz yaxshi o'tsin.", "Хорошей поездки!", "Have a great trip!"],
    ["← Orqaga", "← Назад", "← Back"],
    ["← Barcha variantlar", "← Все варианты", "← All options"],
    ["Qulay uy ijarasi", "Аренда уютного жилья", "Comfortable home rental"],
    ["Avtomobil ijarasi", "Аренда автомобиля", "Car rental"],
    ["har bir kun uchun", "за сутки", "per day"],
    ["kishigacha", "человек", "people max"],
    ["ta", "шт.", ""],
    ["Sig'im", "Вместимость", "Capacity"],
    ["Yotoqxona", "Спальни", "Bedrooms"],
    ["Hammom", "Ванные комнаты", "Bathrooms"],
    ["Uzatmalar qutisi", "Коробка передач", "Transmission"],
    ["Ishlab chiqarilgan yil", "Год выпуска", "Year"],
    ["Tavsif", "Описание", "Description"],
    ["Joylashuv", "Расположение", "Location"],
    ["Aniq manzil bron tasdiqlanish jarayonida mezbon bilan kelishiladi.", "Точный адрес согласовывается с хозяином при подтверждении бронирования.", "The exact address is confirmed with the host during booking confirmation."],
    ["STARTAPP BRONI", "БРОНИРОВАНИЕ STARTAPP", "STARTAPP BOOKING"],
    ["Sanalarni tanlang", "Выберите даты", "Choose dates"],
    ["Kelish / boshlanish", "Заезд / начало", "Check-in / start"],
    ["Ketish / tugash", "Выезд / окончание", "Check-out / end"],
    ["Kunlik narx", "Цена за сутки", "Price per day"],
    ["Davomiyligi", "Продолжительность", "Duration"],
    ["Sanalarni tekshiring", "Проверьте даты", "Check the dates"],
    ["Sanalarni to'g'ri tanlang", "Выберите корректные даты", "Please select valid dates"],
    ["Jami", "Итого", "Total"],
    ["JAMI NARX", "ОБЩАЯ СТОИМОСТЬ", "TOTAL PRICE"],
    ["Bron qilish", "Забронировать", "Book now"],
    ["Bron so'rovi yuboriladi, pul yechilmaydi.", "Будет отправлен запрос на бронирование; деньги не списываются.", "A booking request will be sent; no money will be charged."],
    ["Bron qilish uchun kiring", "Войдите, чтобы забронировать", "Log in to book"],
    ["Akkauntingiz yo'qmi?", "Нет аккаунта?", "Don't have an account?"],
    ["Ro'yxatdan o'ting", "Зарегистрируйтесь", "Sign up"],
    ["SHAXSIY KABINET", "ЛИЧНЫЙ КАБИНЕТ", "YOUR ACCOUNT"],
    ["Bronlaringiz", "Ваши бронирования", "Your bookings"],
    ["Jami bronlar", "Всего бронирований", "Total bookings"],
    ["Kutilmoqda / tasdiqlangan", "Ожидают / подтверждены", "Pending / confirmed"],
    ["Bron holati o'zgarsa, shu sahifadan kuzatishingiz mumkin.", "Здесь можно следить за изменением статуса бронирования.", "You can track booking status updates on this page."],
    ["BOSHLANISH", "НАЧАЛО", "START"],
    ["TUGASH", "ОКОНЧАНИЕ", "END"],
    ["DAVOMIYLIGI", "ДЛИТЕЛЬНОСТЬ", "DURATION"],
    ["Bronni bekor qilish", "Отменить бронирование", "Cancel booking"],
    ["Bron bekor qilingan", "Бронирование отменено", "Booking cancelled"],
    ["Hali bronlaringiz yo'q", "У вас пока нет бронирований", "You don't have any bookings yet"],
    ["O'zingizga mos uy yoki avtomobilni toping — rejalaringizni shu yerdan boshlang.", "Найдите подходящее жильё или автомобиль — начните планировать здесь.", "Find a home or car that suits you and start planning here."],
    ["Ijara variantlarini ko'rish", "Посмотреть варианты аренды", "Browse rentals"],
    ["Ushbu bronni bekor qilmoqchimisiz?", "Вы действительно хотите отменить это бронирование?", "Are you sure you want to cancel this booking?"],
    ["XUSH KELIBSIZ", "С ВОЗВРАЩЕНИЕМ", "WELCOME BACK"],
    ["Yana ko'rishganimizdan xursandmiz.", "Рады снова вас видеть.", "Great to see you again."],
    ["Bronlaringizni ko'rish uchun hisobingizga kiring.", "Войдите в аккаунт, чтобы посмотреть бронирования.", "Log in to view your bookings."],
    ["Foydalanuvchi nomi", "Имя пользователя", "Username"],
    ["Parolingiz", "Ваш пароль", "Your password"],
    ["Parol", "Пароль", "Password"],
    ["Hisobingiz yo'qmi?", "Нет аккаунта?", "Don't have an account?"],
    ["YANGI SAFARLAR UCHUN", "ДЛЯ НОВЫХ ПУТЕШЕСТВИЙ", "FOR NEW ADVENTURES"],
    ["Hisob yarating.", "Создайте аккаунт.", "Create your account."],
    ["Bir necha soniyada ro'yxatdan o'ting va bron qilishni boshlang.", "Зарегистрируйтесь за несколько секунд и начните бронировать.", "Sign up in seconds and start booking."],
    ["Hisob yaratish", "Создать аккаунт", "Create account"],
    ["Hisobingiz bormi?", "Уже есть аккаунт?", "Already have an account?"],
    ["STARTAPP · IJARA QILISHNING OSON USULI", "STARTAPP · ПРОСТОЙ СПОСОБ АРЕНДЫ", "STARTAPP · THE EASY WAY TO RENT"],
    ["Ism", "Имя", "First name"],
    ["Ismingiz", "Ваше имя", "Your first name"],
    ["Elektron pochta", "Электронная почта", "Email address"],
    ["siz@example.com", "you@example.com", "you@example.com"],
    ["Parolni takrorlang", "Повторите пароль", "Confirm password"],
    ["Kamida 8 ta belgi", "Не менее 8 символов", "At least 8 characters"],
    ["Parolni qayta kiriting", "Введите пароль ещё раз", "Re-enter your password"],
    ["Bu elektron pochta allaqachon ro'yxatdan o'tgan.", "Этот адрес электронной почты уже зарегистрирован.", "This email address is already registered."],
    ["Boshlanish sanasi", "Дата начала", "Start date"],
    ["Tugash sanasi", "Дата окончания", "End date"],
    ["Mehmonlar / yo'lovchilar", "Гости / пассажиры", "Guests / passengers"],
    ["Boshlanish sanasi bugundan oldin bo'lishi mumkin emas.", "Дата начала не может быть раньше сегодняшнего дня.", "The start date cannot be before today."],
    ["Tugash sanasi boshlanish sanasidan keyin bo'lishi kerak.", "Дата окончания должна быть позже даты начала.", "The end date must be after the start date."],
    ["Kamida 1 kishi bo'lishi kerak.", "Должен быть хотя бы 1 человек.", "At least 1 person is required."],
    ["Bu e'lon uchun eng ko'p sig'im:", "Максимальная вместимость этого объявления:", "Maximum capacity for this listing:"],
    ["Bu e'lon uchun sig'im", "Вместимость этого объявления", "Capacity for this listing"],
    ["Bu sanalarda e'lon band. Boshqa sanalarni tanlang.", "На эти даты объект занят. Выберите другие даты.", "This listing is booked for these dates. Choose other dates."],
    ["Bu e'lon tanlangan sanalarda band.", "Объект занят на выбранные даты.", "This listing is booked for the selected dates."],
    ["Bu e'lon hozir faol emas.", "Это объявление сейчас неактивно.", "This listing is not currently active."],
    ["Bron muvaffaqiyatli yaratildi! Bron holati: kutilmoqda.", "Бронирование создано! Статус: ожидает подтверждения.", "Booking created successfully! Status: pending."],
    ["Hisobingiz yaratildi. Xush kelibsiz!", "Ваш аккаунт создан. Добро пожаловать!", "Your account has been created. Welcome!"],
    ["Bu bron avval bekor qilingan.", "Это бронирование уже отменено.", "This booking has already been cancelled."],
    ["bron bekor qilindi.", "бронирование отменено.", "booking cancelled."],
    ["Bron topilmadi.", "Бронирование не найдено.", "Booking not found."],
    ["Ko'rsatilmagan", "Не указано", "Not specified"],
    ["Avtomat", "Автомат", "Automatic"],
    ["Mexanika", "Механика", "Manual"],
    ["Kutilmoqda", "Ожидает подтверждения", "Pending"],
    ["Tasdiqlangan", "Подтверждено", "Confirmed"],
    ["Bekor qilingan", "Отменено", "Cancelled"],
    ["Kutilmoqda.", "Ожидает подтверждения.", "Pending."],
    ["Barcha rejalaringiz bir joyda.", "Все ваши планы в одном месте.", "All your plans in one place."],
    ["Menyuni ochish", "Открыть меню", "Open menu"],
    ["Davom etasizmi?", "Продолжить?", "Continue?"],
    ["Tafsilotlari", "Подробнее", "Details"],
    ["turar joy va avtomobil ijarasi", "аренда жилья и автомобилей", "home and car rentals"],
    ["Ijara endi oson", "Аренда стала проще", "Renting made easy"],
    ["Kirish — StartApp", "Вход — StartApp", "Log in — StartApp"],
    ["Ro'yxatdan o'tish — StartApp", "Регистрация — StartApp", "Sign up — StartApp"],
    ["Bronlarim — StartApp", "Мои бронирования — StartApp", "My bookings — StartApp"],
    ["Barcha variantlarni", "Все варианты", "All options"],
    ["bron", "бронирование", "booking"],
    ["Natijalar", "Результаты", "Results"],
    ["Manzil", "Адрес", "Address"],
    ["Narx", "Цена", "Price"],
    ["Tavsiya", "Рекомендуем", "Featured"],
    ["Tafsilotlar", "Подробности", "Details"],
    ["Kishi", "Человек", "People"],
    ["Yil", "Год", "Year"],
    ["Nomi", "Название", "Title"],
    ["Shahar", "Город", "City"],
    ["Noma'lum xatolik", "Неизвестная ошибка", "Unknown error"],
    ["Yorug' va zamonaviy apartament", "Светлые современные апартаменты", "Bright modern apartment"],
    ["Toshkent markaziga qulay masofadagi yorug' va zamonaviy apartament. Toza xonalar, qulay oshxona va dam olish uchun barcha zarur sharoitlar mavjud. Oilaviy sayohat va xizmat safari uchun mos.", "Светлые современные апартаменты недалеко от центра Ташкента. Чистые комнаты, удобная кухня и всё необходимое для отдыха. Подходят для семейной поездки и командировки.", "A bright, modern apartment a convenient distance from central Tashkent. Clean rooms, a well-equipped kitchen and everything needed to relax. Ideal for family trips and business travel."],
    ["Shinam hovlili dam olish uyi", "Уютный дом с двориком для отдыха", "Cozy holiday home with a courtyard"],
    ["Samarqandda oila yoki do'stlar bilan dam olish uchun shinam uy. Keng mehmonxona, jihozlangan oshxona va hovli mavjud. Tarixiy joylarga borish uchun qulay joylashuv.", "Уютный дом в Самарканде для отдыха с семьёй или друзьями. Просторная гостиная, оборудованная кухня и двор. Удобное расположение для посещения исторических достопримечательностей.", "A cozy home in Samarkand for a stay with family or friends. It has a spacious living room, a fully equipped kitchen and a courtyard, with easy access to historic attractions."],
    ["Minimalistik shahar studiyasi", "Минималистичная городская студия", "Minimalist city studio"],
    ["Yolg'iz sayohatchi yoki juftlik uchun ixcham, ozoda va did bilan jihozlangan studiya. Tez internet, qulay ish stoli va transportga yaqin manzil.", "Компактная, чистая и со вкусом оформленная студия для одного путешественника или пары. Быстрый интернет, удобный рабочий стол и близость к транспорту.", "A compact, clean and tastefully furnished studio for a solo traveller or couple. It offers fast internet, a convenient desk and easy access to transport."],
    ["Eski shahar yaqinidagi mehmon uyi", "Гостевой дом рядом со Старым городом", "Guesthouse near the Old City"],
    ["Buxoroning tarixiy maskanlarini piyoda kashf etish uchun qulay mehmon uyi. Sokkin muhit, milliy bezaklar va kundalik ehtiyojlar uchun sharoitlar.", "Удобный гостевой дом для пеших прогулок по историческим местам Бухары. Тихая атмосфера, национальный декор и всё необходимое на каждый день.", "A convenient guesthouse for exploring Bukhara's historic sites on foot. It offers a peaceful atmosphere, traditional decor and everyday essentials."],
    ["Shahar ichida va viloyatlarga safar qilish uchun tejamkor, qulay avtomobil. Avtomat uzatmalar qutisi, konditsioner va keng yukxona. Avtomobilni topshirish va qaytarish vaqti oldindan kelishiladi.", "Экономичный и комфортный автомобиль для поездок по городу и регионам. Автоматическая коробка передач, кондиционер и вместительный багажник. Время получения и возврата согласовывается заранее.", "An economical, comfortable car for city drives and trips to other regions. It has an automatic transmission, air conditioning and a spacious trunk. Pickup and return times are agreed in advance."],
    ["Biznes va oilaviy safarlar uchun zamonaviy sedan. Qulay salon, avtomat uzatmalar qutisi va zamonaviy xavfsizlik imkoniyatlari. Yoqilg'i sarfi tejamkor.", "Современный седан для деловых и семейных поездок. Комфортный салон, автоматическая коробка передач и современные системы безопасности. Экономичный расход топлива.", "A modern sedan for business and family trips. It features a comfortable cabin, automatic transmission, modern safety features and efficient fuel consumption."],
    ["Shahar va uzoqroq sayohatlar uchun qulay krossover. Baland o'tirish holati va keng salon tufayli kundalik foydalanish hamda oilaviy yo'l safarlariga mos.", "Удобный кроссовер для города и дальних поездок. Высокая посадка и просторный салон делают его подходящим для повседневных дел и семейных путешествий.", "A versatile crossover for city driving and longer trips. Its higher seating position and spacious cabin make it ideal for everyday use and family travel."],
    ["Zamonaviy va qulay sedan. Ish uchrashuvlari, tantanali tadbirlar yoki shahar tashqarisiga safar uchun mos. Avtomobil topshirish vaqti bron tasdiqlangach kelishiladi.", "Современный и комфортный седан для деловых встреч, торжественных мероприятий и поездок за город. Время передачи автомобиля согласовывается после подтверждения бронирования.", "A modern, comfortable sedan for business meetings, special occasions or trips out of town. Vehicle handover time is arranged after the booking is confirmed."],
    ["Toshkent", "Ташкент", "Tashkent"],
    ["Samarqand", "Самарканд", "Samarkand"],
    ["Buxoro", "Бухара", "Bukhara"],
    ["Yunusobod tumani", "Юнусабадский район", "Yunusabad district"],
    ["Shahar markazidan 10 daqiqa", "В 10 минутах от центра города", "10 minutes from the city centre"],
    ["Mirzo Ulug'bek tumani", "Мирзо-Улугбекский район", "Mirzo Ulugbek district"],
    ["Eski shahar hududi", "Район Старого города", "Old City area"],
    ["Toshkent shahri, olib ketish punkti", "Ташкент, пункт получения автомобиля", "Tashkent, vehicle pickup point"],
    ["Toshkent shahri, Chilonzor", "Ташкент, Чиланзар", "Tashkent, Chilanzar"],
    ["Samarqand shahri, markaz", "Самарканд, центр города", "Samarkand city centre"],
    ["Buxoro shahri, aeroport yaqinida", "Бухара, рядом с аэропортом", "Bukhara, near the airport"]
  ];

  const dictionaries = { uz: {}, ru: {}, en: {} };
  entries.forEach(([uz, ru, en]) => {
    dictionaries.ru[uz] = ru;
    dictionaries.en[uz] = en;
  });
  const keys = entries.map((entry) => entry[0]).sort((a, b) => b.length - a.length);
  let currentLanguage = 'uz';
  const originalText = new WeakMap();
  const originalAttributes = new WeakMap();
  const originalDocumentTitle = document.title;

  function translateText(source, language = currentLanguage) {
    if (!source || language === 'uz') return source;
    let result = source;
    for (const key of keys) {
      const replacement = dictionaries[language][key];
      if (replacement !== undefined && key && result.includes(key)) {
        if (key.trim().length <= 3) {
          const token = key.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          const pattern = new RegExp(`(^|[^\\p{L}\\p{N}_])${token}(?=$|[^\\p{L}\\p{N}_])`, 'gu');
          result = result.replace(pattern, (match, prefix) => prefix + replacement);
        } else {
          result = result.split(key).join(replacement);
        }
      }
    }
    return result;
  }

  function translateDocument(language) {
    currentLanguage = ['uz', 'ru', 'en'].includes(language) ? language : 'uz';
    document.documentElement.lang = currentLanguage;
    document.title = translateText(originalDocumentTitle, currentLanguage);

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (!parent || parent.closest('[data-no-translate="true"]') || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(parent.tagName)) continue;
      if (!originalText.has(node)) originalText.set(node, node.nodeValue);
      node.nodeValue = translateText(originalText.get(node), currentLanguage);
    }

    const attributes = ['placeholder', 'title', 'aria-label', 'data-confirm'];
    document.querySelectorAll('*').forEach((element) => {
      if (element.closest('[data-no-translate="true"]')) return;
      attributes.forEach((attribute) => {
        if (!element.hasAttribute(attribute)) return;
        let saved = originalAttributes.get(element);
        if (!saved) {
          saved = {};
          originalAttributes.set(element, saved);
        }
        if (!(attribute in saved)) saved[attribute] = element.getAttribute(attribute);
        element.setAttribute(attribute, translateText(saved[attribute], currentLanguage));
      });
    });

    // Listing titles and descriptions can be supplied independently per locale.
    document.querySelectorAll('[data-localized-text]').forEach((element) => {
      const translated = element.getAttribute(`data-${currentLanguage}`);
      const fallback = element.getAttribute('data-uz');
      if (translated !== null || fallback !== null) element.textContent = translated || fallback || '';
    });
    document.querySelectorAll('[data-localized-attribute]').forEach((element) => {
      const attribute = element.getAttribute('data-localized-attribute');
      if (!attribute) return;
      const translated = element.getAttribute(`data-${currentLanguage}`);
      const fallback = element.getAttribute('data-uz');
      const value = translated || fallback;
      if (value !== null && value !== undefined) element.setAttribute(attribute, value);
    });
    const localizedPageTitle = document.querySelector('[data-localized-page-title]');
    if (localizedPageTitle) document.title = `${localizedPageTitle.textContent.trim()} — StartApp`;

    const meta = document.querySelector('meta[name="description"]');
    if (meta) {
      const descriptions = {
        uz: "StartApp — O'zbekistonda uy va avtomobilni oson toping va bron qiling.",
        ru: 'StartApp — легко находите и бронируйте жильё и автомобили в Узбекистане.',
        en: 'StartApp — easily find and book homes and cars in Uzbekistan.'
      };
      meta.content = descriptions[currentLanguage];
    }
    document.querySelectorAll('[data-language-switcher]').forEach((select) => {
      select.value = currentLanguage;
    });
    window.startAppLanguage = currentLanguage;
    window.startAppTranslate = translateText;
    window.dispatchEvent(new CustomEvent('startapp:languagechange', { detail: { language: currentLanguage } }));
  }

  let preferred = 'uz';
  try {
    const stored = window.localStorage.getItem('startapp-language');
    if (['uz', 'ru', 'en'].includes(stored)) preferred = stored;
  } catch (_) { /* Local storage can be disabled in private browsing. */ }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-language-switcher]').forEach((select) => {
      select.addEventListener('change', () => {
        const language = select.value;
        try { window.localStorage.setItem('startapp-language', language); } catch (_) { /* Ignore storage restrictions. */ }
        translateDocument(language);
      });
    });
    translateDocument(preferred);
  });
})();
