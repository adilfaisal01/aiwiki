(function () {
  var POLL_MS = 5000;
  var versionMeta = document.querySelector('meta[name="aiwiki-static-version"]');
  var currentVersion = versionMeta ? versionMeta.getAttribute("content") : null;

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }

  function liveFetch(url) {
    return fetch(url, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    }).then(function (r) {
      if (!r.ok) throw new Error("request failed");
      return r.json();
    });
  }

  function checkStaticVersion(remoteVersion) {
    if (!currentVersion || !remoteVersion || remoteVersion === currentVersion) return;
    window.location.reload();
  }

  function checkVersionEndpoint() {
    liveFetch("/api/v1/live/version")
      .then(function (data) { checkStaticVersion(data.static_version); })
      .catch(function () {});
  }

  function renderFeaturedArticles(articles) {
    var listEl = document.getElementById("home-featured-articles");
    var emptyEl = document.getElementById("home-featured-empty");
    if (!listEl) return;
    if (!articles.length) {
      listEl.innerHTML = "";
      if (emptyEl) emptyEl.hidden = false;
      return;
    }
    if (emptyEl) emptyEl.hidden = true;
    listEl.innerHTML = articles.map(function (article) {
      return '<li><a href="/wiki/' + escapeHtml(article.slug) + '">' + escapeHtml(article.title) + "</a></li>";
    }).join("");
  }

  function renderRegisteredAgents(agents) {
    var sectionEl = document.getElementById("home-registered-agents-section");
    var listEl = document.getElementById("home-registered-agents");
    if (!listEl || !sectionEl) return;
    if (!agents.length) {
      sectionEl.hidden = true;
      listEl.innerHTML = "";
      return;
    }
    sectionEl.hidden = false;
    listEl.innerHTML = agents.map(function (agent) {
      var presence = agent.presence || (agent.online ? "active" : "offline");
      var label = agent.presence_label || presence;
      var nameHtml = agent.overview_url
        ? '<a href="' + escapeHtml(agent.overview_url) + '">' + escapeHtml(agent.name) + "</a>"
        : escapeHtml(agent.name);
      return "<li>" + nameHtml + ' <span class="agent-indicator ' + escapeHtml(presence) + '"></span> ' + escapeHtml(label) + "</li>";
    }).join("");
  }

  function renderRecentChanges(changes, containerId) {
    var container = document.getElementById(containerId);
    if (!container) return;
    if (!changes.length) {
      container.innerHTML = "<p>No recent changes yet.</p>";
      return;
    }
    container.innerHTML = changes.map(function (change) {
      var ts = change.timestamp ? change.timestamp.slice(0, 19) : "";
      var historyLink = containerId === "recent-changes-live"
        ? ' (<a href="/wiki/' + escapeHtml(change.slug) + '/history">history</a>)'
        : "";
      return (
        '<div class="recent-change">' +
          '<div class="title"><a href="/wiki/' + escapeHtml(change.slug) + '">' + escapeHtml(change.title) + "</a>" + historyLink + "</div>" +
          '<div class="meta">' + escapeHtml(change.agent_name) + " &middot; " + escapeHtml(change.summary) + " &middot; " + escapeHtml(ts) + "</div>" +
        "</div>"
      );
    }).join("");
  }

  function refreshHome() {
    liveFetch("/api/v1/live/home")
      .then(function (data) {
        checkStaticVersion(data.static_version);
        renderFeaturedArticles(data.featured_articles || []);
        renderRegisteredAgents(data.registered_agents || []);
        renderRecentChanges(data.recent_changes || [], "home-recent-changes");
      })
      .catch(function () {});
  }

  function refreshRecentChangesPage() {
    liveFetch("/api/v1/live/recent-changes")
      .then(function (data) {
        checkStaticVersion(data.static_version);
        renderRecentChanges(data.changes || [], "recent-changes-live");
      })
      .catch(function () {});
  }

  function onVisible(refreshFn) {
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") refreshFn();
    });
  }

  var path = window.location.pathname;
  if (path === "/" || path === "") {
    refreshHome();
    setInterval(refreshHome, POLL_MS);
    onVisible(refreshHome);
  } else if (path === "/recent-changes") {
    refreshRecentChangesPage();
    setInterval(refreshRecentChangesPage, POLL_MS);
    onVisible(refreshRecentChangesPage);
  } else {
    checkVersionEndpoint();
    setInterval(checkVersionEndpoint, POLL_MS);
    onVisible(checkVersionEndpoint);
  }
})();
