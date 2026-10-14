(() => {
  "use strict";

  const room = document.querySelector("[data-chat-room]");
  if (!room) return;
  const list = room.querySelector("[data-chat-messages]");
  const form = room.querySelector("[data-chat-form]");
  const syncStatus = room.querySelector("[data-chat-sync-status]");
  const t = (text) => (window.startAppTranslate ? window.startAppTranslate(text, window.startAppLanguage || "uz") : text);
  let latestId = Number(list.dataset.lastId) || 0;
  let lastDate = list.querySelector(".tg-date:last-of-type span")?.textContent || "";
  const showSenders = room.hasAttribute("data-show-senders");

  function scrollToBottom() {
    list.scrollTop = list.scrollHeight;
  }

  function markRead(otherLastReadId) {
    list.querySelectorAll(".tg-msg.is-mine .tg-ticks:not(.is-read)").forEach((ticks) => {
      const id = Number(ticks.closest(".tg-msg").dataset.messageId);
      if (id && id <= otherLastReadId) {
        ticks.classList.add("is-read");
        ticks.textContent = "✓✓";
        ticks.setAttribute("aria-label", t("O'qildi"));
      }
    });
  }

  function appendMessage(message) {
    if (list.querySelector(`[data-message-id="${message.id}"]`)) return;
    list.querySelector("[data-chat-empty]")?.remove();
    if (message.date && message.date !== lastDate) {
      const separator = document.createElement("div");
      separator.className = "tg-date";
      const label = document.createElement("span");
      label.textContent = message.date;
      separator.append(label);
      list.append(separator);
      lastDate = message.date;
    }
    const article = document.createElement("article");
    article.className = `tg-msg${message.mine ? " is-mine" : ""}${message.is_ai ? " is-ai" : ""}`;
    article.dataset.noTranslate = "true";
    article.dataset.messageId = String(message.id);
    if (showSenders || !message.mine) {
      const sender = document.createElement("span");
      sender.className = "tg-sender";
      sender.textContent = message.sender;
      article.append(sender);
    }
    if (message.attachment_url) {
      let media;
      if (message.attachment_type === "image") {
        media = document.createElement("a");
        media.className = "tg-media";
        media.href = message.attachment_url;
        media.target = "_blank";
        media.rel = "noopener";
        const image = document.createElement("img");
        image.src = message.attachment_url;
        image.alt = t("Chat rasmi");
        image.loading = "lazy";
        image.addEventListener("load", scrollToBottom, { once: true });
        media.append(image);
      } else {
        media = document.createElement(message.attachment_type === "video" ? "video" : "audio");
        if (message.attachment_type === "video") media.className = "tg-media";
        media.controls = true;
        media.preload = "metadata";
        media.src = message.attachment_url;
      }
      article.append(media);
    }
    if (message.text) {
      const text = document.createElement("p");
      text.className = "tg-text";
      text.textContent = message.text;
      article.append(text);
    }
    const meta = document.createElement("span");
    meta.className = "tg-meta";
    const time = document.createElement("time");
    time.textContent = message.time || message.created_at;
    meta.append(time);
    if (message.mine) {
      const ticks = document.createElement("span");
      ticks.className = `tg-ticks${message.read ? " is-read" : ""}`;
      ticks.textContent = message.read ? "✓✓" : "✓";
      ticks.setAttribute("aria-label", t(message.read ? "O'qildi" : "Yuborildi"));
      meta.append(ticks);
    }
    article.append(meta);
    list.append(article);
    latestId = Math.max(latestId, Number(message.id) || 0);
    list.dataset.lastId = String(latestId);
    scrollToBottom();
  }

  async function refreshMessages() {
    try {
      const response = await fetch(`${room.dataset.messagesUrl}?after=${latestId}`, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) {
        syncStatus.textContent = `${t("Yangi xabarlar yuklanmadi")} (HTTP ${response.status}).`;
        return;
      }
      const data = await response.json();
      data.messages.forEach(appendMessage);
      markRead(data.other_last_read_id || 0);
      syncStatus.textContent = "";
    } catch (error) {
      syncStatus.textContent = t("Chatga ulanish uzildi. Xabarlar qayta yuklanmoqda.");
      console.error("Chat message refresh failed.", error);
    }
  }

  scrollToBottom();
  window.setInterval(refreshMessages, 3000);
  if (!form) return;

  const textArea = form.querySelector("textarea");
  const fileInput = form.querySelector('input[type="file"]');
  const kindInput = form.querySelector("[data-attachment-kind]");
  const preview = form.querySelector("[data-attachment-preview]");
  const previewName = form.querySelector("[data-attachment-name]");
  const removeButton = form.querySelector("[data-attachment-remove]");
  const progress = form.querySelector("[data-upload-progress]");
  const progressBar = progress?.querySelector("span");
  const status = form.querySelector("[data-record-status]");
  const recorderButton = form.querySelector("[data-record-audio]");
  const sendButton = form.querySelector('button[type="submit"]');
  const maxBytes = Number(form.dataset.maxBytes) || 250 * 1024 * 1024;
  let sending = false;

  const formatSize = (bytes) => (bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

  function showAttachment(label) {
    const file = fileInput.files[0];
    if (!file) {
      preview.hidden = true;
      return;
    }
    previewName.textContent = `${label || file.name} · ${formatSize(file.size)}`;
    preview.hidden = false;
  }

  function clearAttachment() {
    fileInput.value = "";
    kindInput.value = "";
    preview.hidden = true;
  }

  function autoGrow() {
    textArea.style.height = "auto";
    textArea.style.height = `${Math.min(textArea.scrollHeight, 160)}px`;
  }

  fileInput.addEventListener("change", () => {
    kindInput.value = "";
    const file = fileInput.files[0];
    if (file && file.size > maxBytes) {
      status.textContent = `${t("Fayl juda katta")} (${formatSize(file.size)}). ${t("Eng ko'pi")}: ${formatSize(maxBytes)}.`;
      clearAttachment();
      return;
    }
    status.textContent = "";
    showAttachment();
  });
  removeButton.addEventListener("click", clearAttachment);
  textArea.addEventListener("input", autoGrow);
  textArea.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (sending) return;
    if (!textArea.value.trim() && !fileInput.files.length) {
      textArea.focus();
      return;
    }
    sending = true;
    sendButton.disabled = true;
    const request = new XMLHttpRequest();
    request.open("POST", form.action);
    request.setRequestHeader("Accept", "application/json");
    request.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    if (fileInput.files.length) {
      progress.hidden = false;
      progressBar.style.width = "0%";
      request.upload.addEventListener("progress", (progressEvent) => {
        if (progressEvent.lengthComputable) {
          progressBar.style.width = `${Math.round((progressEvent.loaded / progressEvent.total) * 100)}%`;
        }
      });
    }
    request.addEventListener("load", () => {
      sending = false;
      sendButton.disabled = false;
      progress.hidden = true;
      let data = {};
      try {
        data = JSON.parse(request.responseText || "{}");
      } catch {
        data = {};
      }
      if (request.status === 201 && data.message) {
        appendMessage(data.message);
        textArea.value = "";
        autoGrow();
        clearAttachment();
        status.textContent = "";
      } else {
        status.textContent = data.detail || `${t("Xabar yuborilmadi")} (HTTP ${request.status}).`;
      }
    });
    request.addEventListener("error", () => {
      sending = false;
      sendButton.disabled = false;
      progress.hidden = true;
      status.textContent = t("Xabar yuborilmadi. Internet aloqasini tekshiring.");
    });
    request.send(new FormData(form));
  });

  let recorder = null;
  let microphone = null;
  let audioChunks = [];
  if (recorderButton && navigator.mediaDevices?.getUserMedia && window.MediaRecorder) {
    recorderButton.addEventListener("click", async () => {
      if (recorder?.state === "recording") {
        recorder.stop();
        recorderButton.classList.remove("is-recording");
        status.textContent = t("Ovoz tayyorlanmoqda…");
        return;
      }
      try {
        microphone = await navigator.mediaDevices.getUserMedia({ audio: true });
        recorder = new MediaRecorder(microphone);
        audioChunks = [];
        recorder.addEventListener("dataavailable", (event) => {
          if (event.data.size) audioChunks.push(event.data);
        });
        recorder.addEventListener("stop", () => {
          const mimeType = recorder.mimeType || "audio/webm";
          const extension = mimeType.includes("ogg") ? "ogg" : mimeType.includes("mp4") ? "m4a" : "webm";
          const voiceFile = new File(audioChunks, `voice-message.${extension}`, { type: mimeType });
          const transfer = new DataTransfer();
          transfer.items.add(voiceFile);
          fileInput.files = transfer.files;
          kindInput.value = "audio";
          showAttachment(`🎤 ${t("Ovozli xabar")}`);
          status.textContent = t("Ovozli xabar yuborishga tayyor.");
          microphone.getTracks().forEach((track) => track.stop());
          microphone = null;
        });
        recorder.start();
        recorderButton.classList.add("is-recording");
        status.textContent = t("Ovoz yozilmoqda…");
      } catch {
        status.textContent = t("Mikrofonga ruxsat berilmadi. Audio fayl tanlashingiz mumkin.");
      }
    });
  } else if (recorderButton) {
    recorderButton.hidden = true;
  }
})();
