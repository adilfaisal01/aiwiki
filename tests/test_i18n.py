from web.i18n import normalize_locale, t


def test_normalize_locale_defaults_to_english():
    assert normalize_locale(None) == "en"
    assert normalize_locale("fr") == "fr"
    assert normalize_locale("de-DE") == "de"
    assert normalize_locale("zh-CN") == "zh"
    assert normalize_locale("pt-BR") == "pt"
    assert normalize_locale("xx") == "en"


def test_translate_spanish():
    assert t("es", "nav.search") == "Buscar"
    assert t("es", "home.welcome") == "Bienvenido a AIWiki"


def test_translate_french():
    assert t("fr", "nav.search") == "Rechercher"


def test_translate_portuguese():
    assert t("pt", "nav.search") == "Pesquisar"


def test_translate_japanese():
    assert t("ja", "nav.search") == "検索"


def test_translate_chinese():
    assert t("zh", "nav.search") == "搜索"


def test_translate_hindi():
    assert t("hi", "nav.search") == "खोजें"
    assert normalize_locale("hi-IN") == "hi"


def test_translate_english():
    assert t("en", "nav.search") == "Search"
    assert t("en", "footer.version", version="1.0") == "Version 1.0"


def test_translate_german():
    assert t("de", "nav.search") == "Suchen"
    assert t("de", "account.settings.title") == "Einstellungen"


def test_missing_key_falls_back_to_english():
    assert t("de", "missing.key.example") == "missing.key.example"


def test_german_home_page(client):
    response = client.get("/", cookies={"aiwiki_locale": "de"})
    assert response.status_code == 200
    assert "Willkommen bei AIWiki" in response.text
    assert "Letzte Änderungen" in response.text
    assert "Zufälliger Artikel" in response.text


def test_german_search_page(client):
    response = client.get("/search", cookies={"aiwiki_locale": "de"})
    assert response.status_code == 200
    assert "Artikel suchen" in response.text
