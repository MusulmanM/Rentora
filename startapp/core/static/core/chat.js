(() => {
  "use strict";

  const room = document.querySelector("[data-chat-room]");
  if (!room) return;
  const list = room.querySelector("[data-chat-messages]");
  const form = room.querySelector("[data-chat-form]");
  const syncStatus = room.querySelector("[data-chat-sync-status]");
  const fileInput = form.querySelector('input[type="file"]');
  const recorderButton = form.querySelector("[data-record-audio]");
  const recorderStatus = form.querySelector("[data-record-status]");
  let latestId = Number(list.dataset.lastId) || 0;

  function appendMessage(message) {
    const article = document.createElement("article");
    article.className = `chat-message${message.mine ? " is-mine" : ""}`;
    article.dataset.messageId = String(message.id);
    const sender = document.createElement("strong");
    sender.textContent = message.sender;
    article.append(sender);
    if (message.text) {
      const text = document.createElement("p");
      text.textContent = message.text;
      article.append(text);
    }
    if (message.attachment_url) {
      if (message.attachment_type === "image") {
        const image = document.createElement("img");
        image.src = message.attachment_url;
        image.alt = "Chat rasmi";
        image.loading = "lazy";
        article.append(image);
      } else if (message.attachment_type === "audio") {
        const audio = document.createElement("audio");
        audio.controls = true;
        audio.preload = "metadata";
        audio.src = message.attachment_url;
        article.append(audio);
      }
    }
    const time = document.createElement("time");
    time.textContent = message.created_at;
    article.append(time);
    list.append(article);
    latestId = Math.max(latestId, Number(message.id) || 0);
    list.dataset.lastId = String(latestId);
    list.scrollTop = list.scrollHeight;
  }

  async function refreshMessages() {
    try {
      const response = await fetch(`${room.dataset.messagesUrl}?after=${latestId}`, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) {
        syncStatus.textContent = `Yangi xabarlar yuklanmadi (HTTP ${response.status}).`;
        return;
      }
      const data = await response.json();
      data.messages.forEach(appendMessage);
      syncStatus.textContent = "";
    } catch (error) {
      syncStatus.textContent = "Chatga ulanish uzildi. Xabarlar qayta yuklanmoqda.";
      console.error("Chat message refresh failed.", error);
    }
  }

  list.scrollTop = list.scrollHeight;
  window.setInterval(refreshMessages, 3000);

  let recorder = null;
  let microphone = null;
  let audioChunks = [];
  if (recorderButton && navigator.mediaDevices?.getUserMedia && window.MediaRecorder) {
    recorderButton.addEventListener("click", async () => {
      if (recorder?.state === "recording") {
        recorder.stop();
        recorderButton.textContent = "Ovoz yozish";
        recorderStatus.textContent = "Ovoz tayyorlanmoqda…";
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
          const extension = mimeType.includes("ogg") ? "ogg" : "webm";
          const voiceFile = new File(audioChunks, `voice-message.${extension}`, { type: mimeType });
          const transfer = new DataTransfer();
          transfer.items.add(voiceFile);
          fileInput.files = transfer.files;
          recorderStatus.textContent = "Ovozli xabar yuborishga tayyor.";
          microphone.getTracks().forEach((track) => track.stop());
          microphone = null;
        });
        recorder.start();
        recorderButton.textContent = "Yozishni to'xtatish";
        recorderStatus.textContent = "Ovoz yozilmoqda…";
      } catch {
        recorderStatus.textContent = "Mikrofonga ruxsat berilmadi. Audio fayl tanlashingiz mumkin.";
      }
    });
  } else if (recorderButton) {
    recorderButton.hidden = true;
  }
})();
