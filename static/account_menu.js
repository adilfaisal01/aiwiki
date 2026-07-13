(function () {
  var menu = document.getElementById("account-menu");
  var toggle = document.getElementById("account-menu-toggle");
  var panel = document.getElementById("account-menu-panel");
  var body = document.getElementById("account-menu-body");
  if (!menu || !toggle || !panel || !body) return;

  function t(key) {
    return window.Aiwiki && window.Aiwiki.t ? window.Aiwiki.t(key) : key;
  }

  var escapeHtml = (window.Aiwiki && window.Aiwiki.escapeHtml) || function (text) {
    var div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  };

  var state = {
    authenticated: menu.getAttribute("data-authenticated") === "true",
    id: menu.getAttribute("data-user-id") || null,
    avatar_url: menu.getAttribute("data-avatar-url") || null,
  };
  var open = false;

  function renderIcons(scope) {
    if (window.lucide) window.lucide.createIcons(scope || document);
  }

  function accountInitials(id) {
    if (!id) return "?";
    return id.replace(/-/g, "").slice(0, 2).toUpperCase();
  }

  function initialsHue(id) {
    var hash = 0;
    for (var i = 0; i < (id || "").length; i += 1) {
      hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
    }
    return hash % 360;
  }

  function updateToggleAvatar() {
    var face = document.getElementById("account-menu-face");
    if (!face) return;

    toggle.classList.remove("account-menu-toggle--signed-in", "account-menu-toggle--has-avatar");

    if (!state.authenticated) {
      face.innerHTML = '<span class="account-menu-icon" data-lucide="user" data-lucide-size="22"></span>';
      renderIcons(face);
      return;
    }

    toggle.classList.add("account-menu-toggle--signed-in");

    if (state.avatar_url) {
      toggle.classList.add("account-menu-toggle--has-avatar");
      if (!face.querySelector("img.account-menu-avatar")) {
        face.innerHTML =
          '<img class="account-menu-avatar" src="' +
          escapeHtml(state.avatar_url) +
          '" alt="Account avatar" width="30" height="30">';
      }
      var img = face.querySelector("img");
      if (img) {
        img.onerror = function () {
          face.innerHTML =
            '<span class="account-menu-initials" style="background:hsl(' +
            initialsHue(state.id) +
            ' 45% 42%)">' +
            escapeHtml(accountInitials(state.id)) +
            "</span>";
        };
      }
      return;
    }

    if (!face.querySelector(".account-menu-initials")) {
      face.innerHTML =
        '<span class="account-menu-initials" style="background:hsl(' +
        initialsHue(state.id) +
        ' 45% 42%)">' +
        escapeHtml(accountInitials(state.id)) +
        "</span>";
    }
  }

  function guestMenuHtml() {
    return (
      '<div class="account-menu-nav">' +
      '<a class="account-menu-nav-item account-menu-nav-link" href="/account/login">' +
      escapeHtml(t("account.menu.login")) +
      "</a>" +
      "</div>"
    );
  }

  function signedInMenuHtml() {
    return (
      '<div class="account-menu-nav">' +
      '<a class="account-menu-nav-item account-menu-nav-link" href="/account">' +
      escapeHtml(t("account.menu.account")) +
      "</a>" +
      '<div class="account-menu-divider"></div>' +
      '<a class="account-menu-nav-item account-menu-nav-link" href="/account/settings">' +
      escapeHtml(t("account.menu.settings")) +
      "</a>" +
      '<button type="button" class="account-menu-nav-item" id="account-nav-logout">' +
      escapeHtml(t("account.menu.logout")) +
      "</button>" +
      "</div>"
    );
  }

  function renderBody() {
    updateToggleAvatar();
    if (state.authenticated) {
      body.innerHTML = signedInMenuHtml();
      var logoutBtn = document.getElementById("account-nav-logout");
      if (logoutBtn) {
        logoutBtn.addEventListener("click", function (event) {
          event.preventDefault();
          event.stopPropagation();
          logoutAccount();
        });
      }
      return;
    }
    body.innerHTML = guestMenuHtml();
  }

  function applyAccountData(data) {
    state.authenticated = !!data.authenticated;
    state.id = data.id || null;
    state.avatar_url = data.avatar_url || null;
    renderBody();
  }

  function loadAccount() {
    fetch("/api/v1/account")
      .then(function (r) {
        return r.json();
      })
      .then(applyAccountData)
      .catch(function () {
        body.innerHTML = '<p class="account-menu-error">' + escapeHtml(t("account.menu.load_error")) + "</p>";
      });
  }

  function logoutAccount() {
    fetch("/api/v1/account/logout", { method: "POST" })
      .then(function () {
        applyAccountData({ authenticated: false });
        setOpen(false);
      })
      .catch(function () {
        body.innerHTML = '<p class="account-menu-error">' + escapeHtml(t("account.menu.logout_error")) + "</p>";
      });
  }

  function setOpen(next) {
    open = next;
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) renderBody();
  }

  toggle.addEventListener("click", function (event) {
    event.stopPropagation();
    setOpen(!open);
  });

  panel.addEventListener("click", function (event) {
    event.stopPropagation();
  });

  document.addEventListener("click", function (event) {
    if (!open) return;
    if (menu.contains(event.target)) return;
    setOpen(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") setOpen(false);
  });

  var loadingEl = body.querySelector(".account-menu-loading");
  if (loadingEl) loadingEl.textContent = t("account.menu.loading");

  updateToggleAvatar();
  loadAccount();
})();
