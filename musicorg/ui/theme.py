"""Application-wide visual theme styling."""

from __future__ import annotations

APP_STYLESHEET = """
QWidget {
    background-color: #141518;
    color: #dcdfe4;
    font-family: "Segoe UI", "Noto Sans", sans-serif;
    font-size: 10pt;
}

QMainWindow {
    background-color: #0c0e12;
}

/* ── Menu Bar ── */

QMenuBar {
    background-color: #0c0e12;
    color: #c9d0db;
    border-bottom: 1px solid #222730;
}

QMenuBar::item {
    padding: 6px 10px;
    spacing: 4px;
    background: transparent;
}

QMenuBar::item:selected {
    background-color: #252a35;
    color: #ffffff;
}

QMenu {
    background-color: #111316;
    border: 1px solid #222730;
    padding: 4px;
}

QMenu::item {
    padding: 6px 22px 6px 10px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #252a35;
}

/* ── Sidebar ── */

#Sidebar {
    background-color: #101216;
    border-right: 1px solid #222730;
}

#SidebarBrand {
    background-color: transparent;
    color: #d4a44a;
    font-size: 14pt;
    font-weight: 700;
    letter-spacing: 1px;
    border-bottom: 1px solid #222730;
}

#SectionHeader {
    background-color: transparent;
    color: #7a8494;
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
}

#NavItem {
    background-color: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: #7a8494;
}

#NavItem:hover {
    background-color: #191c21;
    color: #dcdfe4;
}

#NavItem[selected="true"] {
    background-color: #191c21;
    border-left: 3px solid #d4a44a;
    color: #dcdfe4;
}

#NavItem #NavIcon {
    background-color: transparent;
    font-size: 13pt;
}

#NavItem #NavLabel {
    background-color: transparent;
    font-weight: 600;
    font-size: 10pt;
}

/* ── Status Strip ── */

#StatusStrip {
    background-color: #0c0e12;
    border-top: 1px solid #222730;
}

#StatusStrip QLabel {
    background-color: transparent;
}

#StatusMessage {
    color: #7a8494;
    font-size: 9pt;
}

#StatusDetail {
    color: #7a8494;
    font-size: 9pt;
}

#StatusMuted {
    color: #4a5260;
    font-size: 8pt;
}

#StatusStrip QProgressBar {
    border: 1px solid #222730;
    border-radius: 4px;
    min-height: 10px;
    max-height: 10px;
    background-color: #111316;
}

#StatusStrip QProgressBar::chunk {
    background-color: #d4a44a;
    border-radius: 4px;
}

/* ── Group Box ── */

QGroupBox {
    border: none;
    border-top: 1px solid #222730;
    margin-top: 7px;
    padding-top: 7px;
    font-weight: 600;
    color: #dcdfe4;
    background-color: transparent;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #d4a44a;
    text-transform: uppercase;
    font-size: 9pt;
    letter-spacing: 0.5px;
}

/* ── Labels ── */

QLabel {
    color: #dcdfe4;
}

/* ── Inputs ── */

QLineEdit, QSpinBox {
    background-color: #111316;
    border: 1px solid #222730;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #252a35;
    color: #dcdfe4;
}

QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #d4a44a;
}

QComboBox {
    background-color: #111316;
    border: 1px solid #222730;
    border-radius: 6px;
    padding: 5px 8px;
    color: #dcdfe4;
}

QComboBox:focus {
    border: 1px solid #d4a44a;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #111316;
    border: 1px solid #222730;
    selection-background-color: #252a35;
}

QCheckBox {
    background-color: transparent;
    spacing: 6px;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #222730;
    border-radius: 3px;
    background-color: #111316;
}

QCheckBox::indicator:checked {
    background-color: #d4a44a;
    border-color: #d4a44a;
}

/* ── Buttons ── */

QPushButton {
    background-color: #1e2228;
    color: #dcdfe4;
    border: 1px solid #222730;
    border-radius: 6px;
    padding: 5px 11px;
    min-height: 18px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #252a35;
}

QPushButton:pressed {
    background-color: #191c21;
}

QPushButton:disabled {
    background-color: #191c21;
    color: #4a5260;
    border-color: #222730;
}

QPushButton[role="accent"] {
    background-color: #d4a44a;
    color: #0c0e12;
    border: 1px solid #d4a44a;
}

QPushButton[role="accent"]:hover {
    background-color: #e0b45a;
}

QPushButton[role="accent"]:pressed {
    background-color: #c09440;
}

QPushButton[role="accent"]:disabled {
    background-color: #5a5040;
    color: #8a8070;
    border: 1px solid #5a5040;
}

/* ── Header View ── */

QHeaderView::section {
    background-color: #111316;
    color: #7a8494;
    border: 0;
    border-bottom: 1px solid #222730;
    padding: 5px 7px;
    font-weight: 600;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

/* ── Tables ── */

QTableView, QTableWidget {
    background-color: #111316;
    alternate-background-color: #141518;
    border: none;
    gridline-color: transparent;
    selection-background-color: #252a35;
    selection-color: #f8fbff;
}

QTableView::item, QTableWidget::item {
    padding: 3px 5px;
}

/* ── List Widget ── */

QListWidget {
    background-color: #111316;
    alternate-background-color: #141518;
    border: none;
    border-radius: 0;
}

QListWidget::item {
    padding: 6px 9px;
    border-bottom: 1px solid #1a1d22;
    border-left: 3px solid transparent;
}

QListWidget::item:selected {
    background-color: #252a35;
    color: #f8fbff;
    border-left: 3px solid #d4a44a;
}

QListWidget::item:hover:!selected {
    background-color: #191c21;
}

/* ── Item Views (shared) ── */

QAbstractItemView::item:hover {
    background-color: #191c21;
}

/* ── Progress Bar ── */

QProgressBar {
    border: 1px solid #222730;
    border-radius: 6px;
    min-height: 12px;
    max-height: 12px;
    text-align: center;
    background-color: #111316;
    color: #dcdfe4;
}

QProgressBar::chunk {
    background-color: #d4a44a;
    border-radius: 6px;
}

/* ── Splitter ── */

QSplitter::handle {
    background-color: #222730;
    width: 2px;
    height: 2px;
}

/* ── Scrollbars ── */

QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #2a2f38;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #3a4050;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 2px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background: #2a2f38;
    min-width: 24px;
    border-radius: 4px;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* ── Form Layout Labels ── */

QFormLayout QLabel {
    background-color: transparent;
}

/* ── Album Card ── */

#AlbumCard {
    background-color: #161920;
    border: 1px solid #222730;
    border-radius: 8px;
}

#AlbumCard:hover {
    border-color: #2a3040;
    background-color: #1a1e26;
}

#AlbumCover {
    border: 1px solid #222730;
    border-radius: 4px;
    background-color: #111316;
    color: #4a5260;
    font-size: 8pt;
}

#AlbumTitle {
    background-color: transparent;
    color: #f0f2f5;
    font-size: 12pt;
    font-weight: 700;
}

#AlbumYear {
    background-color: transparent;
    color: #7a8494;
    font-size: 10pt;
}

#AlbumMeta {
    background-color: transparent;
    color: #7a8494;
    font-size: 9pt;
}

#DiscHeader {
    background-color: transparent;
    color: #7a8494;
    font-size: 9pt;
    font-weight: 600;
    padding: 6px 0 2px 0;
    border-top: 1px solid #222730;
    margin-top: 4px;
}

/* ── Track Row ── */

#TrackRow {
    background-color: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0;
    padding: 0;
}

#TrackRow:hover {
    background-color: #1e2228;
}

#TrackRow[selected="true"] {
    background-color: #1e2530;
    border-left: 3px solid #d4a44a;
}

#TrackNumber {
    background-color: transparent;
    color: #4a5260;
    font-size: 9pt;
}

#TrackTitle {
    background-color: transparent;
    color: #dcdfe4;
    font-size: 9pt;
}

#TrackDuration {
    background-color: transparent;
    color: #7a8494;
    font-size: 9pt;
}

/* ── Alphabet Bar ── */

#AlphabetBar {
    background-color: transparent;
}

#AlphabetBar QPushButton {
    background-color: transparent;
    border: none;
    border-radius: 3px;
    color: #7a8494;
    font-size: 8pt;
    font-weight: 600;
    padding: 2px;
    min-height: 18px;
    min-width: 18px;
}

#AlphabetBar QPushButton:hover {
    background-color: #252a35;
    color: #dcdfe4;
}

#AlphabetBar QPushButton:disabled {
    color: #2a2f38;
    background-color: transparent;
}

#AlphabetBar QPushButton[active="true"] {
    background-color: #d4a44a;
    color: #0c0e12;
}

/* ── Album Browser ── */

#AlbumBrowser {
    background-color: transparent;
    border: none;
}

#AlbumBrowserInner {
    background-color: transparent;
}

/* ── Tree Widget (Duplicates) ── */

QTreeWidget {
    background-color: #111316;
    alternate-background-color: #141518;
    border: none;
    selection-background-color: #252a35;
    selection-color: #f8fbff;
}

QTreeWidget::item {
    padding: 3px 5px;
}

QTreeWidget QHeaderView::section {
    background-color: #111316;
    color: #7a8494;
    border: 0;
    border-bottom: 1px solid #222730;
    padding: 5px 7px;
    font-weight: 600;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

#DuplicateKeepLabel {
    color: #4CAF50;
}

#DuplicateDeleteLabel {
    color: #F44336;
}

#DuplicateGroupHeader {
    color: #d4a44a;
}
"""
