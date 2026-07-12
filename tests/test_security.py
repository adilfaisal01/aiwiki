import security


def test_render_markdown_strips_script_tags():
    html = security.render_markdown("## Title\n\nHello\n\n<script>alert('xss')</script>")
    assert "<script>" not in html
    assert "</script>" not in html


def test_validate_agent_name_rejects_invalid_chars():
    try:
        security.validate_agent_name("Bad<Name>")
        assert False, "expected ValidationError"
    except security.ValidationError:
        pass


def test_validate_title_required():
    try:
        security.validate_title("   ")
        assert False, "expected ValidationError"
    except security.ValidationError:
        pass
