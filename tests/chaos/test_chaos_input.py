import pytest
from core import security


@pytest.mark.tier1
class TestUnicodeFuzzing:
    @pytest.mark.xfail(reason="Bleach does not normalize fullwidth characters")
    def test_fullwidth_chars_bypass_bleach(self):
        content = "\uff1cscript\uff1ealert(1)\uff1c/script\uff1e"
        result = security.sanitize_article_html(content)
        assert "<script>" not in result
        assert "alert" not in result

    @pytest.mark.xfail(reason="Bleach does not strip zero-width joiners in tags")
    def test_zero_width_joiner_injection(self):
        content = "<scr\u200dipt>alert(1)</script>"
        result = security.sanitize_article_html(content)
        assert "alert" not in result

    @pytest.mark.xfail(reason="Bleach does not handle RTL override characters")
    def test_rtl_override(self):
        content = "normal \u202e<script>alert(1)</script> text"
        result = security.sanitize_article_html(content)
        assert "alert" not in result

    @pytest.mark.xfail(reason="URL validation does not normalize combining characters")
    def test_combining_chars_in_url(self):
        url = "http://evil.com\u0301/phishing"
        result = security.validate_webhook_url(url)
        assert result[0] is False


@pytest.mark.tier1
class TestReDoS:
    @pytest.mark.xfail(reason="Wikilink regex can cause ReDoS with deeply nested brackets")
    def test_nested_wikilinks(self):
        content = "[[" * 5000 + "a" + "]]" * 5000
        from core.security import render_markdown
        import time
        start = time.perf_counter()
        render_markdown(content)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0

    def test_long_agent_name(self):
        with pytest.raises(security.ValidationError):
            security.validate_agent_name("a" * 81)
        name = security.validate_agent_name("a" * 80)
        assert len(name) == 80


@pytest.mark.tier1
class TestNullBytes:
    def test_null_byte_in_title(self):
        result = security.validate_title("Test\x00Article")
        assert "\x00" not in result

    def test_null_byte_in_content(self):
        from core.database import prepare_article_content
        result = prepare_article_content("Hello\x00World")
        assert "\x00" not in result


@pytest.mark.tier1
class TestBoundaries:
    def test_exactly_max_content(self):
        content = "A" * 500_000
        from core.database import prepare_article_content
        result = prepare_article_content(content)
        assert len(result) == 500_000

    def test_exceed_max_content(self):
        content = "A" * 500_001
        from core.database import prepare_article_content
        result = prepare_article_content(content)
        assert len(result) == 500_000

    def test_empty_content(self):
        from core.security import validate_content
        with pytest.raises(security.ValidationError):
            validate_content("")

    def test_whitespace_only_content(self):
        from core.security import validate_content
        with pytest.raises(security.ValidationError):
            validate_content("   \n\t  ")


@pytest.mark.tier1
class TestMathInjection:
    @pytest.mark.xfail(reason="Math placeholder injection is possible if attacker knows the sentinel")
    def test_math_placeholder_injection(self):
        from core.security import protect_math, restore_math
        content = "Some text \x00MATH0\x00 more text"
        protected = protect_math(content)
        restored = restore_math(protected)
        assert "\x00MATH0\x00" not in restored
