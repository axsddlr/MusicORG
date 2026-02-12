"""A-Z quick-jump letter bar widget."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

_LETTERS = ["#"] + [chr(i) for i in range(ord("A"), ord("Z") + 1)]


class AlphabetBar(QWidget):
    """Horizontal row of compact letter buttons for quick-jump navigation."""

    letter_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AlphabetBar")
        self._buttons: dict[str, QPushButton] = {}
        self._active_letter: str = ""
        self._available: set[str] = set()
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(1)

        for letter in _LETTERS:
            btn = QPushButton(letter)
            btn.setFixedSize(24, 22)
            btn.setProperty("active", False)
            btn.clicked.connect(lambda checked=False, l=letter: self._on_click(l))
            layout.addWidget(btn)
            self._buttons[letter] = btn

        layout.addStretch()

    def _on_click(self, letter: str) -> None:
        self.letter_clicked.emit(letter)

    def set_active_letter(self, letter: str) -> None:
        letter = letter.upper()
        if self._active_letter and self._active_letter in self._buttons:
            btn = self._buttons[self._active_letter]
            btn.setProperty("active", False)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._active_letter = letter
        if letter in self._buttons:
            btn = self._buttons[letter]
            btn.setProperty("active", True)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def set_available_letters(self, letters: set[str]) -> None:
        self._available = {l.upper() for l in letters}
        style = self.style()
        style.unpolish(self)
        for letter, btn in self._buttons.items():
            available = letter in self._available
            btn.setProperty("available", available)
            btn.setEnabled(available)
        style.polish(self)
        self.update()
