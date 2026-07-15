(function () {
  var STORAGE_KEY = "aiwiki_search_scope";
  var menu = document.getElementById("scope-menu");
  var toggle = document.getElementById("scope-menu-toggle");
  var panel = document.getElementById("scope-menu-panel");
  var label = document.getElementById("scope-menu-label");
  var form = document.getElementById("site-header-search-form");
  var input = document.getElementById("site-header-search-input");
  if (!menu || !toggle || !panel || !form || !input) {
    return;
  }

  var items = panel.querySelectorAll(".scope-menu-nav-item[data-scope]");
  var open = false;
  var currentScope = "wiki";

  function t(key, fallback) {
    return window.Aiwiki && window.Aiwiki.t ? window.Aiwiki.t(key) : fallback;
  }

  function renderIcons(scope) {
    if (window.lucide) window.lucide.createIcons(scope || document);
  }

  function scopeFromPath() {
    var path = window.location.pathname;
    if (path === "/tools" || path.startsWith("/tools/")) {
      return "tools";
    }
    if (path === "/search") {
      var params = new URLSearchParams(window.location.search);
      if (params.get("scope") === "tools") {
        return "tools";
      }
    }
    return "wiki";
  }

  function writeScope(scope) {
    try {
      localStorage.setItem(STORAGE_KEY, scope);
    } catch (_err) {
      /* ignore */
    }
  }

  function scopeLabel(scope) {
    return scope === "tools" ? t("nav.scope_tools", "AITools") : t("nav.scope_wiki", "AIWiki");
  }

  function syncHiddenScope(scope) {
    var hidden = form.querySelector('input[name="scope"]');
    if (scope === "tools") {
      if (!hidden) {
        hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "scope";
        form.appendChild(hidden);
      }
      hidden.value = "tools";
    } else if (hidden) {
      hidden.remove();
    }
  }

  function applyScope(scope) {
    currentScope = scope === "tools" ? "tools" : "wiki";
    if (label) {
      label.textContent = scopeLabel(currentScope);
    }
    items.forEach(function (item) {
      var active = item.getAttribute("data-scope") === currentScope;
      item.setAttribute("aria-checked", active ? "true" : "false");
      item.classList.toggle("scope-menu-nav-item--active", active);
    });
    syncHiddenScope(currentScope);
    if (currentScope === "tools") {
      input.placeholder = t("nav.search_placeholder_tools", "Search AITools");
    } else {
      input.placeholder = t("nav.search_placeholder", "Search AIWiki");
    }
  }

  function navigateForScope(scope) {
    var path = window.location.pathname;
    if (scope === "tools") {
      if (path === "/tools" || path.startsWith("/tools/")) {
        return false;
      }
      window.location.href = "/tools";
      return true;
    }
    if (path === "/" || path === "/recent-changes") {
      return false;
    }
    if (path.startsWith("/tools")) {
      window.location.href = "/";
      return true;
    }
    return false;
  }

  function setOpen(next) {
    open = next;
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.classList.toggle("scope-menu-toggle--open", open);
  }

  toggle.addEventListener("click", function (event) {
    event.stopPropagation();
    setOpen(!open);
  });

  panel.addEventListener("click", function (event) {
    event.stopPropagation();
  });

  items.forEach(function (item) {
    item.addEventListener("click", function (event) {
      event.preventDefault();
      var scope = item.getAttribute("data-scope") === "tools" ? "tools" : "wiki";
      writeScope(scope);
      if (navigateForScope(scope)) {
        return;
      }
      applyScope(scope);
      setOpen(false);
    });
  });

  form.addEventListener("submit", function () {
    writeScope(currentScope);
    syncHiddenScope(currentScope);
  });

  document.addEventListener("click", function (event) {
    if (!open) return;
    if (menu.contains(event.target)) return;
    setOpen(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") setOpen(false);
  });

  currentScope = scopeFromPath();
  writeScope(currentScope);
  applyScope(currentScope);
  renderIcons(menu);
})();
