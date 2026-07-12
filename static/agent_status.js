(function () {
  var POLL_MS = 10000;
  var MAX_SIDEBAR = 8;
  var listEl = document.getElementById("agent-status-list");
  var footerEl = document.getElementById("agent-status-footer");
  if (!listEl) return;

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function renderAgent(agent) {
    var li = document.createElement("li");
    var statusClass = agent.online ? "online" : "offline";
    var statusLabel = agent.online ? "Online" : "Offline";
    var nameHtml = agent.overview_url
      ? "<a href=\"" + escapeHtml(agent.overview_url) + "\">" + escapeHtml(agent.name) + "</a>"
      : escapeHtml(agent.name);
    li.innerHTML =
      '<span class="agent-indicator ' + statusClass + '" title="' + statusLabel + '"></span> ' +
      nameHtml;
    return li;
  }

  function renderAgents(data) {
    var agents = data.agents || [];
    listEl.innerHTML = "";

    if (!agents.length) {
      listEl.innerHTML = "<li class=\"agent-status-empty\">No registered agents yet.</li>";
      if (footerEl) footerEl.hidden = true;
      return;
    }

    var shown = agents.slice(0, MAX_SIDEBAR);
    shown.forEach(function (agent) {
      listEl.appendChild(renderAgent(agent));
    });

    if (footerEl) {
      footerEl.hidden = agents.length <= MAX_SIDEBAR;
    }
  }

  function refresh() {
    fetch("/api/v1/agents/status")
      .then(function (r) { return r.json(); })
      .then(renderAgents)
      .catch(function () {
        listEl.innerHTML = "<li class=\"agent-status-empty\">Could not load agent status.</li>";
        if (footerEl) footerEl.hidden = true;
      });
  }

  refresh();
  setInterval(refresh, POLL_MS);
})();
