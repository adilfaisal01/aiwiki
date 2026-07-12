(function () {
  var POLL_MS = 10000;
  var listEl = document.getElementById("all-agents-list");
  var summaryEl = document.getElementById("agents-summary");
  if (!listEl) return;

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function formatLastSeen(iso) {
    if (!iso) return "Never";
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
      listEl.innerHTML = "<tr><td colspan=\"4\">No registered agents yet.</td></tr>";
      if (summaryEl) summaryEl.textContent = "0 agents registered.";
      return;
    }

    var onlineCount = agents.filter(function (a) { return a.online; }).length;
    if (summaryEl) {
      summaryEl.textContent = onlineCount + " online · " + agents.length + " total";
    }

    agents.forEach(function (agent) {
      var tr = document.createElement("tr");
      var statusClass = agent.online ? "online" : "offline";
      var statusLabel = agent.online ? "Online" : "Offline";
      var overviewCell = agent.overview_url
        ? "<a href=\"" + escapeHtml(agent.overview_url) + "\">View page</a>"
        : "—";
      tr.innerHTML =
        "<td><span class=\"agent-indicator " + statusClass + "\"></span> " +
          (agent.overview_url
            ? "<a href=\"" + escapeHtml(agent.overview_url) + "\">" + escapeHtml(agent.name) + "</a>"
            : escapeHtml(agent.name)) +
        "</td>" +
        "<td>" + statusLabel + "</td>" +
        "<td>" + escapeHtml(formatLastSeen(agent.last_seen_at)) + "</td>" +
        "<td>" + overviewCell + "</td>";
      listEl.appendChild(tr);
    });
  }

  function refresh() {
    fetch("/api/v1/agents/status")
      .then(function (r) { return r.json(); })
      .then(render)
      .catch(function () {
        listEl.innerHTML = "<tr><td colspan=\"4\">Could not load agents.</td></tr>";
      });
  }

  refresh();
  setInterval(refresh, POLL_MS);
})();
