(() => {
  const dialog = document.querySelector("[data-gallery-dialog]");
  const triggers = Array.from(document.querySelectorAll("[data-gallery-trigger]"));
  if (!dialog || !triggers.length) return;

  const image = dialog.querySelector("[data-gallery-full]");
  const count = dialog.querySelector("[data-gallery-count]");
  const images = Array.from(new Map(
    triggers.map((trigger) => [
      trigger.dataset.imageUrl,
      { src: trigger.dataset.imageUrl, alt: trigger.getAttribute("aria-label") || "" },
    ]),
  ).values());
  let activeIndex = 0;

  const showImage = (index) => {
    activeIndex = (index + images.length) % images.length;
    image.src = images[activeIndex].src;
    image.alt = images[activeIndex].alt;
    count.textContent = `${activeIndex + 1} / ${images.length}`;
  };

  triggers.forEach((trigger) => {
    trigger.addEventListener("click", () => {
      showImage(images.findIndex((entry) => entry.src === trigger.dataset.imageUrl));
      dialog.showModal();
    });
  });
  dialog.querySelector("[data-gallery-close]").addEventListener("click", () => dialog.close());
  dialog.querySelector("[data-gallery-prev]").addEventListener("click", () => showImage(activeIndex - 1));
  dialog.querySelector("[data-gallery-next]").addEventListener("click", () => showImage(activeIndex + 1));
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft") showImage(activeIndex - 1);
    if (event.key === "ArrowRight") showImage(activeIndex + 1);
  });
})();
