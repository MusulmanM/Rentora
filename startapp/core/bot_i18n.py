"""Texts of the Rentora Telegram bot in Uzbek, Russian and English.

Every message the bot sends goes through `t(key, lang, **values)`. The language is chosen by the
user in the bot (/start or /language) and stored per Telegram chat (TelegramChatLanguage).
"""
from decimal import Decimal

LANGUAGES = ("uz", "ru", "en")
DEFAULT = "uz"
LANGUAGE_BUTTONS = {"uz": "🇺🇿 O'zbekcha", "ru": "🇷🇺 Русский", "en": "🇬🇧 English"}

TEXTS = {
    "choose_language": {
        "uz": "Tilni tanlang:", "ru": "Выберите язык:", "en": "Choose a language:",
    },
    "language_set": {
        "uz": "Til tanlandi: O'zbekcha ✅", "ru": "Язык выбран: Русский ✅", "en": "Language set: English ✅",
    },
    "welcome_need_phone": {
        "uz": "Rentora botiga xush kelibsiz! 👋\n\nSaytda ro'yxatdan o'tish va bron xabarlarini olish uchun pastdagi tugma orqali telefon raqamingizni yuboring.",
        "ru": "Добро пожаловать в бот Rentora! 👋\n\nЧтобы зарегистрироваться на сайте и получать уведомления о бронированиях, отправьте номер телефона кнопкой ниже.",
        "en": "Welcome to the Rentora bot! 👋\n\nTo sign up on the website and get booking updates, share your phone number with the button below.",
    },
    "share_phone": {"uz": "📱 Telefon raqamni yuborish", "ru": "📱 Отправить номер телефона", "en": "📱 Share phone number"},
    "only_uz_phone": {
        "uz": "Faqat O'zbekiston telefon raqami bilan ro'yxatdan o'tish mumkin.",
        "ru": "Зарегистрироваться можно только с узбекским номером телефона.",
        "en": "Only an Uzbekistan phone number can be used to sign up.",
    },
    "phone_linked": {
        "uz": "Telefon raqamingiz bog'landi ✅\n\nEndi saytda ro'yxatdan o'tishingiz mumkin:\n{site}/accounts/register/",
        "ru": "Номер телефона привязан ✅\n\nТеперь можно зарегистрироваться на сайте:\n{site}/accounts/register/",
        "en": "Your phone number is linked ✅\n\nYou can now sign up on the website:\n{site}/accounts/register/",
    },
    "phone_taken": {
        "uz": "Bu Telegram hisobi yoki telefon raqami boshqa akkauntga bog'langan.",
        "ru": "Этот аккаунт Telegram или номер телефона уже привязан к другому аккаунту.",
        "en": "This Telegram account or phone number is already linked to another account.",
    },
    "main_menu": {
        "uz": "Asosiy menyu. Kerakli bo'limni tanlang 👇", "ru": "Главное меню. Выберите раздел 👇", "en": "Main menu. Choose a section 👇",
    },
    "menu_bookings": {"uz": "📋 Bronlarim", "ru": "📋 Мои бронирования", "en": "📋 My bookings"},
    "menu_site": {"uz": "🌐 Sayt", "ru": "🌐 Сайт", "en": "🌐 Website"},
    "menu_help": {"uz": "❓ Yordam", "ru": "❓ Помощь", "en": "❓ Help"},
    "menu_language": {"uz": "🌍 Til", "ru": "🌍 Язык", "en": "🌍 Language"},
    "open_site": {
        "uz": "Rentora sayti: {site}", "ru": "Сайт Rentora: {site}", "en": "Rentora website: {site}",
    },
    "help": {
        "uz": "Rentora — uy va avtomobil ijarasi.\n\n• Sayt: {site}\n• Admin bilan yozishish: {site}/help/chat/\n• Bron holatlari, tasdiqlash kodlari va eslatmalar shu botga keladi.\n\nBuyruqlar: /bookings — bronlarim, /language — tilni o'zgartirish, /help — yordam.",
        "ru": "Rentora — аренда жилья и автомобилей.\n\n• Сайт: {site}\n• Написать администратору: {site}/help/chat/\n• Статусы бронирований, коды подтверждения и напоминания приходят в этот бот.\n\nКоманды: /bookings — мои бронирования, /language — сменить язык, /help — помощь.",
        "en": "Rentora — home and car rentals.\n\n• Website: {site}\n• Chat with an admin: {site}/help/chat/\n• Booking updates, confirmation codes and reminders come to this bot.\n\nCommands: /bookings — my bookings, /language — change language, /help — help.",
    },
    "unknown": {
        "uz": "Menyudan bo'limni tanlang yoki /help yozing.", "ru": "Выберите раздел в меню или напишите /help.", "en": "Pick a section from the menu or type /help.",
    },
    "bookings_not_linked": {
        "uz": "Bronlarni ko'rish uchun avval saytda shu telefon raqami bilan ro'yxatdan o'ting: {site}/accounts/register/",
        "ru": "Чтобы видеть бронирования, сначала зарегистрируйтесь на сайте с этим номером: {site}/accounts/register/",
        "en": "To see bookings, first sign up on the website with this phone number: {site}/accounts/register/",
    },
    "bookings_none": {"uz": "Sizda hali bron yo'q.", "ru": "У вас пока нет бронирований.", "en": "You have no bookings yet."},
    "bookings_header": {"uz": "Oxirgi bronlaringiz:", "ru": "Ваши последние бронирования:", "en": "Your latest bookings:"},
    "bookings_footer": {
        "uz": "Barchasi: {site}/my-bookings/", "ru": "Все бронирования: {site}/my-bookings/", "en": "All bookings: {site}/my-bookings/",
    },
    "otp_register": {
        "uz": "Rentora ro'yxatdan o'tish kodi: {code}\nKod 10 daqiqa amal qiladi.",
        "ru": "Код регистрации Rentora: {code}\nКод действует 10 минут.",
        "en": "Rentora sign-up code: {code}\nThe code is valid for 10 minutes.",
    },
    "otp_phone": {
        "uz": "Rentora telefon tasdiqlash kodi: {code}\nKod 10 daqiqa amal qiladi.",
        "ru": "Код подтверждения телефона Rentora: {code}\nКод действует 10 минут.",
        "en": "Rentora phone confirmation code: {code}\nThe code is valid for 10 minutes.",
    },
    "password_code": {
        "uz": "Rentora: parolni tiklash kodi {code}\nKod 10 daqiqa amal qiladi.\nAgar parolni siz tiklamayotgan bo'lsangiz, bu xabarga e'tibor bermang va kodni hech kimga bermang.",
        "ru": "Rentora: код восстановления пароля {code}\nКод действует 10 минут.\nЕсли вы не восстанавливаете пароль, проигнорируйте это сообщение и никому не сообщайте код.",
        "en": "Rentora: password reset code {code}\nThe code is valid for 10 minutes.\nIf you are not resetting your password, ignore this message and never share the code.",
    },
    "password_changed": {
        "uz": "Rentora: hisobingiz paroli o'zgartirildi. Agar buni siz qilmagan bo'lsangiz, darhol saytdagi \"Admin bilan yozishish\" orqali adminga xabar bering.",
        "ru": "Rentora: пароль вашего аккаунта изменён. Если это были не вы, сразу сообщите администратору через «Написать администратору» на сайте.",
        "en": "Rentora: your account password was changed. If this wasn't you, tell an admin right away via \"Chat with an admin\" on the website.",
    },
    # Payout card review
    "card_review_admin": {
        "uz": "💳 Yangi karta tasdiq kutmoqda.\nIjara beruvchi: {provider}\nKarta: {brand} {card}\nEgasi: {holder}\n\nTasdiqlash: {url}",
        "ru": "💳 Новая карта ждёт подтверждения.\nАрендодатель: {provider}\nКарта: {brand} {card}\nВладелец: {holder}\n\nПодтвердить: {url}",
        "en": "💳 A new card is waiting for approval.\nProvider: {provider}\nCard: {brand} {card}\nHolder: {holder}\n\nReview: {url}",
    },
    "card_approved": {
        "uz": "✅ Kartangiz ({card}) tasdiqlandi. Endi mijozlar e'lonlaringiz uchun Click / Payme orqali to'lay oladi.",
        "ru": "✅ Ваша карта ({card}) подтверждена. Теперь клиенты могут оплачивать ваши объявления через Click / Payme.",
        "en": "✅ Your card ({card}) is approved. Customers can now pay for your listings with Click / Payme.",
    },
    "card_rejected": {
        "uz": "❌ Kartangiz ({card}) tasdiqlanmadi. Iltimos, kabinetdagi \"To'lov sozlamalari\" bo'limida karta ma'lumotlarini tekshirib, qayta kiriting.",
        "ru": "❌ Ваша карта ({card}) не подтверждена. Проверьте данные карты в разделе «Настройки оплаты» и введите их снова.",
        "en": "❌ Your card ({card}) was not approved. Please check the card details in \"Payment settings\" and enter them again.",
    },
    # Monthly rentals and instalments
    "months_line": {"uz": "Ijara: {months} oy (oyiga {price} so'm)", "ru": "Аренда: {months} мес. ({price} сум в месяц)", "en": "Rental: {months} months ({price} UZS a month)"},
    "plan_line": {
        "uz": "To'lov rejasi: {plan} — {count} ta to'lov, birinchisi {first} so'm",
        "ru": "План оплаты: {plan} — платежей: {count}, первый {first} сум",
        "en": "Payment plan: {plan} — {count} payments, first {first} UZS",
    },
    "installment_paid_customer": {
        "uz": "✅ {number}-to'lov qabul qilindi: {amount} so'm.\nQolgan: {left} so'm ({left_count} ta to'lov).\n{title}",
        "ru": "✅ Платёж №{number} получен: {amount} сум.\nОсталось: {left} сум (платежей: {left_count}).\n{title}",
        "en": "✅ Payment {number} received: {amount} UZS.\nLeft: {left} UZS ({left_count} payments).\n{title}",
    },
    "installment_paid_provider": {
        "uz": "✅ {customer}: {number}-to'lov qabul qilindi — {amount} so'm.\nQolgan: {left} so'm ({left_count} ta to'lov).\n{title}",
        "ru": "✅ {customer}: платёж №{number} получен — {amount} сум.\nОсталось: {left} сум (платежей: {left_count}).\n{title}",
        "en": "✅ {customer}: payment {number} received — {amount} UZS.\nLeft: {left} UZS ({left_count} payments).\n{title}",
    },
    "installment_due_customer": {
        "uz": "🔔 Eslatma: {date} kuni {number}-to'lov — {amount} so'm.\n{title}\nTo'lov: {url}",
        "ru": "🔔 Напоминание: {date} платёж №{number} — {amount} сум.\n{title}\nОплата: {url}",
        "en": "🔔 Reminder: payment {number} of {amount} UZS is due on {date}.\n{title}\nPay: {url}",
    },
    "installment_due_provider": {
        "uz": "🔔 {date} kuni {customer} {number}-to'lovni to'lashi kerak: {amount} so'm.\n{title}",
        "ru": "🔔 {date} {customer} должен внести платёж №{number}: {amount} сум.\n{title}",
        "en": "🔔 {customer} has payment {number} of {amount} UZS due on {date}.\n{title}",
    },
    "installment_overdue_customer": {
        "uz": "⚠ {number}-to'lov muddati {days} kun o'tdi: {amount} so'm. Iltimos, to'lovni amalga oshiring.\n{title}\n{url}",
        "ru": "⚠ Платёж №{number} просрочен на {days} дн.: {amount} сум. Пожалуйста, оплатите.\n{title}\n{url}",
        "en": "⚠ Payment {number} is {days} days overdue: {amount} UZS. Please pay.\n{title}\n{url}",
    },
    "installment_overdue_provider": {
        "uz": "⚠ {customer} {number}-to'lovni {days} kun kechiktirdi: {amount} so'm.\n{title}",
        "ru": "⚠ {customer} просрочил платёж №{number} на {days} дн.: {amount} сум.\n{title}",
        "en": "⚠ {customer} is {days} days late with payment {number}: {amount} UZS.\n{title}",
    },
    # Booking notices
    "customer": {"uz": "Mijoz", "ru": "Клиент", "en": "Customer"},
    "price": {"uz": "Narxi: {price} so'm / kun", "ru": "Цена: {price} сум / день", "en": "Price: {price} UZS / day"},
    "period": {
        "uz": "Muddati: {days} kun ({start} — {end})", "ru": "Срок: {days} дн. ({start} — {end})", "en": "Period: {days} days ({start} — {end})",
    },
    "total": {"uz": "Jami: {total} so'm", "ru": "Итого: {total} сум", "en": "Total: {total} UZS"},
    "payment": {"uz": "To'lov: {method}", "ru": "Оплата: {method}", "en": "Payment: {method}"},
    "requested_at": {"uz": "Bron so'rovi: {time}", "ru": "Запрос брони: {time}", "en": "Requested: {time}"},
    "event_requested_provider": {"uz": "Yangi bron so'rovi.", "ru": "Новый запрос на бронирование.", "en": "New booking request."},
    "event_requested_customer": {
        "uz": "Bron so'rovingiz ijaraga beruvchiga yuborildi.", "ru": "Ваш запрос отправлен арендодателю.", "en": "Your request was sent to the provider.",
    },
    "event_rejected_provider": {"uz": "Bron so'rovini rad etdingiz.", "ru": "Вы отклонили запрос на бронирование.", "en": "You declined the booking request."},
    "event_rejected_customer": {
        "uz": "Ijaraga beruvchi bron so'rovingizni rad etdi.", "ru": "Арендодатель отклонил ваш запрос.", "en": "The provider declined your request.",
    },
    "event_cancelled": {"uz": "Bron bekor qilindi.", "ru": "Бронирование отменено.", "en": "The booking was cancelled."},
    "event_confirmed_provider": {"uz": "Bronni tasdiqladingiz.", "ru": "Вы подтвердили бронирование.", "en": "You confirmed the booking."},
    "event_confirmed_customer": {"uz": "Bron tasdiqlandi.", "ru": "Бронирование подтверждено.", "en": "Your booking is confirmed."},
    "event_handed_over_provider": {"uz": "Mahsulot mijozga ijaraga topshirildi.", "ru": "Товар передан клиенту.", "en": "The item was handed over to the customer."},
    "event_handed_over_customer": {
        "uz": "Bugun mahsulotni olib ketishingiz mumkin.", "ru": "Сегодня можно забрать товар.", "en": "You can pick up the item today.",
    },
    "event_ending_provider": {
        "uz": "Bugun ijara muddati tugaydi. Mahsulot qaytarilgach, kabinetda \"Mahsulot qaytarildi\" tugmasini bosing.",
        "ru": "Сегодня заканчивается срок аренды. Когда товар вернут, нажмите «Товар возвращён» в кабинете.",
        "en": "The rental ends today. When the item is back, press \"Item returned\" in your dashboard.",
    },
    "event_ending_customer": {
        "uz": "Bugun ijara muddati tugaydi. Iltimos, mahsulotni bugun qaytaring.\nKechiksangiz, har bir kun uchun {rate} so'm qarz yoziladi.",
        "ru": "Сегодня заканчивается срок аренды. Пожалуйста, верните товар сегодня.\nЗа каждый день просрочки начисляется долг {rate} сум.",
        "en": "The rental ends today. Please return the item today.\nEach late day adds a debt of {rate} UZS.",
    },
    "event_overdue_provider": {
        "uz": "Mijoz mahsulotni qaytarmadi: {days} kun kechikish.\nHozirgi qarz: {debt} so'm. Qaytarishda qarzni oling.",
        "ru": "Клиент не вернул товар: просрочка {days} дн.\nТекущий долг: {debt} сум. Получите его при возврате.",
        "en": "The customer has not returned the item: {days} days late.\nDebt so far: {debt} UZS. Collect it on return.",
    },
    "event_overdue_customer": {
        "uz": "⚠ Ogohlantirish: ijara muddati {days} kun oldin tugagan, mahsulot hali qaytarilmagan.\nHar bir kechikkan kun uchun {rate} so'm qarz yoziladi. Hozirgi qarz: {debt} so'm.\nMahsulotni zudlik bilan qaytaring — qarz qaytarishda to'lanishi shart.",
        "ru": "⚠ Предупреждение: срок аренды закончился {days} дн. назад, товар ещё не возвращён.\nЗа каждый день просрочки начисляется {rate} сум. Текущий долг: {debt} сум.\nСрочно верните товар — долг оплачивается при возврате.",
        "en": "⚠ Warning: the rental ended {days} days ago and the item is not back yet.\nEach late day adds {rate} UZS. Debt so far: {debt} UZS.\nPlease return the item now — the debt must be paid on return.",
    },
    "event_returned": {
        "uz": "Mahsulot qaytarildi. Ijara yakunlandi, rahmat!", "ru": "Товар возвращён. Аренда завершена, спасибо!", "en": "The item was returned. Rental complete, thank you!",
    },
    "returned_debt": {
        "uz": "Kechikish qarzi: {debt} so'm ({days} kun) — to'landi.",
        "ru": "Долг за просрочку: {debt} сум ({days} дн.) — оплачен.",
        "en": "Late-return debt: {debt} UZS ({days} days) — paid.",
    },
}

STATUS = {
    "pending": {"uz": "Kutilmoqda", "ru": "Ожидает", "en": "Pending"},
    "confirmed": {"uz": "Tasdiqlangan", "ru": "Подтверждено", "en": "Confirmed"},
    "handed_over": {"uz": "Mijozga topshirilgan", "ru": "Передано клиенту", "en": "Handed over"},
    "returned": {"uz": "Qaytarilgan", "ru": "Возвращено", "en": "Returned"},
    "cancelled": {"uz": "Bekor qilingan", "ru": "Отменено", "en": "Cancelled"},
}
PAYMENT = {
    "cash": {"uz": "Naqd", "ru": "Наличные", "en": "Cash"},
    "click": {"uz": "Click", "ru": "Click", "en": "Click"},
    "payme": {"uz": "Payme", "ru": "Payme", "en": "Payme"},
}
PLAN = {
    "full": {"uz": "To'liq", "ru": "Полностью", "en": "In full"},
    "monthly": {"uz": "Har oy", "ru": "Каждый месяц", "en": "Every month"},
    "biweekly": {"uz": "Har 15 kunda", "ru": "Каждые 15 дней", "en": "Every 15 days"},
}
COMMANDS = {
    "uz": [("start", "Boshlash"), ("bookings", "Bronlarim"), ("language", "Tilni o'zgartirish"), ("help", "Yordam")],
    "ru": [("start", "Начать"), ("bookings", "Мои бронирования"), ("language", "Сменить язык"), ("help", "Помощь")],
    "en": [("start", "Start"), ("bookings", "My bookings"), ("language", "Change language"), ("help", "Help")],
}


def normalize(language):
    return language if language in LANGUAGES else DEFAULT


def t(key, language=DEFAULT, **values):
    variants = TEXTS[key]
    text = variants.get(normalize(language)) or variants[DEFAULT]
    return text.format(**values) if values else text


def label(table, value, language=DEFAULT):
    return table.get(value, {}).get(normalize(language), value)


def money(amount):
    """1470000 -> "1 470 000" (spaces read well in every language)."""
    try:
        return f"{Decimal(amount):,.0f}".replace(",", " ")
    except Exception:  # noqa: BLE001 - never break a notice over formatting
        return str(amount)


def localized_title(listing, language):
    language = normalize(language)
    if language == "ru" and listing.title_ru:
        return listing.title_ru
    if language == "en" and listing.title_en:
        return listing.title_en
    return listing.title
