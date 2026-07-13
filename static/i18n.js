(function (global) {
  var DEFAULT_CONFIG = {
    locale: "en",
    defaultLocale: "en",
    supportedLocales: ["en", "de", "es", "fr", "pt", "ja", "zh", "hi"],
    messages: {},
  };

  function loadConfig() {
    var meta = document.querySelector('meta[name="aiwiki-i18n-config"]');
    if (!meta) return DEFAULT_CONFIG;
    try {
      return Object.assign({}, DEFAULT_CONFIG, JSON.parse(meta.getAttribute("content") || "{}"));
    } catch (err) {
      return DEFAULT_CONFIG;
    }
  }

  var config = loadConfig();

  function translate(key, vars) {
    var text = config.messages[key] || key;
    if (vars) {
      Object.keys(vars).forEach(function (name) {
        text = text.replace("{" + name + "}", String(vars[name]));
      });
    }
    return text;
  }

  global.Aiwiki = global.Aiwiki || {};
  global.Aiwiki.i18nConfig = config;
  global.Aiwiki.t = translate;
})(window);
