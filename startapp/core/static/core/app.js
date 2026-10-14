(() => {
  'use strict';

  const menuToggle = document.querySelector('[data-menu-toggle]');
  const nav = document.querySelector('#main-nav');
  if (menuToggle && nav) {
    const updateMenuLabel = () => {
      const source = nav.classList.contains('menu-open') ? 'Menyuni yopish' : 'Menyuni ochish';
      const language = window.startAppLanguage || 'uz';
      const label = window.startAppTranslate ? window.startAppTranslate(source, language) : source;
      menuToggle.setAttribute('aria-label', label);
    };
    menuToggle.addEventListener('click', () => {
      const opened = nav.classList.toggle('menu-open');
      menuToggle.setAttribute('aria-expanded', String(opened));
      menuToggle.textContent = opened ? '×' : '☰';
      updateMenuLabel();
    });
    nav.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
      nav.classList.remove('menu-open');
      menuToggle.setAttribute('aria-expanded', 'false');
      menuToggle.textContent = '☰';
      updateMenuLabel();
    }));
    window.addEventListener('startapp:languagechange', updateMenuLabel);
  }

  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      const promptText = form.getAttribute('data-confirm') || 'Davom etasizmi?';
      if (!window.confirm(promptText)) event.preventDefault();
    });
  });

  document.querySelectorAll('[data-booking-form]').forEach((form) => {
    const checkIn = form.querySelector('[name="check_in"]');
    const checkOut = form.querySelector('[name="check_out"]');
    const guests = form.querySelector('[name="guests"]');
    const daysLabel = form.querySelector('#booking-days');
    const totalLabel = form.querySelector('#booking-total');
    const price = Number(form.getAttribute('data-price') || 0);
    const formatMoney = (value) => {
      const language = window.startAppLanguage || 'uz';
      const locale = { uz: 'uz-UZ', ru: 'ru-RU', en: 'en-US' }[language] || 'uz-UZ';
      const currency = { uz: "so'm", ru: 'сум', en: 'UZS' }[language] || "so'm";
      return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value) + ' ' + currency;
    };
    const translate = (text) => window.startAppTranslate ? window.startAppTranslate(text) : text;

    const updateTotal = () => {
      if (checkIn && checkOut && checkIn.value && checkOut.value) {
        const start = new Date(`${checkIn.value}T00:00:00`);
        const end = new Date(`${checkOut.value}T00:00:00`);
        const days = Math.round((end - start) / 86400000);
        if (days > 0) {
          if (daysLabel) daysLabel.textContent = `${days} ${translate('kun')}`;
          if (totalLabel) totalLabel.textContent = formatMoney(days * price);
        } else {
          if (daysLabel) daysLabel.textContent = translate('Sanalarni tekshiring');
          if (totalLabel) totalLabel.textContent = '—';
        }
      } else {
        if (daysLabel) daysLabel.textContent = translate('Sanalarni tanlang');
        if (totalLabel) totalLabel.textContent = '—';
      }
      if (checkOut && checkIn && checkIn.value) {
        const start = new Date(`${checkIn.value}T00:00:00`);
        start.setDate(start.getDate() + 1);
        const minEnd = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;
        checkOut.min = minEnd;
      }
    };

    [checkIn, checkOut, guests].filter(Boolean).forEach((field) => field.addEventListener('change', updateTotal));
    updateTotal();
    window.addEventListener('startapp:languagechange', updateTotal);
    form.addEventListener('submit', (event) => {
      if (!checkIn.value || !checkOut.value || checkOut.value <= checkIn.value) {
        event.preventDefault();
        if (daysLabel) daysLabel.textContent = translate("Sanalarni to'g'ri tanlang");
        checkOut.reportValidity();
      }
    });
  });

  // Keep the search checkout date after the check-in date.
  const searchIn = document.querySelector('.search-form [name="check_in"]');
  const searchOut = document.querySelector('.search-form [name="check_out"]');
  if (searchIn && searchOut) {
    const updateSearchDates = () => {
      if (!searchIn.value) return;
      const start = new Date(`${searchIn.value}T00:00:00`);
      start.setDate(start.getDate() + 1);
      const min = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;
      searchOut.min = min;
      if (searchOut.value && searchOut.value < min) searchOut.value = '';
    };
    searchIn.addEventListener('change', updateSearchDates);
    updateSearchDates();
  }

  // Flash messages fade out after 5 seconds; a click closes one right away.
  const dismissToast = (toast) => {
    if (toast.classList.contains('toast-leaving')) return;
    toast.classList.add('toast-leaving');
    window.setTimeout(() => toast.remove(), 300);
  };
  document.querySelectorAll('.toast-stack .toast').forEach((toast) => {
    window.setTimeout(() => dismissToast(toast), 5000);
    toast.addEventListener('click', () => dismissToast(toast));
  });
})();
