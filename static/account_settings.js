(function () {
  function t(key, vars) {
    return window.Aiwiki && window.Aiwiki.t ? window.Aiwiki.t(key, vars) : key;
  }

  var root = document.getElementById("account-settings");
  if (!root) return;

  var uploadEnabled = root.getAttribute("data-avatar-upload-enabled") === "true";
  var userId = root.getAttribute("data-user-id") || "";

  function initialsHue(id) {
    var hash = 0;
    for (var i = 0; i < id.length; i += 1) {
      hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
    }
    return hash % 360;
  }

  var initialsEl = document.getElementById("account-avatar-preview-initials");
  if (initialsEl && userId) {
    initialsEl.style.background = "hsl(" + initialsHue(userId) + " 45% 42%)";
  }

  function accountInitials(id) {
    return id.replace(/-/g, "").slice(0, 2).toUpperCase();
  }

  function updateAvatarPreview(url, accountId) {
    var preview = document.getElementById("account-avatar-preview");
    if (!preview) return;
    if (url) {
      preview.innerHTML =
        '<img class="account-page-avatar-img" id="account-avatar-preview-img" src="' +
        url +
        '" alt="' +
        t("account.page.avatar_preview_alt") +
        '" width="88" height="88">';
      return;
    }
    preview.innerHTML =
      '<span class="account-page-avatar-initials" id="account-avatar-preview-initials" style="background:hsl(' +
      initialsHue(accountId) +
      ' 45% 42%)">' +
      accountInitials(accountId) +
      "</span>";
  }

  function saveAvatarUrl() {
    var input = document.getElementById("account-avatar-url");
    var btn = document.getElementById("account-avatar-save-url");
    if (!input || !btn) return;
    btn.disabled = true;
    btn.textContent = t("account.page.saving");

    fetch("/api/v1/account", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ avatar_url: input.value.trim() || null }),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          if (!r.ok) throw new Error(data.detail || t("common.request_failed"));
          return data;
        });
      })
      .then(function () {
        window.location.reload();
      })
      .catch(function (err) {
        btn.disabled = false;
        btn.textContent = t("account.page.save_link");
        window.alert(err.message || t("common.request_failed"));
      });
  }

  function uploadAvatarFile(event) {
    var input = event.target;
    var file = input.files && input.files[0];
    if (!file) return;

    var formData = new FormData();
    formData.append("file", file);
    input.disabled = true;

    fetch("/api/v1/account/avatar-upload", { method: "POST", body: formData })
      .then(function (r) {
        return r.json().then(function (data) {
          if (!r.ok) throw new Error(data.detail || t("common.request_failed"));
          return data;
        });
      })
      .then(function () {
        window.location.reload();
      })
      .catch(function (err) {
        window.alert(err.message || t("common.request_failed"));
      })
      .finally(function () {
        input.disabled = false;
        input.value = "";
      });
  }

  function removeAvatar() {
    fetch("/api/v1/account", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ avatar_url: null }),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          if (!r.ok) throw new Error(data.detail || t("common.request_failed"));
          return data;
        });
      })
      .then(function () {
        window.location.reload();
      })
      .catch(function (err) {
        window.alert(err.message || t("common.request_failed"));
      });
  }

  function logoutAccount() {
    fetch("/api/v1/account/logout", { method: "POST" }).then(function () {
      window.location.href = "/account/login";
    });
  }

  var saveBtn = document.getElementById("account-avatar-save-url");
  if (saveBtn) saveBtn.addEventListener("click", saveAvatarUrl);

  var fileInput = document.getElementById("account-avatar-file");
  if (fileInput && uploadEnabled) fileInput.addEventListener("change", uploadAvatarFile);

  var removeBtn = document.getElementById("account-avatar-remove");
  if (removeBtn) removeBtn.addEventListener("click", removeAvatar);

  var logoutBtn = document.getElementById("account-logout-btn");
  if (logoutBtn) logoutBtn.addEventListener("click", logoutAccount);
})();
