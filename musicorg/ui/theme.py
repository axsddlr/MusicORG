"""Application-wide visual theme styling."""

from __future__ import annotations

APP_STYLESHEET = """
QWidget {
    background-color: #16181d;
    color: #d8dde6;
    font-family: "Segoe UI", "Noto Sans", sans-serif;
    font-size: 10pt;
}

QMainWindow {
    background-color: #0f1115;
}

QMenuBar {
    background-color: #0e1014;
    color: #c9d0db;
    border-bottom: 1px solid #242932;
}

QMenuBar::item {
    padding: 6px 10px;
    spacing: 4px;
    background: transparent;
}

QMenuBar::item:selected {
    background-color: #242a35;
    color: #ffffff;
}

QMenu {
    background-color: #13171d;
    border: 1px solid #2a303b;
    padding: 4px;
}

QMenu::item {
    padding: 6px 22px 6px 10px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #2f3948;
}

QStatusBar {
    background-color: #10141a;
    color: #92a0b1;
    border-top: 1px solid #242932;
}

QTabWidget::pane {
    border: 0;
    background-color: #16181d;
}

QTabBar::tab {
    background-color: #12151a;
    color: #8e99aa;
    border: 1px solid #232833;
    border-bottom: none;
    padding: 8px 16px;
    margin-right: 2px;
    text-transform: uppercase;
    font-weight: 600;
    letter-spacing: 0.4px;
}

QTabBar::tab:selected {
    background-color: #1f2530;
    color: #f1f3f6;
    border-top: 2px solid #f0b454;
}

QTabBar::tab:hover:!selected {
    color: #cdd3dc;
}

QGroupBox {
    border: 1px solid #2a313d;
    border-radius: 8px;
    margin-top: 7px;
    padding-top: 7px;
    font-weight: 600;
    color: #dce2ec;
    background-color: #1a1f27;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #f2b84b;
}

QLabel {
    color: #cdd4df;
}

QLineEdit, QSpinBox {
    background-color: #11151a;
    border: 1px solid #313947;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: #3a4a63;
    color: #e4e9f2;
}

QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #f2b84b;
}

QComboBox {
    background-color: #11151a;
    border: 1px solid #313947;
    border-radius: 6px;
    padding: 5px 8px;
    color: #e4e9f2;
}

QComboBox:focus {
    border: 1px solid #f2b84b;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #151a21;
    border: 1px solid #2e3643;
    selection-background-color: #2f3b4c;
}

QPushButton {
    background-color: #2e3642;
    color: #e7edf7;
    border: 1px solid #434f60;
    border-radius: 6px;
    padding: 5px 11px;
    min-height: 18px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #394556;
}

QPushButton:pressed {
    background-color: #243040;
}

QPushButton:disabled {
    background-color: #262b34;
    color: #707d90;
    border-color: #303844;
}

QPushButton[role="accent"] {
    background-color: #f0b454;
    color: #12161e;
    border: 1px solid #f7c57a;
}

QPushButton[role="accent"]:hover {
    background-color: #f8c67a;
}

QPushButton[role="accent"]:pressed {
    background-color: #dda148;
}

QPushButton[role="accent"]:disabled {
    background-color: #6f624b;
    color: #d5d8dd;
    border: 1px solid #7b6e54;
}

QHeaderView::section {
    background-color: #11151b;
    color: #a6b1c0;
    border: 0;
    border-right: 1px solid #27303c;
    border-bottom: 1px solid #27303c;
    padding: 5px 7px;
    font-weight: 600;
}

QTableView, QTableWidget {
    background-color: #12161c;
    alternate-background-color: #181d25;
    border: 1px solid #2a313d;
    border-radius: 8px;
    gridline-color: #242b36;
    selection-background-color: #2f3b4c;
    selection-color: #f8fbff;
}

QListWidget {
    background-color: #12161c;
    alternate-background-color: #181d25;
    border: 1px solid #2a313d;
    border-radius: 8px;
}

QListWidget::item {
    padding: 6px 9px;
    border-bottom: 1px solid #222933;
}

QListWidget::item:selected {
    background-color: #2f3b4c;
    color: #f8fbff;
}

QListWidget::item:hover:!selected {
    background-color: #212834;
}

QTableView::item, QTableWidget::item {
    padding: 3px 5px;
}

QAbstractItemView::item:hover {
    background-color: #212834;
}

QProgressBar {
    border: 1px solid #374153;
    border-radius: 6px;
    min-height: 12px;
    max-height: 12px;
    text-align: center;
    background-color: #0f1319;
    color: #d8deea;
}

QProgressBar::chunk {
    background-color: #5d8bff;
    border-radius: 6px;
}

QSplitter::handle {
    background-color: #242b35;
    width: 2px;
    height: 2px;
}

QScrollBar:vertical {
    background: #11151a;
    width: 12px;
    margin: 2px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background: #394353;
    min-height: 24px;
    border-radius: 6px;
}

QScrollBar::handle:vertical:hover {
    background: #4a5770;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: #11151a;
    height: 12px;
    margin: 2px;
    border-radius: 6px;
}

QScrollBar::handle:horizontal {
    background: #394353;
    min-width: 24px;
    border-radius: 6px;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
"""
