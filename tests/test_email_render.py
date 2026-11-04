from webapp.email_render import downgrade_css, sanitize_email_html, render_message_html
from mail_backend import MailMessage


def test_external_stylesheet_is_removed():
    html = '<link rel="stylesheet" href="https://example.com/style.css">'
    assert "example.com/style.css" not in downgrade_css(html)


def test_import_is_removed():
    html = "<style>@import url('https://example.com/x.css'); body { color: red; }</style>"
    assert "@import" not in downgrade_css(html)


def test_flex_is_downgraded():
    html = "<style>div { display: flex; color: red; }</style>"
    out = downgrade_css(html)
    assert "display: block;" in out
    assert "display: flex" not in out


def test_gradient_is_removed():
    html = "<div style='background: linear-gradient(#fff, #000); color: red;'>x</div>"
    out = downgrade_css(html)
    assert "linear-gradient" not in out
    assert "color: red" in out


def test_external_url_is_removed():
    html = "<div style='background-image: url(https://example.com/a.png); color: red;'>x</div>"
    out = downgrade_css(html)
    assert "example.com/a.png" not in out
    assert "color: red" in out


def test_win98_font_is_forced():
    html = "<div style='font-family: Arial; color: red;'>x</div>"
    out = downgrade_css(html)
    assert "MS Sans Serif" in out


def test_dangerous_tags_and_event_handlers_are_removed():
    raw = "<script>alert(1)</script><div onclick='bad()'>ok</div>"
    out = sanitize_email_html(raw)
    assert "<script" not in out
    assert "onclick" not in out
    assert "ok" in out


def test_javascript_url_is_replaced():
    raw = '<a href="javascript:alert(1)">x</a>'
    out = sanitize_email_html(raw)
    assert "javascript:" not in out
    assert 'href="#"' in out or "href=\"#\"" in out


def test_render_message_html_produces_csp_document():
    msg = MailMessage(
        uid=1,
        subject="Hello",
        sender="a@example.com",
        to="b@example.com",
        date="2026-01-01",
        seen=False,
        body_html="<p>Hello</p>",
    )
    out = render_message_html(msg)
    assert "Content-Security-Policy" in out
    assert "Hello" in out
    assert "<script" not in out
