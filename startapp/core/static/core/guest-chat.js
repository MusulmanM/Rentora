(() => {
  'use strict';

  // Admin chat for visitors without an account: send without reloading and poll for replies.
  const log = document.querySelector('[data-guest-chat]');
  const form = document.querySelector('[data-guest-form]');
  if (!log || !form) return;
  const endpoint = log.dataset.endpoint;
  const errorBox = document.querySelector('[data-guest-error]');
  const input = form.elements.text;
  const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  const guestName = (log.querySelector('.guest-msg.mine b') || {}).textContent || '';

  const lastId = () => {
    const items = log.querySelectorAll('[data-id]');
    return items.length ? Number(items[items.length - 1].dataset.id) : 0;
  };
  const scrollDown = () => { log.scrollTop = log.scrollHeight; };
  const showError = (text) => {
    if (!errorBox) return;
    errorBox.textContent = text || '';
    errorBox.hidden = !text;
  };

  const render = (message) => {
    if (log.querySelector(`[data-id="${message.id}"]`)) return;
    const item = document.createElement('div');
    item.className = `guest-msg${message.mine ? ' mine' : ''}`;
    item.dataset.id = message.id;
    const who = document.createElement('b');
    who.dataset.noTranslate = 'true';
    who.textContent = message.mine ? guestName : message.sender;
    const text = document.createElement('p');
    text.dataset.noTranslate = 'true';
    text.textContent = message.text || '[fayl]';
    const when = document.createElement('small');
    when.textContent = message.created_at;
    item.append(who, text, when);
    log.append(item);
  };

  let polling = false;
  const poll = async () => {
    if (polling || document.hidden) return;
    polling = true;
    try {
      const response = await fetch(`${endpoint}?after=${lastId()}`, { headers: { Accept: 'application/json' } });
      if (response.ok) {
        const data = await response.json();
        if (data.messages && data.messages.length) {
          data.messages.forEach(render);
          scrollDown();
        }
      }
    } catch (error) {
      // Offline for a moment: the next poll will catch up.
    } finally {
      polling = false;
    }
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    const button = form.querySelector('button[type=submit]');
    button.disabled = true;
    showError('');
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { Accept: 'application/json', 'X-CSRFToken': csrf },
        body: new URLSearchParams({ text }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Xabar yuborilmadi.");
      render(data.message);
      input.value = '';
      scrollDown();
    } catch (error) {
      showError(error.message);
    } finally {
      button.disabled = false;
      input.focus();
    }
  });

  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  scrollDown();
  window.setInterval(poll, 4000);
  document.addEventListener('visibilitychange', poll);
})();
