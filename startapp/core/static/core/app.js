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
    const monthsField = form.querySelector('[name="months"]');
    const daysLabel = form.querySelector('#booking-days');
    const totalLabel = form.querySelector('#booking-total');
    const scheduleBox = form.querySelector('[data-booking-schedule]');
    const price = Number(form.getAttribute('data-price') || 0);
    const priceMonth = Number(form.getAttribute('data-price-month') || 0);
    const unitInputs = [...form.querySelectorAll('[name="rental_unit"]')];
    const planInputs = [...form.querySelectorAll('[name="payment_plan"]')];
    const formatMoney = (value) => {
      const language = window.startAppLanguage || 'uz';
      const locale = { uz: 'uz-UZ', ru: 'ru-RU', en: 'en-US' }[language] || 'uz-UZ';
      const currency = { uz: "so'm", ru: 'сум', en: 'UZS' }[language] || "so'm";
      // Same grouping as the server-rendered prices: "6 000 000 so'm".
      const number = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value);
      return (language === 'en' ? number : number.replace(/[,  ]/g, ' ')) + ' ' + currency;
    };
    const translate = (text) => window.startAppTranslate ? window.startAppTranslate(text) : text;
    const unit = () => (unitInputs.find((input) => input.checked) || {}).value || 'day';
    const plan = () => (planInputs.find((input) => input.checked) || {}).value || 'full';
    const addMonths = (date, months) => {
      const result = new Date(date);
      const day = result.getDate();
      result.setDate(1);
      result.setMonth(result.getMonth() + months);
      const lastDay = new Date(result.getFullYear(), result.getMonth() + 1, 0).getDate();
      result.setDate(Math.min(day, lastDay));
      return result;
    };
    const setEmpty = (text) => {
      if (daysLabel) daysLabel.textContent = translate(text);
      if (totalLabel) totalLabel.textContent = '—';
      if (scheduleBox) scheduleBox.hidden = true;
    };

    const toggleUnit = () => {
      const monthly = unit() === 'month';
      form.querySelectorAll('[data-monthly-only]').forEach((element) => { element.hidden = !monthly; });
      form.querySelectorAll('[data-daily-only]').forEach((element) => { element.hidden = monthly; });
      if (checkOut) checkOut.required = !monthly;
      if (!monthly) {
        const full = planInputs.find((input) => input.value === 'full');
        if (full) full.checked = true;
      }
    };

    const updateMonthly = () => {
      const months = Number((monthsField && monthsField.value) || 0);
      // "Every month" needs at least two months.
      planInputs.forEach((input) => {
        if (input.value !== 'monthly') return;
        input.disabled = months < 2;
        if (input.disabled && input.checked) {
          const full = planInputs.find((option) => option.value === 'full');
          if (full) full.checked = true;
        }
      });
      if (!months || !priceMonth) {
        setEmpty('Necha oyga ijaraga olishingizni tanlang.');
        return;
      }
      const total = months * priceMonth;
      if (daysLabel) daysLabel.textContent = `${months} ${translate('oy')}`;
      if (totalLabel) totalLabel.textContent = formatMoney(total);
      let parts = 1;
      if (plan() === 'monthly') parts = months;
      if (plan() === 'biweekly') {
        const start = checkIn && checkIn.value ? new Date(`${checkIn.value}T00:00:00`) : new Date();
        const days = Math.round((addMonths(start, months) - start) / 86400000);
        parts = Math.max(1, Math.ceil(days / 15));
      }
      if (scheduleBox) {
        scheduleBox.hidden = parts < 2;
        if (parts > 1) {
          scheduleBox.textContent = `${translate("Birinchi to'lov")}: ${formatMoney(Math.floor(total / parts))} · ${parts} ${translate("ta to'lov")}`;
        }
      }
    };

    const updateTotal = () => {
      if (unit() === 'month') {
        updateMonthly();
        return;
      }
      if (scheduleBox) scheduleBox.hidden = true;
      if (checkIn && checkOut && checkIn.value && checkOut.value) {
        const start = new Date(`${checkIn.value}T00:00:00`);
        const end = new Date(`${checkOut.value}T00:00:00`);
        const days = Math.round((end - start) / 86400000);
        if (days > 0) {
          if (daysLabel) daysLabel.textContent = `${days} ${translate('kun')}`;
          if (totalLabel) totalLabel.textContent = formatMoney(days * price);
        } else {
          setEmpty('Sanalarni tekshiring');
        }
      } else {
        setEmpty('Sanalarni tanlang');
      }
      if (checkOut && checkIn && checkIn.value) {
        const start = new Date(`${checkIn.value}T00:00:00`);
        start.setDate(start.getDate() + 1);
        const minEnd = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, '0')}-${String(start.getDate()).padStart(2, '0')}`;
        checkOut.min = minEnd;
      }
    };

    [checkIn, checkOut, guests, monthsField].filter(Boolean).forEach((field) => field.addEventListener('change', updateTotal));
    [...unitInputs, ...planInputs].forEach((input) => input.addEventListener('change', () => { toggleUnit(); updateTotal(); }));
    toggleUnit();
    updateTotal();
    window.addEventListener('startapp:languagechange', updateTotal);
    form.addEventListener('submit', (event) => {
      if (unit() === 'month') {
        if (!checkIn.value || !monthsField || !monthsField.value) {
          event.preventDefault();
          (checkIn.value ? monthsField : checkIn).reportValidity();
        }
        return;
      }
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

  // Chart bars: set heights through the CSSOM so the CSP needs no 'unsafe-inline' styles.
  document.querySelectorAll('[data-bar-height]').forEach((bar) => {
    const value = Math.max(0, Math.min(100, Number(bar.dataset.barHeight) || 0));
    bar.style.height = `${value}%`;
  });

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
