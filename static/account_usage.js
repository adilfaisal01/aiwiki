(function () {
  var root = document.getElementById("account-usage-content");
  if (!root) return;

  function t(key, vars) {
    return window.Aiwiki && window.Aiwiki.t ? window.Aiwiki.t(key, vars) : key;
  }

  var loading = document.getElementById("account-usage-loading");
  var alertBox = document.getElementById("account-usage-alert");
  var planName = document.getElementById("account-usage-plan-name");
  var periodEl = document.getElementById("account-usage-period");
  var serverCount = document.getElementById("account-usage-server-count");
  var serverBarWrap = document.getElementById("account-usage-server-bar-wrap");
  var serverBar = document.getElementById("account-usage-server-bar");
  var serverHint = document.getElementById("account-usage-server-hint");
  var agentsCount = document.getElementById("account-usage-agents-count");
  var agentsBarWrap = document.getElementById("account-usage-agents-bar-wrap");
  var agentsBar = document.getElementById("account-usage-agents-bar");
  var agentsHint = document.getElementById("account-usage-agents-hint");
  var paygCost = document.getElementById("account-usage-payg-cost");

  function showAlert(message, kind) {
    if (!alertBox) return;
    alertBox.textContent = message;
    alertBox.className = "ambox ambox-" + (kind || "notice");
    alertBox.hidden = false;
  }

  function formatCount(used, limit, unlimited) {
    if (unlimited) {
      return t("account.settings.usage_count_unlimited", { used: used });
    }
    return t("account.settings.usage_count", { used: used, limit: limit });
  }

  function setBar(barEl, wrapEl, used, limit, unlimited) {
    if (!barEl || !wrapEl) return;
    if (unlimited || !limit) {
      wrapEl.hidden = true;
      return;
    }
    wrapEl.hidden = false;
    var pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
    barEl.style.width = pct + "%";
    barEl.classList.toggle("account-usage-bar-fill--high", pct >= 85);
  }

  function renderUsage(data) {
    if (planName) planName.textContent = data.plan_label || data.plan || "—";
    if (periodEl) {
      periodEl.textContent = t("account.settings.usage_period", {
        start: data.period_start || "—",
        end: data.period_end || "—",
      });
    }

    var server = data.server_invokes || {};
    if (serverCount) {
      serverCount.textContent = formatCount(
        server.used || 0,
        server.limit,
        server.unlimited
      );
    }
    setBar(serverBar, serverBarWrap, server.used || 0, server.limit, server.unlimited);
    if (serverHint) {
      if (server.usage_based) {
        serverHint.textContent = t("account.settings.usage_server_payg");
      } else if (server.unlimited) {
        serverHint.textContent = t("account.settings.usage_server_unlimited");
      } else {
        serverHint.textContent = t("account.settings.usage_server_hint");
      }
    }

    var agents = data.registered_agents || {};
    if (agentsCount) {
      agentsCount.textContent = formatCount(
        agents.used || 0,
        agents.limit,
        agents.unlimited
      );
    }
    setBar(agentsBar, agentsBarWrap, agents.used || 0, agents.limit, agents.unlimited);
    if (agentsHint) {
      agentsHint.textContent = agents.unlimited
        ? t("account.settings.usage_agents_unlimited")
        : t("account.settings.usage_agents_hint");
    }

    if (paygCost) {
      if (data.plan === "payg" && typeof data.estimated_cost_eur === "number") {
        paygCost.textContent = t("account.settings.usage_estimated_cost", {
          amount: data.estimated_cost_eur.toFixed(4),
        });
        paygCost.hidden = false;
      } else {
        paygCost.hidden = true;
      }
    }

    if (loading) loading.hidden = true;
    root.hidden = false;
  }

  fetch("/api/v1/account/usage")
    .then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) throw new Error(data.detail || t("account.settings.usage_load_error"));
        return data;
      });
    })
    .then(renderUsage)
    .catch(function (err) {
      if (loading) loading.hidden = true;
      showAlert(err.message || t("account.settings.usage_load_error"), "error");
    });
})();
