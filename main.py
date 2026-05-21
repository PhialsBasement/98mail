import sys
import json
import os
import re
import html
import keyring
from pathlib import Path
from email.utils import parsedate_to_datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QTextEdit, QToolBar, QStatusBar, QDialog, QLabel, QLineEdit,
    QPushButton, QFormLayout, QCheckBox, QMessageBox, QHeaderView,
    QMenu, QMenuBar, QFileDialog, QComboBox, QProgressBar, QFrame,
    QAbstractItemView, QSpinBox, QSizePolicy,
)
from PySide6.QtCore import (
    Qt, QThread, Signal, QSize, QSettings, QTimer, QUrl,
    QPropertyAnimation, QEasingCurve, QRect, QPoint, Property,
)
from PySide6.QtGui import (
    QAction, QFont, QIcon, QColor, QPixmap, QPainter, QPen, QBrush,
    QFontMetrics, QDesktopServices,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage

from mail_backend import MailClient, MailAccount, MailMessage
from win98style import get_stylesheet

KEYRING_SERVICE = "98mail"

_DANGEROUS_TAGS_RE = re.compile(
    r"<\s*(?:script|iframe|frame|frameset|object|embed|applet|form|input|textarea|select|button|base)\b[^>]*>.*?</\s*(?:script|iframe|frame|frameset|object|embed|applet|form|input|textarea|select|button|base)\s*>|"
    r"<\s*(?:script|iframe|frame|frameset|object|embed|applet|form|input|textarea|select|button|base)\b[^>]*/?\s*>",
    re.IGNORECASE | re.DOTALL,
)

_EVENT_HANDLER_RE = re.compile(
    r"\s+on\w+\s*=\s*(?:\"[^\"]*\"|'[^']*'|\S+)",
    re.IGNORECASE,
)

_JS_URL_RE = re.compile(
    r'(href|src|action)\s*=\s*(["\'])?\s*(?:javascript|vbscript|data\s*:text/html)\s*:',
    re.IGNORECASE,
)

_META_REFRESH_RE = re.compile(
    r'<\s*meta[^>]*http-equiv\s*=\s*["\']?refresh[^>]*>',
    re.IGNORECASE,
)


def _sanitize_email_html(raw_html: str) -> str:
    s = _DANGEROUS_TAGS_RE.sub("", raw_html)
    s = _EVENT_HANDLER_RE.sub("", s)
    s = _JS_URL_RE.sub(r'\1=\2#', s)
    s = _META_REFRESH_RE.sub("", s)
    return s


class RestrictedPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            QDesktopServices.openUrl(url)
            return False
        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

CONFIG_DIR = Path.home() / ".98mail"
CONFIG_FILE = CONFIG_DIR / "accounts.json"

# CSS2 (1998) allowed properties — everything else gets stripped
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

_CSS_PROP_RE = re.compile(
    r"([\w-]+)\s*:[^;\"'}]+;?",
    re.IGNORECASE,
)

_CSS_AT_RULES_POST2 = re.compile(
    r"@(?:font-face|keyframes|supports|layer|media)\b[^{]*\{(?:[^{}]*\{[^}]*\})*[^}]*\}",
    re.IGNORECASE | re.DOTALL,
)

_CSS_DISPLAY_POST2 = re.compile(
    r"display\s*:\s*(?:flex|inline-flex|grid|inline-grid)\s*;?",
    re.IGNORECASE,
)


_GRADIENT_RE = re.compile(
    r"(?:linear|radial|conic)-gradient\(", re.IGNORECASE,
)

_EXTERNAL_URL_RE = re.compile(
    r"url\s*\(\s*[\"']?\s*https?://", re.IGNORECASE,
)

def _strip_non_css2_props(css_text: str) -> str:
    def _filter(m):
        prop = m.group(1).strip().lower()
        if prop not in _CSS2_PROPERTIES:
            return ""
        value = m.group(0)
        if _GRADIENT_RE.search(value):
            return ""
        if _EXTERNAL_URL_RE.search(value):
            return ""
        return value
    return _CSS_PROP_RE.sub(_filter, css_text)


def _downgrade_css(html_str: str) -> str:
    # Remove external stylesheet links
    s = re.sub(r"<link[^>]*rel=[\"']?stylesheet[\"']?[^>]*>", "", html_str, flags=re.IGNORECASE)
    s = re.sub(r"<link[^>]*type=[\"']?text/css[\"']?[^>]*>", "", s, flags=re.IGNORECASE)

    # Kill @import rules (loads external CSS/fonts)
    s = re.sub(r"@import\b[^;]*;", "", s, flags=re.IGNORECASE)

    # Remove post-CSS2 at-rules
    s = _CSS_AT_RULES_POST2.sub("", s)

    # Downgrade display:flex/grid to block
    s = _CSS_DISPLAY_POST2.sub("display: block;", s)

    # Force all fonts to Win98 system fonts
    s = re.sub(
        r"font-family\s*:[^;\"'}]+",
        'font-family: "MS Sans Serif", "Microsoft Sans Serif", Tahoma, Arial, sans-serif',
        s, flags=re.IGNORECASE,
    )
    # Also catch the shorthand font: property
    s = re.sub(
        r"(font\s*:\s*(?:italic\s+|normal\s+|bold\s+|lighter\s+|bolder\s+|\d+\s+)*\d+[^;/]*?)/[^;\"'}]*",
        r"\1",
        s, flags=re.IGNORECASE,
    )

    # Strip non-CSS2 properties inside { } blocks within <style> tags
    def _clean_rule_body(m):
        return "{" + _strip_non_css2_props(m.group(1)) + "}"

    def _clean_style_block(m):
        css = m.group(2)
        # Strip HTML comment wrappers
        css = re.sub(r"<!--\s*", "", css)
        css = re.sub(r"\s*-->", "", css)
        # Only process inside { } braces, leave selectors alone
        css = re.sub(r"\{([^}]*)\}", _clean_rule_body, css)
        return m.group(1) + css + m.group(3)

    s = re.sub(
        r"(<style[^>]*>)(.*?)(</style>)",
        _clean_style_block,
        s, flags=re.DOTALL | re.IGNORECASE,
    )

    # Strip non-CSS2 properties from inline style="" attributes
    def _clean_inline_style(m):
        quote = m.group(1)
        cleaned = _strip_non_css2_props(m.group(2))
        if not cleaned.strip():
            return ""
        return f"style={quote}{cleaned}{quote}"

    s = re.sub(
        r'style=(["\'])(.*?)\1',
        _clean_inline_style,
        s, flags=re.DOTALL | re.IGNORECASE,
    )

    return s


# ─── Pixel-art icon generation ───

def _make_pixmap(size, draw_func):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, False)
    draw_func(p, size)
    p.end()
    return QIcon(pm)


def icon_mail_new():
    def draw(p, s):
        p.setPen(QPen(QColor("#000000"), 1))
        p.setBrush(QBrush(QColor("#FFFFCC")))
        p.drawRect(2, 4, s - 5, s - 8)
        p.drawLine(2, 4, s // 2, s // 2 - 1)
        p.drawLine(s - 3, 4, s // 2, s // 2 - 1)
    return _make_pixmap(20, draw)


def icon_reply():
    def draw(p, s):
        p.setPen(QPen(QColor("#000080"), 2))
        p.drawLine(4, s // 2, s - 4, s // 2)
        p.drawLine(4, s // 2, 8, s // 2 - 4)
        p.drawLine(4, s // 2, 8, s // 2 + 4)
    return _make_pixmap(20, draw)


def icon_delete():
    def draw(p, s):
        p.setPen(QPen(QColor("#CC0000"), 2))
        p.drawLine(4, 4, s - 5, s - 5)
        p.drawLine(s - 5, 4, 4, s - 5)
    return _make_pixmap(20, draw)


def icon_refresh():
    def draw(p, s):
        p.setPen(QPen(QColor("#008000"), 2))
        # arc from 60° sweeping 300° clockwise (open at top-right)
        p.drawArc(4, 4, s - 8, s - 8, 60 * 16, 300 * 16)
        # arrowhead at the open end (top-right, pointing clockwise/down-right)
        ex, ey = s - 5, 5
        p.drawLine(ex, ey, ex + 3, ey - 2)
        p.drawLine(ex, ey, ex + 2, ey + 3)
    return _make_pixmap(20, draw)


def icon_folder():
    def draw(p, s):
        p.setPen(QPen(QColor("#000000"), 1))
        p.setBrush(QBrush(QColor("#FFD700")))
        p.drawRect(2, 3, 6, 3)
        p.drawRect(2, 5, s - 5, s - 9)
    return _make_pixmap(20, draw)


def icon_send():
    def draw(p, s):
        p.setPen(QPen(QColor("#000080"), 2))
        p.drawLine(4, s // 2, s - 4, s // 2)
        p.drawLine(s - 8, s // 2 - 4, s - 4, s // 2)
        p.drawLine(s - 8, s // 2 + 4, s - 4, s // 2)
    return _make_pixmap(20, draw)


def icon_attach():
    def draw(p, s):
        p.setPen(QPen(QColor("#808080"), 2))
        p.drawLine(s // 2, 4, s // 2, s - 4)
        p.drawArc(s // 2 - 4, 4, 8, 8, 0, 180 * 16)
    return _make_pixmap(20, draw)


# ─── Win9x Animations & Effects ───

class SplashScreen(QDialog):
    """Classic Win98 boot-style splash with progress bar."""
    connected_client = Signal(object)

    def __init__(self, saved_account: dict | None = None):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._saved_account = saved_account
        self._client: MailClient | None = None
        self._connect_error: str | None = None
        self.setFixedSize(360, 200)
        self.setStyleSheet("background-color: #c0c0c0;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)

        outer = QFrame()
        outer.setStyleSheet(
            "border-top: 2px solid #ffffff; border-left: 2px solid #ffffff;"
            "border-bottom: 2px solid #404040; border-right: 2px solid #404040;"
            "background-color: #c0c0c0;"
        )
        outer_layout = QVBoxLayout(outer)

        title_bar = QLabel("  98Mail")
        title_bar.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #000080, stop:1 #1084d0);"
            "color: white; font-weight: bold; font-size: 9pt;"
            "padding: 3px; border: none;"
        )
        outer_layout.addWidget(title_bar)

        outer_layout.addSpacing(8)

        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("border: none;")
        logo_pm = QPixmap(48, 48)
        logo_pm.fill(Qt.transparent)
        lp = QPainter(logo_pm)
        lp.setRenderHint(QPainter.Antialiasing, False)
        lp.setPen(QPen(QColor("#000000"), 1))
        lp.setBrush(QBrush(QColor("#FFFFCC")))
        lp.drawRect(4, 10, 40, 28)
        lp.drawLine(4, 10, 24, 26)
        lp.drawLine(44, 10, 24, 26)
        lp.setPen(QPen(QColor("#000080"), 2))
        lp.drawText(8, 8, "98")
        lp.end()
        logo.setPixmap(logo_pm)
        outer_layout.addWidget(logo)

        name_label = QLabel("98Mail - Internet Mail Client")
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("font-size: 10pt; font-weight: bold; border: none;")
        outer_layout.addWidget(name_label)

        ver_label = QLabel("Version 1.0")
        ver_label.setAlignment(Qt.AlignCenter)
        ver_label.setStyleSheet("font-size: 8pt; color: #404040; border: none;")
        outer_layout.addWidget(ver_label)

        outer_layout.addSpacing(8)

        self.status_label = QLabel("Initializing...")
        self.status_label.setStyleSheet("font-size: 8pt; border: none; padding-left: 4px;")
        outer_layout.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(18)
        outer_layout.addWidget(self.progress)

        layout.addWidget(outer)

        self._step = 0
        self._tried_connect = False
        if self._saved_account:
            self._messages = [
                "Initializing...",
                "Loading mail components...",
                "Connecting to mail server...",
                "Authenticating...",
                "Loading address book...",
                "Ready.",
            ]
        else:
            self._messages = [
                "Initializing...",
                "Loading mail components...",
                "Preparing user interface...",
                "Registering MAPI services...",
                "Loading address book...",
                "Ready.",
            ]
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(180)

    def _tick(self):
        self._step += 4
        self.progress.setValue(min(self._step, 100))
        idx = min(self._step // 20, len(self._messages) - 1)
        self.status_label.setText(self._messages[idx])

        if self._step >= 40 and not self._tried_connect and self._saved_account:
            self._tried_connect = True
            self._try_connect()

        if self._step >= 100:
            self._timer.stop()
            QTimer.singleShot(200, self.accept)

    def _try_connect(self):
        try:
            account = MailAccount(
                imap_host=self._saved_account["imap_host"],
                imap_port=self._saved_account["imap_port"],
                smtp_host=self._saved_account["smtp_host"],
                smtp_port=self._saved_account["smtp_port"],
                username=self._saved_account["username"],
                password=self._saved_account["password"],
                use_ssl=self._saved_account.get("use_ssl", True),
            )
            client = MailClient(account)
            client.connect_imap()
            self._client = client
        except Exception as e:
            self._connect_error = str(e)
            self._client = None


class MarqueeLabel(QLabel):
    """Scrolling text label, like the classic Win98 status ticker."""
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = text
        self._offset = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll)
        self.setStyleSheet("border: none; background: transparent;")

    def start(self, text: str):
        self._full_text = "    " + text + "    "
        self._offset = 0
        self.setText(self._full_text)
        self._timer.start(80)

    def stop(self):
        self._timer.stop()
        self.setText("")

    def _scroll(self):
        self._offset += 1
        if self._offset >= len(self._full_text):
            self._offset = 0
        display = self._full_text[self._offset:] + self._full_text[:self._offset]
        self.setText(display)


class SendingDialog(QDialog):
    """Animated 'sending mail' dialog with envelope animation."""
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setFixedSize(300, 120)
        self.setStyleSheet("background-color: #c0c0c0;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)

        outer = QFrame()
        outer.setStyleSheet(
            "border-top: 2px solid #ffffff; border-left: 2px solid #ffffff;"
            "border-bottom: 2px solid #404040; border-right: 2px solid #404040;"
            "background-color: #c0c0c0;"
        )
        inner = QVBoxLayout(outer)

        title = QLabel("  Sending Message...")
        title.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #000080, stop:1 #1084d0);"
            "color: white; font-weight: bold; padding: 2px; border: none;"
        )
        inner.addWidget(title)

        inner.addSpacing(4)

        self._anim_label = QLabel()
        self._anim_label.setAlignment(Qt.AlignCenter)
        self._anim_label.setFixedHeight(32)
        self._anim_label.setStyleSheet("border: none;")
        inner.addWidget(self._anim_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(16)
        inner.addWidget(self._progress)

        layout.addWidget(outer)

        self._frame = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._animate)
        self._anim_timer.start(150)

    def _animate(self):
        self._frame = (self._frame + 1) % 20
        pm = QPixmap(200, 28)
        pm.fill(QColor("#c0c0c0"))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, False)

        x_pos = self._frame * 10
        # draw envelope flying across
        p.setPen(QPen(QColor("#000000"), 1))
        p.setBrush(QBrush(QColor("#FFFFCC")))
        p.drawRect(x_pos, 6, 18, 12)
        p.drawLine(x_pos, 6, x_pos + 9, 14)
        p.drawLine(x_pos + 18, 6, x_pos + 9, 14)

        # draw "motion lines" behind envelope
        p.setPen(QPen(QColor("#808080"), 1))
        for i in range(3):
            lx = x_pos - 6 - i * 5
            if lx > 0:
                p.drawLine(lx, 10 + i * 2, lx + 3, 10 + i * 2)

        # draw receiving computer on right side
        p.setPen(QPen(QColor("#000000"), 1))
        p.setBrush(QBrush(QColor("#c0c0c0")))
        p.drawRect(175, 2, 20, 16)
        p.drawRect(180, 18, 10, 4)
        p.setBrush(QBrush(QColor("#000080")))
        p.drawRect(177, 4, 16, 12)

        p.end()
        self._anim_label.setPixmap(pm)


class DeleteAnimation(QDialog):
    """'Emptying' style animation for deleting mail."""
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setFixedSize(260, 100)
        self.setStyleSheet("background-color: #c0c0c0;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)

        outer = QFrame()
        outer.setStyleSheet(
            "border-top: 2px solid #ffffff; border-left: 2px solid #ffffff;"
            "border-bottom: 2px solid #404040; border-right: 2px solid #404040;"
            "background-color: #c0c0c0;"
        )
        inner = QVBoxLayout(outer)

        title = QLabel("  Deleting...")
        title.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #000080, stop:1 #1084d0);"
            "color: white; font-weight: bold; padding: 2px; border: none;"
        )
        inner.addWidget(title)

        self._anim_label = QLabel()
        self._anim_label.setAlignment(Qt.AlignCenter)
        self._anim_label.setFixedHeight(32)
        self._anim_label.setStyleSheet("border: none;")
        inner.addWidget(self._anim_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(16)
        inner.addWidget(self._progress)

        layout.addWidget(outer)

        self._frame = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(100)

    def _animate(self):
        self._frame += 5
        self._progress.setValue(min(self._frame, 100))

        pm = QPixmap(200, 28)
        pm.fill(QColor("#c0c0c0"))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, False)

        # envelope on left, gets crumpled
        shrink = min(self._frame // 10, 8)
        ex, ey = 30, 4
        ew = max(18 - shrink, 4)
        eh = max(12 - shrink // 2, 4)

        x_pos = 30 + (self._frame * 2) // 3
        y_pos = 4 + shrink

        p.setPen(QPen(QColor("#000000"), 1))
        p.setBrush(QBrush(QColor("#FFFFCC")))
        if self._frame < 80:
            p.drawRect(x_pos, y_pos, ew, eh)
        # trash can on right
        p.setPen(QPen(QColor("#000000"), 1))
        p.setBrush(QBrush(QColor("#808080")))
        p.drawRect(150, 6, 20, 18)
        p.setBrush(QBrush(QColor("#c0c0c0")))
        p.drawRect(148, 3, 24, 4)
        p.drawLine(155, 10, 155, 20)
        p.drawLine(160, 10, 160, 20)
        p.drawLine(165, 10, 165, 20)

        p.end()
        self._anim_label.setPixmap(pm)

        if self._frame >= 100:
            self._timer.stop()
            QTimer.singleShot(150, self.accept)


class AboutDialog(QDialog):
    """Win98-style About dialog with scrolling credits."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About 98Mail")
        self.setFixedSize(340, 280)

        layout = QVBoxLayout(self)

        logo_frame = QFrame()
        logo_frame.setFixedHeight(80)
        logo_frame.setStyleSheet(
            "background-color: #000080;"
            "border-top: 2px solid #808080;"
            "border-left: 2px solid #808080;"
            "border-bottom: 2px solid #ffffff;"
            "border-right: 2px solid #ffffff;"
        )
        logo_layout = QVBoxLayout(logo_frame)
        title = QLabel("98Mail")
        title.setStyleSheet("color: white; font-size: 18pt; font-weight: bold; border: none;")
        title.setAlignment(Qt.AlignCenter)
        logo_layout.addWidget(title)
        subtitle = QLabel("Internet Mail Client v1.0")
        subtitle.setStyleSheet("color: #c0c0c0; font-size: 8pt; border: none;")
        subtitle.setAlignment(Qt.AlignCenter)
        logo_layout.addWidget(subtitle)
        layout.addWidget(logo_frame)

        layout.addSpacing(4)

        self._credits_label = QLabel()
        self._credits_label.setAlignment(Qt.AlignCenter)
        self._credits_label.setStyleSheet(
            "border-top: 2px solid #808080; border-left: 2px solid #808080;"
            "border-bottom: 2px solid #ffffff; border-right: 2px solid #ffffff;"
            "background: white; padding: 4px;"
        )
        self._credits_label.setFixedHeight(100)
        self._credits_label.setWordWrap(True)
        layout.addWidget(self._credits_label)

        self._credits = [
            "A Windows 98-style email client",
            "compatible with Docker Mailserver",
            "",
            "IMAP / SMTP",
            "",
            "Built with Python & PySide6",
            "",
            "© 2026",
            "",
            "Thanks for using 98Mail!",
            "",
            "",
        ]
        self._scroll_pos = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scroll_credits)
        self._timer.start(300)
        self._scroll_credits()

        layout.addSpacing(4)

        info_label = QLabel(
            "This product is licensed for personal use.\n"
            "Compatible with Docker Mailserver (IMAP/SMTP)."
        )
        info_label.setStyleSheet("font-size: 8pt; color: #404040;")
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def _scroll_credits(self):
        visible = 5
        lines = []
        for i in range(visible):
            idx = (self._scroll_pos + i) % len(self._credits)
            lines.append(self._credits[idx])
        self._credits_label.setText("\n".join(lines))
        self._scroll_pos = (self._scroll_pos + 1) % len(self._credits)


class NewMailNotification(QDialog):
    """Slide-up 'You have new mail' toast, Win98/ME style."""
    def __init__(self, count: int, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setFixedSize(220, 60)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet("background-color: #FFFFCC;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)

        frame = QFrame()
        frame.setStyleSheet(
            "border-top: 2px solid #ffffff; border-left: 2px solid #ffffff;"
            "border-bottom: 2px solid #404040; border-right: 2px solid #404040;"
            "background-color: #FFFFCC;"
        )
        fl = QHBoxLayout(frame)
        fl.setContentsMargins(6, 4, 6, 4)

        icon_label = QLabel()
        icon_label.setPixmap(icon_mail_new().pixmap(20, 20))
        icon_label.setStyleSheet("border: none;")
        fl.addWidget(icon_label)

        text = QLabel(f"You have {count} new message{'s' if count != 1 else ''}!")
        text.setStyleSheet("font-weight: bold; font-size: 8pt; border: none;")
        fl.addWidget(text)
        fl.addStretch()

        layout.addWidget(frame)

        QTimer.singleShot(3000, self._fade_out)

    def showEvent(self, event):
        super().showEvent(event)
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen:
            self.move(screen.right() - self.width() - 8, screen.bottom() + self.height())
            self._slide_anim = QPropertyAnimation(self, b"pos")
            self._slide_anim.setDuration(300)
            self._slide_anim.setStartValue(self.pos())
            self._slide_anim.setEndValue(QPoint(
                screen.right() - self.width() - 8,
                screen.bottom() - self.height() - 8
            ))
            self._slide_anim.setEasingCurve(QEasingCurve.OutQuad)
            self._slide_anim.start()

    def _fade_out(self):
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen:
            self._out_anim = QPropertyAnimation(self, b"pos")
            self._out_anim.setDuration(300)
            self._out_anim.setStartValue(self.pos())
            self._out_anim.setEndValue(QPoint(
                screen.right() - self.width() - 8,
                screen.bottom() + self.height()
            ))
            self._out_anim.setEasingCurve(QEasingCurve.InQuad)
            self._out_anim.finished.connect(self.close)
            self._out_anim.start()
        else:
            self.close()


class _DateTableItem(QTableWidgetItem):
    """QTableWidgetItem that sorts by parsed timestamp, not string."""
    def __init__(self, raw_date: str):
        display = raw_date[:24] if raw_date else ""
        super().__init__(display)
        try:
            self._ts = parsedate_to_datetime(raw_date).timestamp()
        except Exception:
            self._ts = 0.0

    def __lt__(self, other):
        if isinstance(other, _DateTableItem):
            return self._ts < other._ts
        return super().__lt__(other)


# ─── Worker Threads ───

class FetchFoldersWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, client: MailClient):
        super().__init__()
        self.client = client

    def run(self):
        try:
            folders = self.client.list_folders()
            self.finished.emit(folders)
        except Exception as e:
            self.error.emit(str(e))


class FetchMessagesWorker(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, client: MailClient, folder: str):
        super().__init__()
        self.client = client
        self.folder = folder

    def run(self):
        try:
            messages = self.client.fetch_message_list(self.folder)
            self.finished.emit(messages)
        except Exception as e:
            self.error.emit(str(e))


class FetchMessageWorker(QThread):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, client: MailClient, uid: int, folder: str):
        super().__init__()
        self.client = client
        self.uid = uid
        self.folder = folder

    def run(self):
        try:
            msg = self.client.fetch_message(self.uid, self.folder)
            self.finished.emit(msg)
        except Exception as e:
            self.error.emit(str(e))


class SendMessageWorker(QThread):
    finished = Signal()
    error = Signal(str)

    def __init__(self, client: MailClient, to, subject, body, cc="",
                 attachments=None, in_reply_to="", references=""):
        super().__init__()
        self.client = client
        self.to = to
        self.subject = subject
        self.body = body
        self.cc = cc
        self.attachments = attachments or []
        self.in_reply_to = in_reply_to
        self.references = references

    def run(self):
        try:
            self.client.send_message(
                self.to, self.subject, self.body, self.cc,
                self.attachments, self.in_reply_to, self.references
            )
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class DeleteMessageWorker(QThread):
    finished = Signal()
    error = Signal(str)

    def __init__(self, client: MailClient, uid: int, folder: str):
        super().__init__()
        self.client = client
        self.uid = uid
        self.folder = folder

    def run(self):
        try:
            self.client.delete_message(self.uid, self.folder)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


# ─── Login Dialog ───

class LoginDialog(QDialog):
    def __init__(self, parent=None, saved: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("98Mail - Connect to Mail Server")
        self.setFixedSize(420, 380)
        self.setModal(True)

        layout = QVBoxLayout(self)

        title = QLabel("Mail Server Connection")
        title_font = QFont("MS Sans Serif", 12, QFont.Bold)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("background-color: #000080; color: white; padding: 6px; border: 2px outset #c0c0c0;")
        layout.addWidget(title)

        form = QFormLayout()

        self.imap_host = QLineEdit(saved.get("imap_host", "") if saved else "")
        self.imap_host.setPlaceholderText("mail.example.com")
        form.addRow("IMAP Server:", self.imap_host)

        self.imap_port = QSpinBox()
        self.imap_port.setRange(1, 65535)
        self.imap_port.setValue(saved.get("imap_port", 993) if saved else 993)
        form.addRow("IMAP Port:", self.imap_port)

        self.smtp_host = QLineEdit(saved.get("smtp_host", "") if saved else "")
        self.smtp_host.setPlaceholderText("mail.example.com")
        form.addRow("SMTP Server:", self.smtp_host)

        self.smtp_port = QSpinBox()
        self.smtp_port.setRange(1, 65535)
        self.smtp_port.setValue(saved.get("smtp_port", 587) if saved else 587)
        form.addRow("SMTP Port:", self.smtp_port)

        self.username = QLineEdit(saved.get("username", "") if saved else "")
        self.username.setPlaceholderText("user@example.com")
        form.addRow("Username:", self.username)

        self.password = QLineEdit(saved.get("password", "") if saved else "")
        self.password.setEchoMode(QLineEdit.Password)
        form.addRow("Password:", self.password)

        self.use_ssl = QCheckBox("Use SSL/TLS")
        self.use_ssl.setChecked(saved.get("use_ssl", True) if saved else True)
        form.addRow("", self.use_ssl)

        self.save_account = QCheckBox("Remember this account")
        self.save_account.setChecked(True)
        form.addRow("", self.save_account)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        connect_btn = QPushButton("Connect")
        connect_btn.setDefault(True)
        connect_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(connect_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def get_account(self) -> MailAccount:
        return MailAccount(
            imap_host=self.imap_host.text().strip(),
            imap_port=self.imap_port.value(),
            smtp_host=self.smtp_host.text().strip(),
            smtp_port=self.smtp_port.value(),
            username=self.username.text().strip(),
            password=self.password.text(),
            use_ssl=self.use_ssl.isChecked(),
        )

    def should_save(self) -> bool:
        return self.save_account.isChecked()


# ─── Compose Window ───

class ComposeWindow(QDialog):
    def __init__(self, client: MailClient, parent=None,
                 reply_to: MailMessage | None = None, reply_all: bool = False):
        super().__init__(parent)
        self.client = client
        self.reply_to = reply_to
        self.attachment_paths: list[str] = []
        self._worker = None

        self.setWindowTitle("New Message" if not reply_to else f"Re: {reply_to.subject}")
        self.resize(550, 450)

        layout = QVBoxLayout(self)

        toolbar = QToolBar()
        toolbar.setIconSize(QSize(20, 20))
        send_action = toolbar.addAction(icon_send(), "Send")
        send_action.triggered.connect(self._send)
        toolbar.addSeparator()
        attach_action = toolbar.addAction(icon_attach(), "Attach")
        attach_action.triggered.connect(self._attach_file)
        layout.addWidget(toolbar)

        form = QFormLayout()

        self.to_field = QLineEdit()
        form.addRow("To:", self.to_field)

        self.cc_field = QLineEdit()
        form.addRow("Cc:", self.cc_field)

        self.subject_field = QLineEdit()
        form.addRow("Subject:", self.subject_field)

        layout.addLayout(form)

        self.attachments_label = QLabel("")
        self.attachments_label.setStyleSheet("color: #808080; padding: 2px;")
        layout.addWidget(self.attachments_label)

        self.body_edit = QTextEdit()
        self.body_edit.setFont(QFont("Courier New", 10))
        layout.addWidget(self.body_edit)

        if reply_to:
            self.subject_field.setText(
                reply_to.subject if reply_to.subject.lower().startswith("re:") else f"Re: {reply_to.subject}"
            )
            self.to_field.setText(reply_to.sender)
            if reply_all and reply_to.cc:
                self.cc_field.setText(reply_to.cc)
            quote = reply_to.body_text or ""
            quoted = "\n".join(f"> {line}" for line in quote.splitlines())
            self.body_edit.setPlainText(
                f"\n\nOn {reply_to.date}, {reply_to.sender} wrote:\n{quoted}"
            )
            cursor = self.body_edit.textCursor()
            cursor.movePosition(cursor.Start)
            self.body_edit.setTextCursor(cursor)

    def _attach_file(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach Files")
        if paths:
            self.attachment_paths.extend(paths)
            names = [os.path.basename(p) for p in self.attachment_paths]
            self.attachments_label.setText(f"Attachments: {', '.join(names)}")

    def _send(self):
        to = self.to_field.text().strip()
        if not to:
            QMessageBox.warning(self, "98Mail", "Please enter a recipient.")
            return

        self._worker = SendMessageWorker(
            self.client,
            to=to,
            subject=self.subject_field.text().strip(),
            body=self.body_edit.toPlainText(),
            cc=self.cc_field.text().strip(),
            attachments=self.attachment_paths if self.attachment_paths else None,
            in_reply_to=self.reply_to.message_id if self.reply_to else "",
            references=self.reply_to.message_id if self.reply_to else "",
        )
        self._sending_dlg = SendingDialog(self)
        self._sending_dlg.show()
        self._worker.finished.connect(self._on_sent)
        self._worker.error.connect(self._on_send_error)
        self._worker.start()

    def _on_sent(self):
        if hasattr(self, "_sending_dlg") and self._sending_dlg:
            self._sending_dlg.close()
        QMessageBox.information(self, "98Mail", "Message sent successfully!")
        self.accept()

    def _on_send_error(self, err):
        if hasattr(self, "_sending_dlg") and self._sending_dlg:
            self._sending_dlg.close()
        QMessageBox.critical(self, "98Mail - Error", f"Failed to send message:\n{err}")


# ─── Main Window ───

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("98Mail - Internet Mail Client")
        self.resize(900, 620)

        self.client: MailClient | None = None
        self.current_folder = "INBOX"
        self.messages: dict[int, MailMessage] = {}
        self.current_message: MailMessage | None = None
        self._workers = []
        self._prev_unread_uids: set[int] = set()
        self._notification: NewMailNotification | None = None
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_new_mail)
        self._poll_timer.setInterval(30_000)
        self._new_mail_sound = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._audio_output.setVolume(0.35)
        self._new_mail_sound.setAudioOutput(self._audio_output)
        sound_path = Path(__file__).parent / "youve-got-mail-sound.mp3"
        if sound_path.exists():
            self._new_mail_sound.setSource(QUrl.fromLocalFile(str(sound_path)))

        self._setup_menu()
        self._setup_toolbar()
        self._setup_ui()
        self._setup_statusbar()

    def _setup_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        file_menu.addAction("Connect...", self._show_login)
        file_menu.addAction("Disconnect", self._disconnect)
        file_menu.addSeparator()
        file_menu.addAction("E&xit", self.close)

        mail_menu = menubar.addMenu("&Mail")
        mail_menu.addAction("New Message", self._compose_new, "Ctrl+N")
        mail_menu.addAction("Reply", self._reply, "Ctrl+R")
        mail_menu.addAction("Reply All", self._reply_all, "Ctrl+Shift+R")
        mail_menu.addSeparator()
        mail_menu.addAction("Delete", self._delete_selected, "Delete")
        mail_menu.addAction("Mark as Unread", self._mark_unread)

        view_menu = menubar.addMenu("&View")
        view_menu.addAction("Refresh", self._refresh, "F5")

        help_menu = menubar.addMenu("&Help")
        help_menu.addAction("About 98Mail...", self._show_about)

    def _setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        self.action_new = toolbar.addAction(icon_mail_new(), "New Mail")
        self.action_new.triggered.connect(self._compose_new)
        self.action_new.setEnabled(False)

        toolbar.addSeparator()

        self.action_reply = toolbar.addAction(icon_reply(), "Reply")
        self.action_reply.triggered.connect(self._reply)
        self.action_reply.setEnabled(False)

        toolbar.addSeparator()

        self.action_delete = toolbar.addAction(icon_delete(), "Delete")
        self.action_delete.triggered.connect(self._delete_selected)
        self.action_delete.setEnabled(False)

        toolbar.addSeparator()

        self.action_refresh = toolbar.addAction(icon_refresh(), "Refresh")
        self.action_refresh.triggered.connect(self._refresh)
        self.action_refresh.setEnabled(False)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(0)

        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setChildrenCollapsible(False)

        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderLabel("Folders")
        self.folder_tree.setMinimumWidth(120)
        self.folder_tree.itemClicked.connect(self._on_folder_selected)
        main_splitter.addWidget(self.folder_tree)

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.setChildrenCollapsible(False)

        self.message_table = QTableWidget()
        self.message_table.setColumnCount(4)
        self.message_table.setHorizontalHeaderLabels(["", "From", "Subject", "Date"])
        self.message_table.horizontalHeader().setStretchLastSection(False)
        self.message_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.message_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.message_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.message_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.message_table.setColumnWidth(0, 24)
        self.message_table.setColumnWidth(1, 200)
        self.message_table.setColumnWidth(3, 150)
        self.message_table.verticalHeader().setVisible(False)
        self.message_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.message_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.message_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.message_table.setSortingEnabled(True)
        self.message_table.horizontalHeader().setSortIndicatorShown(True)
        self.message_table.cellClicked.connect(self._on_message_selected)
        self.message_table.cellDoubleClicked.connect(self._on_message_double_clicked)
        right_splitter.addWidget(self.message_table)

        preview_container = QWidget()
        preview_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        self.attachment_bar = QWidget()
        self.attachment_bar.setVisible(False)
        self.attachment_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        att_layout = QHBoxLayout(self.attachment_bar)
        att_layout.setContentsMargins(4, 2, 4, 2)
        att_layout.setSpacing(4)
        self.attachment_bar.setStyleSheet(
            "background-color: #c0c0c0; "
            "border-top: 1px solid #ffffff; "
            "border-bottom: 1px solid #808080;"
        )
        self.att_icon_label = QLabel()
        self.att_icon_label.setPixmap(icon_attach().pixmap(16, 16))
        att_layout.addWidget(self.att_icon_label)
        self.att_buttons_layout = att_layout
        preview_layout.addWidget(self.attachment_bar)

        self.preview_pane = QWebEngineView()
        self.preview_pane.setPage(RestrictedPage(self.preview_pane))
        self.preview_pane.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_pane.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, False)
        self.preview_pane.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
        self.preview_pane.settings().setAttribute(QWebEngineSettings.AutoLoadImages, False)
        self.preview_pane.setHtml("<body style='background:#ffffff;'></body>")
        preview_layout.addWidget(self.preview_pane, 1)

        right_splitter.addWidget(preview_container)

        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 2)
        right_splitter.setSizes([250, 300])
        main_splitter.addWidget(right_splitter)

        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([180, 700])
        main_layout.addWidget(main_splitter)

    def _setup_statusbar(self):
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.status_label = QLabel("Not connected")
        self.statusbar.addWidget(self.status_label)
        self.marquee = MarqueeLabel()
        self.marquee.setFixedWidth(180)
        self.statusbar.addWidget(self.marquee)
        self.message_count_label = QLabel("")
        self.statusbar.addPermanentWidget(self.message_count_label)

    # ─── Connection ───

    def _show_login(self):
        saved = _load_account()
        dlg = LoginDialog(self, saved)
        if dlg.exec() == QDialog.Accepted:
            account = dlg.get_account()
            if dlg.should_save():
                _save_account(account)
            self._connect(account)

    def set_client(self, client: MailClient):
        self.client = client
        self.status_label.setText(f"Connected to {client.account.imap_host}")
        self.action_new.setEnabled(True)
        self.action_refresh.setEnabled(True)
        self._poll_timer.start()
        self._load_folders()

    def _connect(self, account: MailAccount):
        self.status_label.setText("Connecting...")
        self.client = MailClient(account)

        try:
            self.client.connect_imap()
        except Exception as e:
            QMessageBox.critical(self, "Connection Failed", f"Could not connect to IMAP server:\n{e}")
            self.status_label.setText("Not connected")
            self.client = None
            return

        self.status_label.setText(f"Connected to {account.imap_host}")
        self.action_new.setEnabled(True)
        self.action_refresh.setEnabled(True)
        self._poll_timer.start()
        self._load_folders()

    def _disconnect(self):
        self._poll_timer.stop()
        if self.client:
            self.client.disconnect()
            self.client = None
        self.folder_tree.clear()
        self.message_table.setRowCount(0)
        self.preview_pane.setHtml("")
        self.messages.clear()
        self.action_new.setEnabled(False)
        self.action_reply.setEnabled(False)
        self.action_delete.setEnabled(False)
        self.action_refresh.setEnabled(False)
        self.status_label.setText("Not connected")
        self.message_count_label.setText("")

    def _poll_new_mail(self):
        if not self.client:
            return
        self._load_messages()

    # ─── Folders ───

    def _load_folders(self):
        if not self.client:
            return
        worker = FetchFoldersWorker(self.client)
        worker.finished.connect(self._on_folders_loaded)
        worker.error.connect(lambda e: self.status_label.setText(f"Error: {e}"))
        self._workers.append(worker)
        worker.start()

    def _on_folders_loaded(self, folders: list[str]):
        self.folder_tree.clear()

        folder_icon = icon_folder()

        sorted_folders = sorted(folders, key=lambda f: (0 if f.upper() == "INBOX" else 1, f))
        for folder_name in sorted_folders:
            item = QTreeWidgetItem([folder_name])
            item.setIcon(0, folder_icon)
            self.folder_tree.addTopLevelItem(item)
            if folder_name.upper() == "INBOX":
                self.folder_tree.setCurrentItem(item)

        self.current_folder = "INBOX"
        self._load_messages()

    # ─── Messages ───

    def _load_messages(self):
        if not self.client:
            return
        self.status_label.setText(f"Loading {self.current_folder}...")
        worker = FetchMessagesWorker(self.client, self.current_folder)
        worker.finished.connect(self._on_messages_loaded)
        worker.error.connect(lambda e: self.status_label.setText(f"Error: {e}"))
        self._workers.append(worker)
        worker.start()

    def _on_messages_loaded(self, messages: list[MailMessage]):
        self.messages = {msg.uid: msg for msg in messages}
        self.message_table.setSortingEnabled(False)
        self.message_table.setRowCount(len(messages))

        for row, msg in enumerate(messages):
            status_item = QTableWidgetItem("●" if not msg.seen else "")
            status_item.setTextAlignment(Qt.AlignCenter)
            status_item.setData(Qt.UserRole, msg.uid)
            if not msg.seen:
                status_item.setForeground(QColor("#000080"))
            self.message_table.setItem(row, 0, status_item)

            from_item = QTableWidgetItem(msg.sender)
            from_item.setData(Qt.UserRole, msg.uid)
            if not msg.seen:
                font = from_item.font()
                font.setBold(True)
                from_item.setFont(font)
            self.message_table.setItem(row, 1, from_item)

            subj_item = QTableWidgetItem(msg.subject)
            subj_item.setData(Qt.UserRole, msg.uid)
            if not msg.seen:
                font = subj_item.font()
                font.setBold(True)
                subj_item.setFont(font)
            self.message_table.setItem(row, 2, subj_item)

            date_item = _DateTableItem(msg.date)
            date_item.setData(Qt.UserRole, msg.uid)
            self.message_table.setItem(row, 3, date_item)

        self.message_table.setSortingEnabled(True)
        unread = sum(1 for m in messages if not m.seen)
        self.message_count_label.setText(f"{len(messages)} messages, {unread} unread")
        self.status_label.setText(f"{self.current_folder}")

        current_unread = {m.uid for m in messages if not m.seen}
        new_unread = current_unread - self._prev_unread_uids
        self._prev_unread_uids = current_unread

        if new_unread and self.current_folder.upper() == "INBOX":
            self._notification = NewMailNotification(len(new_unread), self)
            self._notification.show()
            self.marquee.start("You have new mail!")
            QTimer.singleShot(5000, self.marquee.stop)
            if self._new_mail_sound.source().isValid():
                self._new_mail_sound.setPosition(0)
                self._new_mail_sound.play()

    def _on_folder_selected(self, item: QTreeWidgetItem, column: int):
        folder = item.text(0)
        if folder != self.current_folder:
            self.current_folder = folder
            self.preview_pane.setHtml("")
            self.current_message = None
            self.action_reply.setEnabled(False)
            self.action_delete.setEnabled(False)
            self._load_messages()

    def _get_selected_uid(self) -> int | None:
        row = self.message_table.currentRow()
        if row < 0:
            return None
        item = self.message_table.item(row, 0)
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _on_message_selected(self, row: int, column: int):
        item = self.message_table.item(row, 0)
        if item is None:
            return
        uid = item.data(Qt.UserRole)
        if uid is None or uid not in self.messages:
            return
        self.action_reply.setEnabled(True)
        self.action_delete.setEnabled(True)

        self.status_label.setText("Loading message...")
        worker = FetchMessageWorker(self.client, uid, self.current_folder)
        worker.finished.connect(self._on_message_fetched)
        worker.error.connect(lambda e: self.status_label.setText(f"Error: {e}"))
        self._workers.append(worker)
        worker.start()

    def _on_message_fetched(self, msg: MailMessage):
        if msg is None:
            self.preview_pane.setHtml("<body>Failed to load message.</body>")
            return

        self.current_message = msg
        self._populate_attachment_bar(msg)
        header = self._build_header(msg)

        if msg.body_html:
            body = _sanitize_email_html(msg.body_html)
        elif msg.body_text:
            body = f"<pre style='font-family:Courier New,monospace; font-size:9pt; white-space:pre-wrap; margin:8px;'>{html.escape(msg.body_text)}</pre>"
        else:
            body = "<p style='margin:8px; color:#808080;'>(No content)</p>"

        downgraded = _downgrade_css(f"{header}{body}")
        self._render_email(downgraded, remote_images=False)

        if not msg.seen:
            self._mark_seen_async(msg.uid)

    def _render_email(self, content: str, remote_images: bool = False):
        img_src = "img-src * data: cid:"
        full_html = (
            "<html><head><meta charset='utf-8'>"
            "<meta http-equiv='Content-Security-Policy' "
            f"content=\"default-src 'none'; style-src 'unsafe-inline'; {img_src}; font-src 'none';\">"
            f"</head><body style='margin:0; padding:0;'>{content}</body></html>"
        )
        self.preview_pane.settings().setAttribute(
            QWebEngineSettings.AutoLoadImages, remote_images
        )
        self.preview_pane.setHtml(full_html)

    def _load_remote_images(self):
        if not self.current_message:
            return
        msg = self.current_message
        if msg.body_html:
            body = _sanitize_email_html(msg.body_html)
        elif msg.body_text:
            body = f"<pre style='font-family:Courier New,monospace; font-size:9pt; white-space:pre-wrap; margin:8px;'>{html.escape(msg.body_text)}</pre>"
        else:
            return
        header = self._build_header(msg)
        downgraded = _downgrade_css(f"{header}{body}")
        self._render_email(downgraded, remote_images=True)

        self.status_label.setText(self.current_folder)

    def _build_header(self, msg: MailMessage) -> str:
        header = (
            f"<div style='background:#c0c0c0; padding:4px 6px; margin:0; "
            f"font-family:MS Sans Serif,Tahoma,sans-serif; font-size:8pt; "
            f"border-bottom:1px solid #808080;'>"
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

    def _populate_attachment_bar(self, msg: MailMessage):
        layout = self.att_buttons_layout
        while layout.count() > 1:
            child = layout.takeAt(1)
            if child.widget():
                child.widget().deleteLater()

        has_content = False

        if msg.body_html:
            load_img_btn = QPushButton("Load Remote Images")
            load_img_btn.setMinimumWidth(0)
            load_img_btn.setStyleSheet("min-width: 0; padding: 2px 8px;")
            load_img_btn.clicked.connect(self._load_remote_images)
            layout.addWidget(load_img_btn)
            has_content = True

        for att in msg.attachments:
            btn = QPushButton(att["filename"])
            btn.setMinimumWidth(0)
            btn.setStyleSheet("min-width: 0; padding: 2px 8px;")
            btn.clicked.connect(lambda checked, a=att: self._save_attachment(a))
            layout.addWidget(btn)
            has_content = True

        if len(msg.attachments) > 1:
            save_all = QPushButton("Save All...")
            save_all.setMinimumWidth(0)
            save_all.setStyleSheet("min-width: 0; padding: 2px 8px;")
            save_all.clicked.connect(lambda: self._save_all_attachments(msg.attachments))
            layout.addWidget(save_all)

        layout.addStretch()
        self.attachment_bar.setVisible(has_content)

    def _save_attachment(self, att: dict):
        downloads = str(Path.home() / "Downloads")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Attachment", os.path.join(downloads, att["filename"])
        )
        if not path:
            return
        try:
            with open(path, "wb") as f:
                f.write(att["data"] or b"")
            self.status_label.setText(f"Saved: {os.path.basename(path)}")
        except Exception as e:
            QMessageBox.critical(self, "98Mail", f"Failed to save:\n{e}")

    def _save_all_attachments(self, attachments: list[dict]):
        downloads = str(Path.home() / "Downloads")
        folder = QFileDialog.getExistingDirectory(self, "Save All Attachments To", downloads)
        if not folder:
            return
        saved = 0
        for att in attachments:
            try:
                path = os.path.join(folder, att["filename"])
                with open(path, "wb") as f:
                    f.write(att["data"] or b"")
                saved += 1
            except Exception:
                pass
        self.status_label.setText(f"Saved {saved} attachment(s)")

    def _mark_seen_async(self, uid: int):
        class _W(QThread):
            def __init__(s, client, uid, folder):
                super().__init__()
                s.client = client
                s.uid = uid
                s.folder = folder
            def run(s):
                try:
                    s.client.mark_seen(s.uid, s.folder)
                except Exception:
                    pass

        worker = _W(self.client, uid, self.current_folder)
        worker.finished.connect(lambda: self._on_mark_seen_done(uid))
        self._workers.append(worker)
        worker.start()

    def _on_mark_seen_done(self, uid: int):
        if uid in self.messages:
            self.messages[uid].seen = True
        for row in range(self.message_table.rowCount()):
            item = self.message_table.item(row, 0)
            if item and item.data(Qt.UserRole) == uid:
                item.setText("")
                for col in range(1, 4):
                    cell = self.message_table.item(row, col)
                    if cell:
                        font = cell.font()
                        font.setBold(False)
                        cell.setFont(font)
                break

    def _on_message_double_clicked(self, row: int, column: int):
        self._on_message_selected(row, column)

    # ─── Actions ───

    def _compose_new(self):
        if not self.client:
            return
        dlg = ComposeWindow(self.client, self)
        dlg.exec()

    def _reply(self):
        if not self.client or not self.current_message:
            return
        dlg = ComposeWindow(self.client, self, reply_to=self.current_message)
        dlg.exec()

    def _reply_all(self):
        if not self.client or not self.current_message:
            return
        dlg = ComposeWindow(self.client, self, reply_to=self.current_message, reply_all=True)
        dlg.exec()

    def _delete_selected(self):
        if not self.client:
            return
        uid = self._get_selected_uid()
        if uid is None or uid not in self.messages:
            return
        msg = self.messages[uid]
        reply = QMessageBox.question(
            self, "98Mail",
            f"Delete this message?\n\n{msg.subject}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        row = self.message_table.currentRow()
        self._delete_anim = DeleteAnimation(self)
        self._delete_anim.show()
        worker = DeleteMessageWorker(self.client, uid, self.current_folder)
        worker.finished.connect(lambda: self._on_deleted(row, uid))
        worker.error.connect(lambda e: QMessageBox.critical(self, "Error", f"Delete failed:\n{e}"))
        self._workers.append(worker)
        worker.start()

    def _on_deleted(self, row: int, uid: int):
        if hasattr(self, "_delete_anim") and self._delete_anim:
            self._delete_anim.close()
        self.message_table.removeRow(row)
        self.messages.pop(uid, None)
        self.preview_pane.setHtml("")
        self.current_message = None
        self.status_label.setText("Message deleted")

    def _mark_unread(self):
        if not self.client or not self.current_message:
            return
        uid = self.current_message.uid
        try:
            self.client.mark_unseen(uid, self.current_folder)
            if uid in self.messages:
                self.messages[uid].seen = False
            row = self.message_table.currentRow()
            if row >= 0:
                self.message_table.item(row, 0).setText("●")
                self.message_table.item(row, 0).setForeground(QColor("#000080"))
                for col in range(1, 4):
                    item = self.message_table.item(row, col)
                    if item:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
        except Exception as e:
            self.status_label.setText(f"Error: {e}")

    def _refresh(self):
        if not self.client:
            return
        self._load_messages()

    def _show_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def closeEvent(self, event):
        if self.client:
            self.client.disconnect()
        event.accept()


# ─── Config persistence ───

def _save_account(account: MailAccount):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "imap_host": account.imap_host,
        "imap_port": account.imap_port,
        "smtp_host": account.smtp_host,
        "smtp_port": account.smtp_port,
        "username": account.username,
        "use_ssl": account.use_ssl,
    }
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        keyring.set_password(KEYRING_SERVICE, account.username, account.password)
    except Exception:
        pass


def _load_account() -> dict | None:
    if not CONFIG_FILE.exists():
        return None
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if "password" in data:
        try:
            keyring.set_password(KEYRING_SERVICE, data["username"], data["password"])
        except Exception:
            pass
        del data["password"]
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        data["password"] = keyring.get_password(KEYRING_SERVICE, data["username"]) or ""
    except Exception:
        data["password"] = ""
    return data


# ─── Entry Point ───

def main():
    app = QApplication(sys.argv)
    app.setStyle("Windows")
    app.setStyleSheet(get_stylesheet())

    saved = _load_account()
    splash = SplashScreen(saved)
    splash.exec()

    window = MainWindow()
    window.show()

    if splash._client:
        QTimer.singleShot(100, lambda: window.set_client(splash._client))
    else:
        if splash._connect_error and saved:
            QTimer.singleShot(200, lambda: (
                QMessageBox.warning(window, "98Mail", f"Auto-login failed:\n{splash._connect_error}"),
                window._show_login(),
            ))
        else:
            QTimer.singleShot(200, lambda: window._show_login())

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
