(function () {
  var STORAGE_KEY = "aiwiki-pricing-billing";
  var root = document.getElementById("pricing-page");
  var toggle = document.getElementById("pricing-billing-toggle");
  if (!root || !toggle) return;

  var options = toggle.querySelectorAll(".pricing-billing-option");

  function setBilling(mode) {
    var isAnnual = mode === "annual";
    toggle.setAttribute("data-billing", mode);

    options.forEach(function (btn) {
      var active = btn.getAttribute("data-billing") === mode;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-checked", active ? "true" : "false");
    });

    root.querySelectorAll("[data-monthly][data-annual]").forEach(function (el) {
      el.textContent = isAnnual ? el.getAttribute("data-annual") : el.getAttribute("data-monthly");
    });

    root.querySelectorAll(".pricing-price-equiv").forEach(function (el) {
      el.hidden = !isAnnual;
    });

    try {
      sessionStorage.setItem(STORAGE_KEY, mode);
    } catch (_err) {
      /* ignore */
    }
  }

  options.forEach(function (btn) {
    btn.addEventListener("click", function () {
      setBilling(btn.getAttribute("data-billing") || "monthly");
    });
  });

  var saved = "monthly";
  try {
    saved = sessionStorage.getItem(STORAGE_KEY) || "monthly";
  } catch (_err) {
    saved = "monthly";
  }
  if (saved === "annual") {
    setBilling("annual");
  }
})();
