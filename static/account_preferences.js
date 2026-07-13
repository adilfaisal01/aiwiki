(function () {
  var root = document.getElementById("account-preferences-root");
  if (!root) return;

  var select = document.getElementById("account-locale-select");
  var saveBtn = document.getElementById("account-locale-save");
  var alertBox = document.getElementById("account-locale-alert");

  function t(key, vars) {
    if (window.Aiwiki && window.Aiwiki.t) return window.Aiwiki.t(key, vars);
    return key;
  }

  function showAlert(message, kind) {
    if (!alertBox) return;
    alertBox.textContent = message;
    alertBox.className = "ambox ambox-" + (kind || "notice");
    alertBox.hidden = false;
  }

  if (saveBtn && select) {
    saveBtn.addEventListener("click", function () {
      saveBtn.disabled = true;
      fetch("/api/v1/account/locale", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ locale: select.value }),
      })
        .then(function (r) {
          return r.json().then(function (data) {
            if (!r.ok) throw new Error(data.detail || t("account.settings.language_error"));
            return data;
          });
        })
        .then(function () {
          window.location.reload();
        })
        .catch(function (err) {
          saveBtn.disabled = false;
          showAlert(err.message || t("account.settings.language_error"), "error");
        });
    });
  }
})();
