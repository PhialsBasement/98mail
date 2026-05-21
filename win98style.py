import tempfile
import os

from PySide6.QtGui import QPixmap, QPainter, QColor, QPen
from PySide6.QtCore import Qt

_STYLE_DIR = tempfile.mkdtemp(prefix="98mail_style_")


def _generate_checkbox_images():
    size = 13

    # unchecked
    pm = QPixmap(size, size)
    pm.fill(QColor("#ffffff"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, False)
    # outer border: top/left dark, bottom/right light
    p.setPen(QPen(QColor("#808080"), 1))
    p.drawLine(0, 0, size - 2, 0)
    p.drawLine(0, 0, 0, size - 2)
    p.setPen(QPen(QColor("#404040"), 1))
    p.drawLine(1, 1, size - 3, 1)
    p.drawLine(1, 1, 1, size - 3)
    p.setPen(QPen(QColor("#ffffff"), 1))
    p.drawLine(0, size - 1, size - 1, size - 1)
    p.drawLine(size - 1, 0, size - 1, size - 1)
    p.setPen(QPen(QColor("#dfdfdf"), 1))
    p.drawLine(1, size - 2, size - 2, size - 2)
    p.drawLine(size - 2, 1, size - 2, size - 2)
    p.end()

    unchecked_path = os.path.join(_STYLE_DIR, "cb_unchecked.png")
    pm.save(unchecked_path)

    # checked: same border + checkmark
    pm2 = pm.copy()
    p2 = QPainter(pm2)
    p2.setRenderHint(QPainter.Antialiasing, False)
    p2.setPen(QPen(QColor("#000000"), 1))
    # draw a classic Win98 checkmark pixel by pixel
    check = [
        (3, 5), (3, 6), (3, 7),
        (4, 6), (4, 7), (4, 8),
        (5, 7), (5, 8), (5, 9),
        (6, 6), (6, 7), (6, 8),
        (7, 5), (7, 6), (7, 7),
        (8, 4), (8, 5), (8, 6),
        (9, 3), (9, 4), (9, 5),
        (10, 2), (10, 3), (10, 4),
    ]
    for x, y in check:
        p2.drawPoint(x, y)
    p2.end()

    checked_path = os.path.join(_STYLE_DIR, "cb_checked.png")
    pm2.save(checked_path)

    return unchecked_path, checked_path


def get_stylesheet():
    unchecked, checked = _generate_checkbox_images()
    unchecked = unchecked.replace("\\", "/")
    checked = checked.replace("\\", "/")
    s = _STYLESHEET_TEMPLATE
    s = s.replace("{cb_unchecked}", unchecked)
    s = s.replace("{cb_checked}", checked)
    return s


_STYLESHEET_TEMPLATE = """
/* ===== Global ===== */
* {
    font-family: "MS Sans Serif", "Microsoft Sans Serif", "Fixedsys";
    font-size: 8pt;
    color: #000000;
}

QMainWindow, QDialog {
    background-color: #c0c0c0;
}

/* ===== Raised border (button/toolbar look) ===== */
/* Win98 raised: top/left white, bottom/right #404040,
   inner top/left #dfdfdf, inner bottom/right #808080 */

/* ===== Sunken border (input fields) ===== */
/* Win98 sunken: top/left #808080, bottom/right #ffffff,
   inner top/left #404040, inner bottom/right #dfdfdf */

/* ===== Menu Bar ===== */
QMenuBar {
    background-color: #c0c0c0;
    border-bottom: 1px solid #808080;
    padding: 0px;
    spacing: 0px;
}

QMenuBar::item {
    background: transparent;
    padding: 3px 6px;
    margin: 0px;
}

QMenuBar::item:selected {
    background-color: #000080;
    color: #ffffff;
}

QMenu {
    background-color: #c0c0c0;
    border-top: 1px solid #ffffff;
    border-left: 1px solid #ffffff;
    border-right: 1px solid #404040;
    border-bottom: 1px solid #404040;
    padding: 2px;
}

QMenu::item {
    padding: 2px 20px 2px 24px;
    background: transparent;
}

QMenu::item:selected {
    background-color: #000080;
    color: #ffffff;
}

QMenu::separator {
    height: 1px;
    background: #808080;
    margin: 2px 2px;
    border-bottom: 1px solid #ffffff;
}

/* ===== Toolbar ===== */
QToolBar {
    background-color: #c0c0c0;
    border-top: 1px solid #ffffff;
    border-bottom: 1px solid #808080;
    spacing: 0px;
    padding: 1px 2px;
    margin: 0px;
}

QToolBar::separator {
    width: 2px;
    margin: 2px 3px;
    border-left: 1px solid #808080;
    border-right: 1px solid #ffffff;
}

QToolButton {
    background-color: #c0c0c0;
    border: 1px solid #c0c0c0;
    padding: 3px 6px;
    margin: 1px;
    min-width: 40px;
}

QToolButton:hover {
    border-top: 1px solid #ffffff;
    border-left: 1px solid #ffffff;
    border-bottom: 1px solid #404040;
    border-right: 1px solid #404040;
}

QToolButton:pressed {
    border-top: 1px solid #404040;
    border-left: 1px solid #404040;
    border-bottom: 1px solid #ffffff;
    border-right: 1px solid #ffffff;
    padding-left: 7px;
    padding-top: 4px;
}

/* ===== Buttons ===== */
QPushButton {
    background-color: #c0c0c0;
    border-top: 2px solid #ffffff;
    border-left: 2px solid #ffffff;
    border-bottom: 2px solid #404040;
    border-right: 2px solid #404040;
    padding: 3px 12px;
    min-width: 75px;
    min-height: 18px;
}

QPushButton:hover {
    background-color: #c0c0c0;
}

QPushButton:pressed {
    border-top: 2px solid #404040;
    border-left: 2px solid #404040;
    border-bottom: 2px solid #ffffff;
    border-right: 2px solid #ffffff;
    padding-left: 13px;
    padding-top: 4px;
}

QPushButton:focus {
    outline: 1px dotted #000000;
    outline-offset: -4px;
}

QPushButton:disabled {
    color: #808080;
}

/* ===== Tree View (Folder List) ===== */
QTreeView, QTreeWidget {
    background-color: #ffffff;
    border-top: 2px solid #808080;
    border-left: 2px solid #808080;
    border-bottom: 2px solid #ffffff;
    border-right: 2px solid #ffffff;
    selection-background-color: #000080;
    selection-color: #ffffff;
    outline: none;
}

QTreeView::item {
    padding: 1px 0;
    min-height: 16px;
}

QTreeView::item:selected {
    background-color: #000080;
    color: #ffffff;
}

QTreeView::item:hover:!selected {
    background: transparent;
}

QHeaderView {
    background-color: #c0c0c0;
}

/* ===== Table View (Message List) ===== */
QTableView, QTableWidget {
    background-color: #ffffff;
    border-top: 2px solid #808080;
    border-left: 2px solid #808080;
    border-bottom: 2px solid #ffffff;
    border-right: 2px solid #ffffff;
    selection-background-color: #000080;
    selection-color: #ffffff;
    gridline-color: #c0c0c0;
    outline: none;
}

QTableView::item {
    padding: 1px 3px;
    border: none;
}

QTableView::item:selected {
    background-color: #000080;
    color: #ffffff;
}

QHeaderView::section {
    background-color: #c0c0c0;
    border-top: 1px solid #ffffff;
    border-left: 1px solid #ffffff;
    border-bottom: 1px solid #404040;
    border-right: 1px solid #404040;
    padding: 2px 4px;
    font-weight: bold;
}

QHeaderView::section:pressed {
    border-top: 1px solid #404040;
    border-left: 1px solid #404040;
    border-bottom: 1px solid #ffffff;
    border-right: 1px solid #ffffff;
}

/* ===== Scroll Bars ===== */
QScrollBar:vertical {
    background: #c0c0c0;
    width: 16px;
    margin: 16px 0;
    border: none;
}

QScrollBar::handle:vertical {
    background: #c0c0c0;
    border-top: 1px solid #ffffff;
    border-left: 1px solid #ffffff;
    border-bottom: 1px solid #404040;
    border-right: 1px solid #404040;
    min-height: 16px;
}

QScrollBar::add-line:vertical {
    background: #c0c0c0;
    border-top: 1px solid #ffffff;
    border-left: 1px solid #ffffff;
    border-bottom: 1px solid #404040;
    border-right: 1px solid #404040;
    height: 16px;
    subcontrol-position: bottom;
    subcontrol-origin: margin;
}

QScrollBar::sub-line:vertical {
    background: #c0c0c0;
    border-top: 1px solid #ffffff;
    border-left: 1px solid #ffffff;
    border-bottom: 1px solid #404040;
    border-right: 1px solid #404040;
    height: 16px;
    subcontrol-position: top;
    subcontrol-origin: margin;
}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: #c0c0c0;
}

QScrollBar:horizontal {
    background: #c0c0c0;
    height: 16px;
    margin: 0 16px;
    border: none;
}

QScrollBar::handle:horizontal {
    background: #c0c0c0;
    border-top: 1px solid #ffffff;
    border-left: 1px solid #ffffff;
    border-bottom: 1px solid #404040;
    border-right: 1px solid #404040;
    min-width: 16px;
}

QScrollBar::add-line:horizontal {
    background: #c0c0c0;
    border-top: 1px solid #ffffff;
    border-left: 1px solid #ffffff;
    border-bottom: 1px solid #404040;
    border-right: 1px solid #404040;
    width: 16px;
    subcontrol-position: right;
    subcontrol-origin: margin;
}

QScrollBar::sub-line:horizontal {
    background: #c0c0c0;
    border-top: 1px solid #ffffff;
    border-left: 1px solid #ffffff;
    border-bottom: 1px solid #404040;
    border-right: 1px solid #404040;
    width: 16px;
    subcontrol-position: left;
    subcontrol-origin: margin;
}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: #c0c0c0;
}

/* ===== Text Edit / Plain Text ===== */
QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    border-top: 2px solid #808080;
    border-left: 2px solid #808080;
    border-bottom: 2px solid #ffffff;
    border-right: 2px solid #ffffff;
    selection-background-color: #000080;
    selection-color: #ffffff;
}

/* ===== Line Edit ===== */
QLineEdit {
    background-color: #ffffff;
    border-top: 2px solid #808080;
    border-left: 2px solid #808080;
    border-bottom: 2px solid #ffffff;
    border-right: 2px solid #ffffff;
    padding: 1px 2px;
    selection-background-color: #000080;
    selection-color: #ffffff;
    min-height: 16px;
}

/* ===== Spin Box ===== */
QSpinBox {
    background-color: #ffffff;
    border-top: 2px solid #808080;
    border-left: 2px solid #808080;
    border-bottom: 2px solid #ffffff;
    border-right: 2px solid #ffffff;
    padding: 1px 2px;
    min-height: 16px;
}

QSpinBox::up-button, QSpinBox::down-button {
    background: #c0c0c0;
    border-top: 1px solid #ffffff;
    border-left: 1px solid #ffffff;
    border-bottom: 1px solid #404040;
    border-right: 1px solid #404040;
    width: 14px;
}

QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {
    border-top: 1px solid #404040;
    border-left: 1px solid #404040;
    border-bottom: 1px solid #ffffff;
    border-right: 1px solid #ffffff;
}

/* ===== Labels ===== */
QLabel {
    background: transparent;
    border: none;
}

/* ===== Group Box ===== */
QGroupBox {
    border-top: 1px solid #808080;
    border-left: 1px solid #808080;
    border-bottom: 1px solid #ffffff;
    border-right: 1px solid #ffffff;
    margin-top: 8px;
    padding-top: 8px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 3px;
    background-color: #c0c0c0;
}

/* ===== Tab Widget ===== */
QTabWidget::pane {
    border-top: 2px solid #ffffff;
    border-left: 2px solid #ffffff;
    border-bottom: 2px solid #404040;
    border-right: 2px solid #404040;
    background-color: #c0c0c0;
}

QTabBar::tab {
    background-color: #c0c0c0;
    border-top: 2px solid #ffffff;
    border-left: 2px solid #ffffff;
    border-right: 2px solid #404040;
    border-bottom: none;
    padding: 3px 10px;
    margin-right: 1px;
}

QTabBar::tab:selected {
    background-color: #c0c0c0;
    margin-bottom: -2px;
    padding-bottom: 5px;
}

/* ===== Splitter ===== */
QSplitter::handle {
    background-color: #c0c0c0;
    width: 4px;
    height: 4px;
}

/* ===== Status Bar ===== */
QStatusBar {
    background-color: #c0c0c0;
    min-height: 20px;
}

QStatusBar::item {
    border-top: 1px solid #808080;
    border-left: 1px solid #808080;
    border-bottom: 1px solid #ffffff;
    border-right: 1px solid #ffffff;
}

/* ===== Combo Box ===== */
QComboBox {
    background-color: #ffffff;
    border-top: 2px solid #808080;
    border-left: 2px solid #808080;
    border-bottom: 2px solid #ffffff;
    border-right: 2px solid #ffffff;
    padding: 1px 2px;
    min-height: 16px;
}

QComboBox::drop-down {
    background: #c0c0c0;
    border-top: 1px solid #ffffff;
    border-left: 1px solid #ffffff;
    border-bottom: 1px solid #404040;
    border-right: 1px solid #404040;
    width: 16px;
}

QComboBox::drop-down:pressed {
    border-top: 1px solid #404040;
    border-left: 1px solid #404040;
    border-bottom: 1px solid #ffffff;
    border-right: 1px solid #ffffff;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #000000;
    selection-background-color: #000080;
    selection-color: #ffffff;
}

/* ===== Check Box ===== */
QCheckBox {
    spacing: 4px;
    background: transparent;
}

QCheckBox::indicator {
    width: 13px;
    height: 13px;
    image: url({cb_unchecked});
}

QCheckBox::indicator:checked {
    image: url({cb_checked});
}

/* ===== Progress Bar ===== */
QProgressBar {
    border-top: 2px solid #808080;
    border-left: 2px solid #808080;
    border-bottom: 2px solid #ffffff;
    border-right: 2px solid #ffffff;
    background: #ffffff;
    text-align: center;
    height: 16px;
}

QProgressBar::chunk {
    background-color: #000080;
}

/* ===== Message Box ===== */
QMessageBox {
    background-color: #c0c0c0;
}

QMessageBox QLabel {
    font-size: 8pt;
}
"""
