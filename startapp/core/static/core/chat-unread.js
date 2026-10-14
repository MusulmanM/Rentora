(() => {
  "use strict";

  const header = document.querySelector("[data-unread-endpoint]");
  if (!header) return;
  const indicators = document.querySelectorAll("[data-unread-indicator]");
  const inbox = document.querySelector("[data-inbox]");
  if (!indicators.length && !inbox) return;
  let lastCount = Number(inbox?.dataset.unreadTotal || 0);

  async function refreshUnreadState() {
    try {
      const response = await fetch(header.dataset.unreadEndpoint, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) return;
      const { has_unread: hasUnread, count = 0 } = await response.json();
      indicators.forEach((indicator) => {
        indicator.hidden = !hasUnread;
      });
      // On the chat list, refresh the per-chat red badges when a new message arrives.
      if (inbox && count > lastCount) window.location.reload();
      lastCount = count;
    } catch {
      // Retain the last server-rendered state until the next successful poll.
    }
  }

  window.setInterval(refreshUnreadState, inbox ? 5000 : 8000);
})();
