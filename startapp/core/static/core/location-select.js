(() => {
  document.querySelectorAll("[data-location-region]").forEach((regionSelect) => {
    const form = regionSelect.closest("form");
    const districtSelect = form?.querySelector("[data-location-district]");
    if (!districtSelect) return;

    const districtOptions = Array.from(districtSelect.options).slice(1);
    const allOption = districtSelect.options[0];
    const filterDistricts = (resetSelection) => {
      const regionId = regionSelect.value;
      districtOptions.forEach((option) => {
        option.hidden = !regionId || option.dataset.region !== regionId;
      });
      allOption.textContent = regionId ? "Barcha shaharlar va tumanlar" : "Avval viloyatni tanlang";
      districtSelect.disabled = !regionId;
      if (resetSelection || (districtSelect.value && districtSelect.selectedOptions[0]?.hidden)) {
        districtSelect.value = "";
      }
    };

    filterDistricts(false);
    regionSelect.addEventListener("change", () => filterDistricts(true));
  });
})();
