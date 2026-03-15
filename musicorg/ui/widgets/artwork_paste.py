"""Reusable clipboard-aware artwork input helpers."""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QIODevice, Qt, Signal
from PySide6.QtGui import QClipboard, QGuiApplication, QImage, QKeySequence
from PySide6.QtWidgets import QLabel, QMenu, QWidget

_SUPPORTED_IMAGE_MIME_TYPES: tuple[str, ...] = (
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/bmp",
    "image/gif",
)


class PasteArtworkLabel(QLabel):
    """Artwork preview label that accepts paste shortcuts and context-menu paste."""

    paste_requested = Signal()

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setToolTip("Click the artwork box and press Ctrl+V to paste an image.")

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction("Paste Image", self.paste_requested.emit)
        menu.exec(self.mapToGlobal(pos))


def clipboard_image_payload(
    clipboard: QClipboard | None = None,
) -> tuple[bytes, str] | None:
    """Return image bytes and mime type from the clipboard when possible."""

    resolved_clipboard = clipboard or QGuiApplication.clipboard()
    if resolved_clipboard is None:
        return None

    mime_data = resolved_clipboard.mimeData()
    if mime_data is not None:
        for mime_type in _SUPPORTED_IMAGE_MIME_TYPES:
            if not mime_data.hasFormat(mime_type):
                continue
            raw_data = bytes(mime_data.data(mime_type))
            if not raw_data:
                continue
            if QImage.fromData(raw_data).isNull():
                continue
            normalized_mime = "image/jpeg" if mime_type == "image/jpg" else mime_type
            return raw_data, normalized_mime

    image = resolved_clipboard.image()
    if image.isNull():
        return None
    return _encode_image_as_png(image)


def _encode_image_as_png(image: QImage) -> tuple[bytes, str] | None:
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        return None
    if not image.save(buffer, "PNG"):
        return None
    return bytes(buffer.data()), "image/png"

