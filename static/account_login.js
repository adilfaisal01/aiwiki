(function () {
  function t(key, vars) {
    return window.Aiwiki && window.Aiwiki.t ? window.Aiwiki.t(key, vars) : key;
  }

  var errorBox = document.getElementById("account-auth-error");
  var errorText = document.getElementById("account-auth-error-text");
  var loginTab = document.getElementById("account-tab-login");
  var registerTab = document.getElementById("account-tab-register");
  var loginPanel = document.getElementById("account-panel-login");
  var registerPanel = document.getElementById("account-panel-register");
  var loginForm = document.getElementById("account-panel-login");
  var registerForm = document.getElementById("account-panel-register");

  function showError(message) {
    if (!errorBox || !errorText) return;
    errorText.textContent = message;
    errorBox.hidden = false;
  }

  function hideError() {
    if (errorBox) errorBox.hidden = true;
  }

  function setMode(mode) {
    var isLogin = mode === "login";
    if (loginTab) {
      loginTab.classList.toggle("active", isLogin);
      loginTab.setAttribute("aria-selected", isLogin ? "true" : "false");
    }
    if (registerTab) {
      registerTab.classList.toggle("active", !isLogin);
      registerTab.setAttribute("aria-selected", !isLogin ? "true" : "false");
    }
    if (loginPanel) loginPanel.hidden = !isLogin;
    if (registerPanel) registerPanel.hidden = isLogin;
    hideError();
  }

  function setButtonLabel(button, label) {
    if (!button) return;
    if (button.tagName === "INPUT") button.value = label;
    else button.textContent = label;
  }

  function getButtonLabel(button) {
    if (!button) return "";
    return button.tagName === "INPUT" ? button.value : button.textContent;
  }

  function errorMessage(data, fallback) {
    if (!data || !data.detail) return fallback;
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail) && data.detail[0] && data.detail[0].msg) {
      return data.detail[0].msg;
    }
    return fallback;
  }

  function submitAuth(url, payload, button, loadingText) {
    button.disabled = true;
    var originalText = getButtonLabel(button);
    setButtonLabel(button, loadingText);
    hideError();

    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          if (!r.ok) throw new Error(errorMessage(data, t("account.login.request_failed")));
          return data;
        });
      })
      .then(function () {
        window.location.href = "/account";
      })
      .catch(function (err) {
        button.disabled = false;
        setButtonLabel(button, originalText);
        showError(err.message || t("account.login.generic_error"));
      });
  }

  if (loginTab) loginTab.addEventListener("click", function () { setMode("login"); });
  if (registerTab) registerTab.addEventListener("click", function () { setMode("register"); });

  if (loginForm) {
    loginForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var email = document.getElementById("login-email").value.trim();
      var password = document.getElementById("login-password").value;
      var btn = document.getElementById("account-login-btn");
      submitAuth("/api/v1/account/login", { email: email, password: password }, btn, t("account.login.signing_in"));
    });
  }

  if (registerForm) {
    registerForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var email = document.getElementById("register-email").value.trim();
      var password = document.getElementById("register-password").value;
      var confirm = document.getElementById("register-password-confirm").value;
      var btn = document.getElementById("account-register-btn");

      if (password !== confirm) {
        showError(t("account.login.password_mismatch"));
        setMode("register");
        return;
      }

      submitAuth("/api/v1/account", { email: email, password: password }, btn, t("account.login.creating"));
    });
  }

  fetch("/api/v1/account")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.authenticated && data.email) {
        window.location.href = "/account";
      }
    })
    .catch(function () {});

  var params = new URLSearchParams(window.location.search);
  if (params.get("mode") === "register") {
    setMode("register");
  }
})();
