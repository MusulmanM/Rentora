(() => {
  const assistant = document.querySelector("[data-ai-search]");
  if (!assistant) return;

  const form = assistant.querySelector(".ai-search-form");
  const status = assistant.querySelector("[data-ai-status]");
  const results = assistant.querySelector("[data-ai-results]");
  if (!form || !status || !results) return;

  const button = form.querySelector("button[type=submit]");
  const translate = (text) => window.startAppTranslate
    ? window.startAppTranslate(text, window.startAppLanguage || "uz")
    : text;

  function addText(parent, tag, className, value) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = translate(value);
    parent.append(element);
    return element;
  }

  function renderResults(items) {
    results.replaceChildren();
    const language = window.startAppLanguage || "uz";
    const locale = { uz: "uz-UZ", ru: "ru-RU", en: "en-US" }[language];
    const numberFormat = new Intl.NumberFormat(locale);
    for (const item of items) {
      const card = document.createElement("article");
      card.className = "ai-result-card";
      if (item.image_url) {
        try {
          const imageUrl = new URL(item.image_url, window.location.href);
          if (["http:", "https:"].includes(imageUrl.protocol)) {
            const image = document.createElement("img");
            image.src = imageUrl.href;
            image.alt = item.title;
            image.loading = "lazy";
            card.append(image);
          }
        } catch {
          // A missing or invalid optional image should not hide the rental result.
        }
      }
      const details = document.createElement("div");
      details.className = "ai-result-details";
      const title = addText(details, "strong", "", item.title);
      title.dataset.localizedText = "";
      title.dataset.uz = item.title;
      title.dataset.ru = item.title_ru || item.title;
      title.dataset.en = item.title_en || item.title;
      addText(details, "span", "", `${item.city}${item.region ? `, ${item.region}` : ""} · ${item.kind}`);
      const price = item.total_price
        ? `${numberFormat.format(Number(item.total_price))} so'm · ${item.rental_days} kun`
        : `${numberFormat.format(Number(item.price_per_day))} so'm / kun`;
      addText(details, "span", "ai-result-price", price);
      const link = document.createElement("a");
      link.className = "btn btn-dark btn-small";
      link.href = item.url;
      link.textContent = translate("Ko'rish");
      details.append(link);
      card.append(details);
      results.append(card);
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.textContent = translate("Ijara variantlari qidirilmoqda…");
    status.classList.remove("is-error");
    results.replaceChildren();
    button.disabled = true;

    try {
      const response = await fetch(form.action, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value,
        },
        body: JSON.stringify({ message: form.elements.message.value.trim() }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "AI so'rovini bajarib bo'lmadi.");
      status.textContent = translate(data.message);
      renderResults(data.results || []);
    } catch (error) {
      status.textContent = translate(error.message || "Ulanishda xatolik yuz berdi.");
      status.classList.add("is-error");
    } finally {
      button.disabled = false;
    }
  });
})();
