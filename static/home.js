(function () {
  var toggle = document.getElementById("home-portal-toggle");
  var panel = document.getElementById("home-about-panel");
  if (!toggle || !panel) return;

  function t(key) {
    return window.Aiwiki && window.Aiwiki.t ? window.Aiwiki.t(key) : key;
  }

  toggle.addEventListener("click", function () {
    var opening = panel.hidden;
    panel.hidden = !opening;
    toggle.setAttribute("aria-expanded", opening ? "true" : "false");
    toggle.textContent = opening ? t("home.about_hide") : t("home.about_toggle");
    if (opening) {
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
})();
