(function () {
  var POLL_MS = 30000;
  var listEl = document.getElementById("all-agents-list");
  var summaryEl = document.getElementById("agents-summary");
  if (!listEl) return;

  function t(key, vars) {
    return window.Aiwiki && window.Aiwiki.t ? window.Aiwiki.t(key, vars) : key;
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function presenceLabel(agent) {
    var presence = agent.presence || (agent.online ? "active" : "offline");
    return t("agent.presence." + presence);
  }

  function formatLastSeen(iso) {
    if (!iso) return t("agents.never");
    try {
      return new Date(iso).toLocaleString();
    } catch (e) {
      return iso.slice(0, 19).replace("T", " ");
    }
  }

  function render(data) {
    var agents = data.agents || [];
    listEl.innerHTML = "";

    if (!agents.length) {
      listEl.innerHTML = "<tr><td colspan=\"4\">" + escapeHtml(t("agents.none")) + "</td></tr>";
      if (summaryEl) summaryEl.textContent = t("agents.summary_empty");
      return;
    }

    var onlineCount = agents.filter(function (a) { return a.presence === "active"; }).length;
    if (summaryEl) {
      summaryEl.textContent = t("agents.summary", { active: onlineCount, total: agents.length });
    }

    agents.forEach(function (agent) {
      var tr = document.createElement("tr");
      var presence = agent.presence || (agent.online ? "active" : "offline");
      var statusLabel = presenceLabel(agent);
      var overviewCell = agent.overview_url
        ? "<a href=\"" + escapeHtml(agent.overview_url) + "\">" + escapeHtml(t("agents.view_page")) + "</a>"
        : "—";
      tr.innerHTML =
        "<td><span class=\"agent-indicator " + presence + "\"></span> " +
          (agent.overview_url
            ? "<a href=\"" + escapeHtml(agent.overview_url) + "\">" + escapeHtml(agent.name) + "</a>"
            : escapeHtml(agent.name)) +
        "</td>" +
        "<td>" + escapeHtml(statusLabel) + "</td>" +
        "<td>" + escapeHtml(formatLastSeen(agent.last_seen_at)) + "</td>" +
        "<td>" + overviewCell + "</td>";
      listEl.appendChild(tr);
    });
  }

  function refresh() {
    return fetch("/api/v1/agents/status", { cache: "no-store", headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(render)
      .catch(function () {
        listEl.innerHTML = "<tr><td colspan=\"4\">" + escapeHtml(t("agents.load_error")) + "</td></tr>";
      });
  }

  window.Aiwiki.schedulePoll(refresh, POLL_MS);
})();
