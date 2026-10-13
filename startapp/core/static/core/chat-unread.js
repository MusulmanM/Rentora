(() => {
  "use strict";

  const header = document.querySelector("[data-unread-endpoint]");
  if (!header) return;
  const indicators = document.querySelectorAll("[data-unread-indicator]");
  if (!indicators.length) return;

  async function refreshUnreadState() {
    try {
      const response = await fetch(header.dataset.unreadEndpoint, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) return;
      const { has_unread: hasUnread } = await response.json();
      indicators.forEach((indicator) => {
        indicator.hidden = !hasUnread;
      });
    } catch {
      // Retain the last server-rendered state until the next successful poll.
    }
  }

  window.setInterval(refreshUnreadState, 8000);
})();
