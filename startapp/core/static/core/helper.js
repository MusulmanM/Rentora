(() => {
  "use strict";

  const t = (text) => (window.startAppTranslate ? window.startAppTranslate(text, window.startAppLanguage || "uz") : text);
  const csrfToken = () => document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";

  // Sidebar badges: unanswered support chats and unread contact-form messages.
  const shell = document.querySelector("[data-helper-unread]");
  async function refreshCounts() {
    if (!shell) return;
    try {
      const response = await fetch(shell.dataset.helperUnread, { headers: { Accept: "application/json" }, credentials: "same-origin" });
      if (!response.ok) return;
      const data = await response.json();
      document.querySelectorAll("[data-count]").forEach((badge) => {
        const value = Number(data[badge.dataset.count] || 0);
        badge.textContent = String(value);
        badge.hidden = value === 0;
      });
    } catch {
      // Keep the last known numbers.
    }
  }
  refreshCounts();
  window.setInterval(refreshCounts, 10000);

  // Read-only AI assistant for admins.
  const box = document.querySelector("[data-helper-ai]");
  if (!box) return;
  const form = box.querySelector("[data-ai-form]");
  const input = form.querySelector("input[name=message]");
  const log = box.querySelector("[data-ai-log]");
  const button = form.querySelector("button");

  function addBubble(text, kind) {
    const bubble = document.createElement("div");
    bubble.className = `helper-ai-msg is-${kind}`;
    bubble.textContent = text;
    log.append(bubble);
    log.scrollTop = log.scrollHeight;
    return bubble;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    addBubble(question, "question");
    input.value = "";
    button.disabled = true;
    const pending = addBubble(t("Savolingiz ustida ishlayapman…"), "answer");
    try {
      const response = await fetch(box.dataset.url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({ message: question }),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok) {
        pending.textContent = data.answer;
      } else {
        pending.className = "helper-ai-msg is-error";
        pending.textContent = data.detail || `HTTP ${response.status}`;
      }
    } catch {
      pending.className = "helper-ai-msg is-error";
      pending.textContent = t("AI xizmatiga ulanib bo'lmadi.");
    } finally {
      button.disabled = false;
      input.focus();
    }
  });
})();
