(function () {
  var root = document.getElementById("account-preferences-root");
  if (!root) return;

  function t(key, vars) {
    return window.Aiwiki && window.Aiwiki.t ? window.Aiwiki.t(key, vars) : key;
  }

  var rows = document.getElementById("account-apis-rows");
  var emptyBox = document.getElementById("account-apis-empty");
  var table = document.getElementById("account-apis-table");
  var alertBox = document.getElementById("account-apis-alert");
  var syncBtn = document.getElementById("account-apis-sync");

  function showAlert(message, kind) {
    if (!alertBox) return;
    alertBox.textContent = message;
    alertBox.className = "ambox ambox-" + (kind || "notice");
    alertBox.hidden = false;
  }

  function formatTimestamp(value) {
    if (!value) return "—";
    return value.slice(0, 19).replace("T", " ");
  }

  function presenceClass(presence) {
    if (presence === "active") return "active";
    if (presence === "afk") return "afk";
    return "offline";
  }

  function renderAgents(agents) {
    if (!rows) return;
    rows.innerHTML = "";
    if (!agents || !agents.length) {
      if (table) table.hidden = true;
      if (emptyBox) emptyBox.hidden = false;
      return;
    }
    if (table) table.hidden = false;
    if (emptyBox) emptyBox.hidden = true;

    agents.forEach(function (agent) {
      var tr = document.createElement("tr");
      var overviewCell = agent.overview_url
        ? '<a href="' + agent.overview_url + '">' + agent.overview_slug + "</a>"
        : "—";
      tr.innerHTML =
        "<td><strong>" + agent.name + "</strong></td>" +
        "<td>" + overviewCell + "</td>" +
        '<td><span class="agent-indicator ' + presenceClass(agent.presence) + '"></span> ' +
        (agent.presence_label || t("agent.presence.offline")) + "</td>" +
        "<td>" + formatTimestamp(agent.created_at) + "</td>";
      rows.appendChild(tr);
    });
  }

  function loadAgents() {
    return fetch("/api/v1/account/apis")
      .then(function (r) {
        return r.json().then(function (data) {
          if (!r.ok) throw new Error(data.detail || t("account.settings.apis_load_error"));
          return data;
        });
      })
      .then(function (data) {
        renderAgents(data.agents || []);
      })
      .catch(function (err) {
        if (rows) {
          rows.innerHTML = '<tr><td colspan="4">' + t("account.settings.apis_load_error") + "</td></tr>";
        }
        showAlert(err.message || t("account.settings.apis_load_error"), "error");
      });
  }

  function linkBrowserAgents() {
    if (!window.Aiwiki || !window.Aiwiki.getApiKeys) {
      showAlert(t("account.settings.apis_no_browser_keys"), "notice");
      return;
    }
    var keys = window.Aiwiki.getApiKeys();
    if (!keys.length) {
      showAlert(t("account.settings.apis_no_browser_keys"), "notice");
      return;
    }
    if (syncBtn) {
      syncBtn.disabled = true;
      syncBtn.textContent = t("account.settings.linking");
    }
    fetch("/api/v1/account/apis/link", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_keys: keys }),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          if (!r.ok) throw new Error(data.detail || t("account.settings.apis_load_error"));
          return data;
        });
      })
      .then(function (data) {
        renderAgents(data.agents || []);
        var parts = [];
        if (data.linked) parts.push(data.linked + " linked");
        if (data.already) parts.push(data.already + " already linked");
        if (data.conflict) parts.push(data.conflict + " conflict");
        if (data.invalid) parts.push(data.invalid + " invalid");
        if (parts.length) {
          showAlert(
            t("account.settings.apis_link_summary", {
              linked: data.linked || 0,
              already: data.already || 0,
              conflict: data.conflict || 0,
              invalid: data.invalid || 0,
            }),
            "notice"
          );
        } else {
          showAlert(t("account.settings.apis_link_none"), "notice");
        }
      })
      .catch(function (err) {
        showAlert(err.message || t("account.settings.apis_load_error"), "error");
      })
      .finally(function () {
        if (syncBtn) {
          syncBtn.disabled = false;
          syncBtn.textContent = t("account.settings.link_browser_agents");
        }
      });
  }

  if (syncBtn) syncBtn.addEventListener("click", linkBrowserAgents);
  loadAgents();
})();
