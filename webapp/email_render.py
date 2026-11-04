import html
import re

from bs4 import BeautifulSoup

from mail_backend import MailMessage


# CSS2 (1998) allowed properties — everything else gets stripped.
_CSS2_PROPERTIES = {
    "background", "background-attachment", "background-color",
    "background-image", "background-position", "background-repeat",
    "border", "border-collapse", "border-color", "border-spacing",
    "border-style", "border-width",
    "border-top", "border-right", "border-bottom", "border-left",
    "border-top-color", "border-right-color", "border-bottom-color", "border-left-color",
    "border-top-style", "border-right-style", "border-bottom-style", "border-left-style",
    "border-top-width", "border-right-width", "border-bottom-width", "border-left-width",
    "bottom", "caption-side", "clear", "clip", "color", "content",
    "counter-increment", "counter-reset", "cursor",
    "direction", "display", "empty-cells", "float",
    "font", "font-family", "font-size", "font-style",
    "font-variant", "font-weight",
    "height", "left", "letter-spacing", "line-height",
    "list-style", "list-style-image", "list-style-position", "list-style-type",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "max-height", "max-width", "min-height", "min-width",
    "overflow", "padding",
    "padding-top", "padding-right", "padding-bottom", "padding-left",
    "page-break-after", "page-break-before", "page-break-inside",
    "position", "quotes", "right",
    "table-layout", "text-align", "text-decoration", "text-indent",
    "text-transform", "top", "unicode-bidi",
    "vertical-align", "visibility", "white-space",
    "width", "word-spacing", "z-index",
}

_CSS_PROP_RE = re.compile(r"([\w-]+)\s*:[^;\"'}]+;?", re.IGNORECASE)

_CSS_AT_RULES_POST2 = re.compile(
    r"@(?:font-face|keyframes|supports|layer|media)\b[^{]*\{(?:[^{}]*\{[^}]*\})*[^}]*\}",
    re.IGNORECASE | re.DOTALL,
)

_CSS_DISPLAY_POST2 = re.compile(
    r"display\s*:\s*(?:flex|inline-flex|grid|inline-grid)\s*;?",
    re.IGNORECASE,
)

_GRADIENT_RE = re.compile(r"(?:linear|radial|conic)-gradient\(", re.IGNORECASE)

_EXTERNAL_URL_RE = re.compile(r"url\s*\(\s*[\"']?\s*https?://", re.IGNORECASE)

_DANGEROUS_TAGS = {
    "script", "iframe", "frame", "frameset", "object", "embed",
    "applet", "form", "input", "textarea", "select", "button", "base",
}


def sanitize_email_html(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html or "", "html.parser")

    for tag in soup.find_all(_DANGEROUS_TAGS):
        tag.decompose()

    for tag in soup.find_all(True):
        attrs = dict(tag.attrs)

        for key in list(attrs):
            if key.lower().startswith("on"):
                del attrs[key]

        for key in ("href", "src", "action"):
            value = attrs.get(key)
            if isinstance(value, list):
                value = " ".join(value)
            if value and re.match(r"^\s*(?:javascript|vbscript|data\s*:text/html)\s*:", value, re.I):
                attrs[key] = "#"

        tag.attrs = attrs

    for meta in soup.find_all("meta"):
        if (meta.get("http-equiv") or "").lower() == "refresh":
            meta.decompose()

    return str(soup)


def _strip_non_css2_props(css_text: str) -> str:
    def _filter(match: re.Match) -> str:
        prop = match.group(1).strip().lower()
        if prop not in _CSS2_PROPERTIES:
            return ""

        value = match.group(0)
        if _GRADIENT_RE.search(value):
            return ""
        if _EXTERNAL_URL_RE.search(value):
            return ""
        return value

    return _CSS_PROP_RE.sub(_filter, css_text)


def downgrade_css(html_str: str) -> str:
    # Remove external stylesheet links.
    s = re.sub(r"<link[^>]*rel=[\"']?stylesheet[\"']?[^>]*>", "", html_str, flags=re.IGNORECASE)
    s = re.sub(r"<link[^>]*type=[\"']?text/css[\"']?[^>]*>", "", s, flags=re.IGNORECASE)

    # Kill @import rules.
    s = re.sub(r"@import\b[^;]*;", "", s, flags=re.IGNORECASE)

    # Remove post-CSS2 at-rules.
    s = _CSS_AT_RULES_POST2.sub("", s)

    # Downgrade display:flex/grid to block.
    s = _CSS_DISPLAY_POST2.sub("display: block;", s)

    # Force Win98 system fonts.
    s = re.sub(
        r"font-family\s*:[^;\"'}]+",
        'font-family: "MS Sans Serif", "Microsoft Sans Serif", Tahoma, Arial, sans-serif',
        s,
        flags=re.IGNORECASE,
    )

    # Catch the shorthand font: property.
    s = re.sub(
        r"(font\s*:\s*(?:italic\s+|normal\s+|bold\s+|lighter\s+|bolder\s+|\d+\s+)*\d+[^;/]*?)/[^;\"'}]*",
        r"\1",
        s,
        flags=re.IGNORECASE,
    )

    def _clean_rule_body(match: re.Match) -> str:
        return "{" + _strip_non_css2_props(match.group(1)) + "}"

    def _clean_style_block(match: re.Match) -> str:
        css = match.group(2)
        css = re.sub(r"<!--\s*", "", css)
        css = re.sub(r"\s*-->", "", css)
        css = re.sub(r"\{([^}]*)\}", _clean_rule_body, css)
        return match.group(1) + css + match.group(3)

    s = re.sub(
        r"(<style[^>]*>)(.*?)(</style>)",
        _clean_style_block,
        s,
        flags=re.DOTALL | re.IGNORECASE,
    )

    def _clean_inline_style(match: re.Match) -> str:
        quote = match.group(1)
        cleaned = _strip_non_css2_props(match.group(2))
        if not cleaned.strip():
            return ""
        return f"style={quote}{cleaned}{quote}"

    s = re.sub(
        r'style=(["\'])(.*?)\1',
        _clean_inline_style,
        s,
        flags=re.DOTALL | re.IGNORECASE,
    )

    return s


def build_header(msg: MailMessage) -> str:
    header = (
        "<div style='background:#c0c0c0; padding:4px 6px; margin:0; "
        "font-family:MS Sans Serif,Tahoma,sans-serif; font-size:8pt; "
        "border-bottom:1px solid #808080;'>"
        f"<b>From:</b> {html.escape(msg.sender)}<br>"
        f"<b>To:</b> {html.escape(msg.to)}<br>"
    )
    if msg.cc:
        header += f"<b>Cc:</b> {html.escape(msg.cc)}<br>"
    header += (
        f"<b>Date:</b> {html.escape(msg.date)}<br>"
        f"<b>Subject:</b> {html.escape(msg.subject)}"
    )
    header += "</div>"
    return header


def render_message_html(msg: MailMessage, load_images: bool = False) -> str:
    header = build_header(msg)

    if msg.body_html:
        body = sanitize_email_html(msg.body_html)
    elif msg.body_text:
        body = (
            "<pre style='font-family:Courier New,monospace; font-size:9pt; "
            "white-space:pre-wrap; margin:8px;'>"
            f"{html.escape(msg.body_text)}</pre>"
        )
    else:
        body = "<p style='margin:8px; color:#808080;'>(No content)</p>"

    content = downgrade_css(header + body)

    img_src = "img-src * data:" if load_images else "img-src 'self' data:"
    return (
        "<html><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' "
        f"content=\"default-src 'none'; style-src 'unsafe-inline'; {img_src}; font-src 'none';\">"
        "</head><body style='margin:0; padding:0;'>"
        f"{content}"
        "</body></html>"
    )
