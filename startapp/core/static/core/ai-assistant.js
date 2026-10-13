(() => {
  "use strict";

  const widget = document.querySelector("[data-ai-widget]");
  if (!widget) return;

  const launcher = widget.querySelector("[data-ai-open]");
  const panel = widget.querySelector("#ai-chat-panel");
  const closeButton = widget.querySelector("[data-ai-close]");
  const form = widget.querySelector("[data-ai-form]");
  const conversation = widget.querySelector("[data-ai-conversation]");
  if (!launcher || !panel || !closeButton) return;

  function setOpen(isOpen) {
    panel.hidden = !isOpen;
    launcher.setAttribute("aria-expanded", String(isOpen));
    if (isOpen) {
      (form?.elements.message || closeButton).focus();
    } else {
      launcher.focus();
    }
  }

  launcher.addEventListener("click", () => setOpen(panel.hidden));
  closeButton.addEventListener("click", () => setOpen(false));
  panel.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
    }
  });

  if (!form || !conversation || widget.dataset.enabled !== "true") return;

  const input = form.elements.message;
  const sendButton = form.querySelector("[data-ai-send]");

  function scrollToLatest() {
    conversation.scrollTop = conversation.scrollHeight;
  }

  function addTurn(role, text, options = {}) {
    const turn = document.createElement("div");
    turn.className = `ai-chat-turn is-${role}${options.loading ? " ai-chat-loading" : ""}`;
    if (role === "user") turn.dataset.noTranslate = "true";
    const bubble = document.createElement("div");
    bubble.className = `ai-chat-bubble${options.error ? " is-error" : ""}`;
    bubble.textContent = text;
    turn.append(bubble);
    conversation.append(turn);
    scrollToLatest();
    return turn;
  }

  function safeUrl(value) {
    if (typeof value !== "string" || !value.trim()) return null;
    try {
      const url = new URL(value, window.location.href);
      return ["http:", "https:"].includes(url.protocol) ? url.href : null;
    } catch {
      return null;
    }
  }

  function appendResults(items) {
    if (!Array.isArray(items) || !items.length) return;

    const language = window.startAppLanguage || "uz";
    const section = document.createElement("section");
    section.className = "ai-chat-results";
    const heading = document.createElement("h3");
    heading.className = "ai-chat-results-heading";
    heading.textContent = "Ijara variantlari";
    section.append(heading);

    const locale = { uz: "uz-UZ", ru: "ru-RU", en: "en-US" }[language] || "uz-UZ";
    const numberFormat = new Intl.NumberFormat(locale);

    for (const item of items) {
      if (!item || typeof item !== "object") continue;
      const card = document.createElement("article");
      card.className = "ai-result-card";
      const localizedTitle = item[language === "ru" ? "title_ru" : language === "en" ? "title_en" : "title"]
        || item.title
        || "";
      const imageUrl = safeUrl(item.image_url);
      if (imageUrl) {
        const image = document.createElement("img");
        image.src = imageUrl;
        image.alt = typeof localizedTitle === "string" ? localizedTitle : "";
        image.loading = "lazy";
        card.append(image);
      }

      const details = document.createElement("div");
      details.className = "ai-result-details";
      const title = document.createElement("strong");
      title.textContent = typeof localizedTitle === "string" ? localizedTitle : "";
      title.dataset.noTranslate = "true";
      details.append(title);

      const location = document.createElement("span");
      const city = typeof item.city === "string" ? item.city : "";
      const region = typeof item.region === "string" ? item.region : "";
      const kind = typeof item.kind === "string" ? item.kind : "";
      const place = document.createElement("span");
      place.dataset.noTranslate = "true";
      place.textContent = region ? `${city}, ${region}` : city;
      location.append(place);
      if (kind) {
        const category = document.createElement("span");
        category.textContent = kind;
        location.append(" · ", category);
      }
      details.append(location);

      const price = Number(item.total_price || item.price_per_day);
      const priceLabel = document.createElement("span");
      priceLabel.className = "ai-result-price";
      if (Number.isFinite(price)) {
        const period = item.total_price
          ? ` · ${numberFormat.format(Number(item.rental_days) || 0)} kun`
          : " / kun";
        priceLabel.textContent = `${numberFormat.format(price)} so'm${period}`;
      }
      details.append(priceLabel);

      const linkUrl = safeUrl(item.url);
      if (linkUrl) {
        const link = document.createElement("a");
        link.className = "ai-result-link";
        link.href = linkUrl;
        link.textContent = "Ko'rish";
        details.append(link);
      }

      card.append(details);
      section.append(card);
    }
    if (section.querySelector(".ai-result-card")) {
      conversation.append(section);
      scrollToLatest();
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message || sendButton.disabled) return;

    addTurn("user", message);
    input.value = "";
    input.disabled = true;
    sendButton.disabled = true;
    form.setAttribute("aria-busy", "true");
    const loadingTurn = addTurn("assistant", "Savolingiz ustida ishlayapman…", { loading: true });

    try {
      const response = await fetch(form.action, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value,
        },
        body: JSON.stringify({
          message,
          language: window.startAppLanguage || "uz",
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : "AI so'rovini bajarib bo'lmadi.");
      }

      const reply = typeof data.message === "string" ? data.message : "AI javobi olinmadi.";
      loadingTurn.remove();
      addTurn("assistant", reply);
      appendResults(data.results);
    } catch (error) {
      loadingTurn.remove();
      addTurn("assistant", error.message || "Ulanishda xatolik yuz berdi.", { error: true });
    } finally {
      input.disabled = false;
      sendButton.disabled = false;
      form.removeAttribute("aria-busy");
      input.focus();
    }
  });
})();
