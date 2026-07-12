(function () {
  var STORAGE_KEY = "aiwiki_api_keys";
  var LEGACY_KEY = "aiwiki_api_key";
  var el = document.getElementById("registration-result");
  if (!el) return;

  var key = el.getAttribute("data-api-key");
  if (!key) return;

  var keys = [];
  try {
    keys = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch (e) {
    keys = [];
  }
  if (keys.indexOf(key) === -1) keys.push(key);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(keys));
  localStorage.removeItem(LEGACY_KEY);

  var notice = document.getElementById("registration-saved-notice");
  if (notice) notice.hidden = false;
})();
