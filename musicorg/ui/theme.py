"""Application-wide visual theme styling."""

from __future__ import annotations

from typing import Mapping

# Theme tokens are centralized to keep visual decisions consistent.
TOKENS = {
    "canvas": "#0e1015",
    "surface_0": "#12151c",
    "surface_1": "#171b24",
    "surface_2": "#1d2230",
    "surface_3": "#252c3d",
    "line_soft": "#2a3143",
    "line_strong": "#36405a",
    "text_primary": "#e6ebf5",
    "text_muted": "#93a0b8",
    "text_dim": "#6f7b92",
    "accent": "#d4a44a",
    "accent_hover": "#e6b962",
    "accent_press": "#ba8b35",
    "accent_subtle": "#4e452f",
    "danger": "#d76868",
    "success": "#5fb484",
    "focus_ring": "#8cb6ff",
}

FONTS = {
    "body": '"Noto Sans", "Segoe UI Variable Text", "Segoe UI", sans-serif',
    "display": '"Bahnschrift", "Segoe UI Semibold", "Segoe UI", sans-serif',
    "icon": '"Segoe Fluent Icons", "Segoe MDL2 Assets", "Segoe UI Symbol", sans-serif',
}

DEFAULT_TOKENS = dict(TOKENS)
DEFAULT_FONTS = dict(FONTS)

BASE_STYLES = f"""
QWidget {{
    background-color: {TOKENS["surface_0"]};
    color: {TOKENS["text_primary"]};
    font-family: {FONTS["body"]};
    font-size: 10pt;
}}

QMainWindow {{
    background-color: {TOKENS["canvas"]};
}}

QLabel {{
    color: {TOKENS["text_primary"]};
    background-color: transparent;
}}

#StatusMuted {{
    color: {TOKENS["text_dim"]};
    font-size: 8pt;
}}

#StatusDetail {{
    color: {TOKENS["text_muted"]};
    font-size: 9pt;
}}

#StatusMessage {{
    color: {TOKENS["text_muted"]};
    font-size: 9pt;
}}
"""

MENU_STYLES = f"""
QMenuBar {{
    background-color: {TOKENS["canvas"]};
    color: {TOKENS["text_muted"]};
    border-bottom: 1px solid {TOKENS["line_soft"]};
}}

QMenuBar::item {{
    padding: 6px 10px;
    background: transparent;
}}

QMenuBar::item:selected {{
    background-color: {TOKENS["surface_2"]};
    color: {TOKENS["text_primary"]};
}}

QMenu {{
    background-color: {TOKENS["surface_0"]};
    border: 1px solid {TOKENS["line_soft"]};
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 22px 6px 10px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {TOKENS["surface_2"]};
}}
"""

SIDEBAR_STYLES = f"""
#Sidebar {{
    background-color: {TOKENS["surface_0"]};
    border-right: 1px solid {TOKENS["line_soft"]};
}}

#SidebarBrand {{
    background-color: transparent;
    color: {TOKENS["accent"]};
    font-family: {FONTS["display"]};
    font-size: 15pt;
    font-weight: 700;
    letter-spacing: 1px;
    border-bottom: 1px solid {TOKENS["line_soft"]};
}}

#SectionHeader {{
    background-color: transparent;
    color: {TOKENS["text_muted"]};
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 1.1px;
    text-transform: uppercase;
}}

#NavItem {{
    background-color: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: {TOKENS["text_muted"]};
}}

#NavItem:hover {{
    background-color: {TOKENS["surface_1"]};
    color: {TOKENS["text_primary"]};
}}

#NavItem[selected="true"] {{
    background-color: {TOKENS["surface_1"]};
    border-left: 3px solid {TOKENS["accent"]};
    color: {TOKENS["text_primary"]};
}}

#NavItem[focused="true"] {{
    border-left: 3px solid {TOKENS["focus_ring"]};
    background-color: {TOKENS["surface_2"]};
}}

#NavItem #NavIcon {{
    background-color: transparent;
    font-family: {FONTS["icon"]};
    font-size: 13pt;
}}

#NavItem #NavLabel {{
    background-color: transparent;
    font-family: {FONTS["display"]};
    font-size: 10pt;
    font-weight: 600;
}}
"""

FORM_STYLES = f"""
QLineEdit, QSpinBox, QComboBox {{
    background-color: {TOKENS["surface_0"]};
    border: 1px solid {TOKENS["line_soft"]};
    border-radius: 7px;
    padding: 5px 8px;
    selection-background-color: {TOKENS["surface_3"]};
    color: {TOKENS["text_primary"]};
}}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {TOKENS["focus_ring"]};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background-color: {TOKENS["surface_0"]};
    border: 1px solid {TOKENS["line_soft"]};
    selection-background-color: {TOKENS["surface_2"]};
}}

QCheckBox {{
    background-color: transparent;
    spacing: 6px;
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {TOKENS["line_soft"]};
    border-radius: 3px;
    background-color: {TOKENS["surface_0"]};
}}

QCheckBox::indicator:checked {{
    background-color: {TOKENS["accent"]};
    border-color: {TOKENS["accent"]};
}}
"""

BUTTON_STYLES = f"""
QPushButton {{
    background-color: {TOKENS["surface_1"]};
    color: {TOKENS["text_primary"]};
    border: 1px solid {TOKENS["line_soft"]};
    border-radius: 7px;
    padding: 5px 11px;
    min-height: 18px;
    font-family: {FONTS["display"]};
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {TOKENS["surface_2"]};
}}

QPushButton:pressed {{
    background-color: {TOKENS["surface_0"]};
}}

QPushButton:focus {{
    border: 1px solid {TOKENS["focus_ring"]};
}}

QPushButton:disabled {{
    background-color: {TOKENS["surface_1"]};
    color: {TOKENS["text_dim"]};
    border-color: {TOKENS["line_soft"]};
}}

QPushButton[compact="true"] {{
    min-height: 16px;
    padding: 3px 8px;
    font-size: 8.5pt;
    border-radius: 6px;
}}

QPushButton[role="accent"] {{
    background-color: {TOKENS["accent"]};
    color: {TOKENS["canvas"]};
    border: 1px solid {TOKENS["accent"]};
}}

QPushButton[role="accent"]:hover {{
    background-color: {TOKENS["accent_hover"]};
}}

QPushButton[role="accent"]:pressed {{
    background-color: {TOKENS["accent_press"]};
}}

QPushButton[role="accent"]:disabled {{
    background-color: {TOKENS["accent_subtle"]};
    color: {TOKENS["text_dim"]};
    border: 1px solid {TOKENS["accent_subtle"]};
}}
"""

STRUCTURE_STYLES = f"""
QGroupBox {{
    border: none;
    border-top: 1px solid {TOKENS["line_soft"]};
    margin-top: 7px;
    padding-top: 7px;
    font-weight: 600;
    color: {TOKENS["text_primary"]};
    background-color: transparent;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: {TOKENS["accent"]};
    text-transform: uppercase;
    font-size: 9pt;
    letter-spacing: 0.5px;
}}

QSplitter::handle {{
    background-color: {TOKENS["line_soft"]};
    width: 2px;
    height: 2px;
}}

#SelectionActionBar {{
    background-color: {TOKENS["surface_1"]};
    border: 1px solid {TOKENS["line_soft"]};
    border-radius: 8px;
    padding: 2px 4px;
}}
"""

DATA_VIEW_STYLES = f"""
QHeaderView::section {{
    background-color: {TOKENS["surface_0"]};
    color: {TOKENS["text_muted"]};
    border: 0;
    border-bottom: 1px solid {TOKENS["line_soft"]};
    padding: 5px 7px;
    font-weight: 600;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}}

QTableView, QTableWidget, QTreeWidget, QListWidget {{
    background-color: {TOKENS["surface_0"]};
    alternate-background-color: {TOKENS["surface_1"]};
    border: none;
    selection-background-color: {TOKENS["surface_2"]};
    selection-color: {TOKENS["text_primary"]};
    gridline-color: transparent;
}}

QTableView::item, QTableWidget::item, QTreeWidget::item {{
    padding: 3px 5px;
}}

QListWidget::item {{
    padding: 6px 9px;
    border-bottom: 1px solid {TOKENS["surface_1"]};
    border-left: 3px solid transparent;
}}

QListWidget::item:selected {{
    background-color: {TOKENS["surface_2"]};
    border-left: 3px solid {TOKENS["accent"]};
}}

QListWidget::item:hover:!selected, QAbstractItemView::item:hover {{
    background-color: {TOKENS["surface_1"]};
}}
"""

PROGRESS_STYLES = f"""
QProgressBar {{
    border: 1px solid {TOKENS["line_soft"]};
    border-radius: 6px;
    min-height: 12px;
    max-height: 12px;
    text-align: center;
    background-color: {TOKENS["surface_0"]};
    color: {TOKENS["text_primary"]};
}}

QProgressBar::chunk {{
    background-color: {TOKENS["accent"]};
    border-radius: 6px;
}}

#StatusStrip {{
    background-color: {TOKENS["canvas"]};
    border-top: 1px solid {TOKENS["line_soft"]};
}}

#StatusStrip QProgressBar {{
    border: 1px solid {TOKENS["line_soft"]};
    border-radius: 4px;
    min-height: 10px;
    max-height: 10px;
    background-color: {TOKENS["surface_0"]};
}}

#StatusStrip QProgressBar::chunk {{
    background-color: {TOKENS["accent"]};
    border-radius: 4px;
}}
"""

ALBUM_STYLES = f"""
#AlbumCard {{
    background-color: {TOKENS["surface_1"]};
    border: 1px solid {TOKENS["line_soft"]};
    border-radius: 10px;
}}

#AlbumCard:hover {{
    border-color: {TOKENS["line_strong"]};
    background-color: {TOKENS["surface_2"]};
}}

#AlbumCover {{
    border: 1px solid {TOKENS["line_soft"]};
    border-radius: 6px;
    background-color: {TOKENS["surface_0"]};
    color: {TOKENS["text_dim"]};
    font-size: 8pt;
}}

#AlbumTitle {{
    color: {TOKENS["text_primary"]};
    font-family: {FONTS["display"]};
    font-size: 12pt;
    font-weight: 700;
}}

#AlbumActionButton {{
    background-color: {TOKENS["surface_0"]};
    color: {TOKENS["text_muted"]};
    border: 1px solid {TOKENS["line_soft"]};
    min-width: 34px;
}}

#AlbumActionButton:hover {{
    background-color: {TOKENS["surface_1"]};
    color: {TOKENS["text_primary"]};
}}

#AlbumSelectedBadge {{
    background-color: {TOKENS["accent_subtle"]};
    color: {TOKENS["accent_hover"]};
    border: 1px solid {TOKENS["line_soft"]};
    border-radius: 9px;
    padding: 1px 8px;
    font-size: 8pt;
    font-weight: 600;
}}

#AlbumYear, #AlbumMeta, #DiscHeader, #TrackDuration {{
    color: {TOKENS["text_muted"]};
}}

#TrackNumber {{
    color: {TOKENS["text_dim"]};
}}

#TrackTitle {{
    color: {TOKENS["text_primary"]};
}}

#TrackRow {{
    background-color: transparent;
    border: none;
    border-left: 3px solid transparent;
}}

#TrackRow:hover {{
    background-color: {TOKENS["surface_1"]};
}}

#TrackRow[focused="true"] {{
    background-color: {TOKENS["surface_2"]};
    border-left: 3px solid {TOKENS["focus_ring"]};
}}

#TrackRow[selected="true"] {{
    background-color: {TOKENS["surface_2"]};
    border-left: 3px solid {TOKENS["accent"]};
}}

#AlphabetBar QPushButton {{
    background-color: transparent;
    border: none;
    border-radius: 3px;
    color: {TOKENS["text_muted"]};
    font-size: 8pt;
    font-weight: 600;
    padding: 2px;
    min-height: 18px;
    min-width: 18px;
}}

#AlphabetBar QPushButton:hover {{
    background-color: {TOKENS["surface_2"]};
    color: {TOKENS["text_primary"]};
}}

#AlphabetBar QPushButton:disabled {{
    color: {TOKENS["text_dim"]};
}}

#AlphabetBar QPushButton[active="true"] {{
    background-color: {TOKENS["accent"]};
    color: {TOKENS["canvas"]};
}}
"""

SCROLLBAR_STYLES = f"""
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical {{
    background: {TOKENS["line_soft"]};
    min-height: 24px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background: {TOKENS["line_strong"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 2px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background: {TOKENS["line_soft"]};
    min-width: 24px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {TOKENS["line_strong"]};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
"""

APP_STYLESHEET = "\n".join(
    [
        BASE_STYLES,
        MENU_STYLES,
        SIDEBAR_STYLES,
        FORM_STYLES,
        BUTTON_STYLES,
        STRUCTURE_STYLES,
        DATA_VIEW_STYLES,
        PROGRESS_STYLES,
        ALBUM_STYLES,
        SCROLLBAR_STYLES,
    ]
)


def build_stylesheet(
    *,
    tokens: Mapping[str, str] | None = None,
    fonts: Mapping[str, str] | None = None,
    extra_stylesheet: str = "",
) -> str:
    """Build the application stylesheet with token/font overrides."""
    resolved_tokens = dict(DEFAULT_TOKENS)
    for key, value in (tokens or {}).items():
        if key in resolved_tokens and isinstance(value, str) and value:
            resolved_tokens[key] = value

    resolved_fonts = dict(DEFAULT_FONTS)
    for key, value in (fonts or {}).items():
        if key in resolved_fonts and isinstance(value, str) and value:
            resolved_fonts[key] = value

    stylesheet = APP_STYLESHEET
    for key, default_value in DEFAULT_TOKENS.items():
        stylesheet = stylesheet.replace(default_value, resolved_tokens[key])
    for key, default_value in DEFAULT_FONTS.items():
        stylesheet = stylesheet.replace(default_value, resolved_fonts[key])

    extra = extra_stylesheet.strip()
    if extra:
        stylesheet = f"{stylesheet}\n\n{extra}\n"
    return stylesheet
