"""Left sidebar navigation widget inspired by MusicBee."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)


class NavItem(QFrame):
    """A single clickable navigation item."""

    clicked = Signal()

    def __init__(self, icon_char: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NavItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("selected", False)
        self.setProperty("focused", False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        icon_label = QLabel(icon_char)
        icon_label.setObjectName("NavIcon")
        icon_label.setFixedWidth(22)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        text_label = QLabel(label)
        text_label.setObjectName("NavLabel")
        layout.addWidget(text_label, 1)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        self.setProperty("focused", True)
        self.style().unpolish(self)
        self.style().polish(self)
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.setProperty("focused", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().focusOutEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)


class SidebarNav(QFrame):
    """Left sidebar with branding, navigation items, and settings."""

    page_changed = Signal(int)

    _NAV_ITEMS = [
        ("\uE8B7", "Source"),
        ("\uE895", "Sync"),
        ("\uE8C8", "Duplicates"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setMinimumWidth(184)
        self.setMaximumWidth(236)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Branding
        branding = QLabel("MusicOrg")
        branding.setObjectName("SidebarBrand")
        branding.setAlignment(Qt.AlignmentFlag.AlignCenter)
        branding.setFixedHeight(48)
        layout.addWidget(branding)

        # Section label
        section = QLabel("LIBRARY")
        section.setObjectName("SectionHeader")
        section.setContentsMargins(14, 12, 14, 4)
        layout.addWidget(section)

        # Navigation items
        self._nav_items: list[NavItem] = []
        for i, (icon, label) in enumerate(self._NAV_ITEMS):
            item = NavItem(icon, label)
            item.clicked.connect(lambda idx=i: self._on_item_clicked(idx))
            self._nav_items.append(item)
            layout.addWidget(item)

        layout.addStretch(1)

        # Select first item by default
        if self._nav_items:
            self._nav_items[0].set_selected(True)

    def _on_item_clicked(self, index: int) -> None:
        self.set_selected(index)
        self.page_changed.emit(index)

    def set_selected(self, index: int) -> None:
        for i, item in enumerate(self._nav_items):
            item.set_selected(i == index)
