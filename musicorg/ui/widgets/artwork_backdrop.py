"""Faded, blurred artwork overlay for the main content area."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, Property, QPropertyAnimation, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class ArtworkBackdrop(QWidget):
    """Mouse-transparent overlay that paints blurred album artwork."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self._target_opacity: float = 0.07
        self._paint_opacity: float = 0.0
        self._artwork_data: bytes | None = None
        self._source_pixmap = QPixmap()
        self._blurred_pixmap = QPixmap()
        self._fade = QPropertyAnimation(self, b"paintOpacity", self)
        self._fade.setDuration(260)
        self._fade.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._fade.finished.connect(self._on_fade_finished)
        self.hide()

    def set_artwork(self, data: bytes | None) -> None:
        """Load new artwork and invalidate cached blur output."""
        if not data:
            self.clear()
            return
        if self._artwork_data == data and not self._source_pixmap.isNull():
            self.show()
            self.update()
            return

        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self.clear()
            return

        self._artwork_data = data
        self._source_pixmap = pixmap
        self._blurred_pixmap = QPixmap()
        self._fade.stop()
        self._paint_opacity = 0.0
        self.show()
        self._animate_to(self._target_opacity)
        self.update()

    def set_opacity(self, value: float) -> None:
        """Set the backdrop paint opacity and repaint."""
        self._target_opacity = max(0.0, min(0.35, value))
        if self._source_pixmap.isNull():
            self._paint_opacity = 0.0
        else:
            self._paint_opacity = self._target_opacity
        self.update()

    def clear(self) -> None:
        """Clear current artwork and hide the overlay."""
        if self._source_pixmap.isNull():
            self._clear_immediately()
            return
        self._animate_to(0.0)

    def paintEvent(self, _event) -> None:
        if self._source_pixmap.isNull() or self.width() <= 0 or self.height() <= 0:
            return

        if self._blurred_pixmap.isNull() or self._blurred_pixmap.size() != self.size():
            self._rebuild_blurred_pixmap()
        if self._blurred_pixmap.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setOpacity(self._paint_opacity)
        painter.drawPixmap(self.rect(), self._blurred_pixmap)

    def _clear_immediately(self) -> None:
        self._artwork_data = None
        self._source_pixmap = QPixmap()
        self._blurred_pixmap = QPixmap()
        self._paint_opacity = 0.0
        self.hide()
        self.update()

    def _animate_to(self, value: float) -> None:
        self._fade.stop()
        self._fade.setStartValue(self._paint_opacity)
        self._fade.setEndValue(value)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._paint_opacity <= 0.001:
            self._clear_immediately()

    def _rebuild_blurred_pixmap(self) -> None:
        if self._source_pixmap.isNull():
            self._blurred_pixmap = QPixmap()
            return

        target_size = self.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            self._blurred_pixmap = QPixmap()
            return

        cover = self._source_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (cover.width() - target_size.width()) // 2)
        y = max(0, (cover.height() - target_size.height()) // 2)
        cover = cover.copy(x, y, target_size.width(), target_size.height())

        tiny = cover.scaled(
            32,
            32,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._blurred_pixmap = tiny.scaled(
            target_size,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _get_paint_opacity(self) -> float:
        return self._paint_opacity

    def _set_paint_opacity(self, value: float) -> None:
        self._paint_opacity = max(0.0, min(1.0, value))
        if self._paint_opacity > 0.001 and not self.isVisible():
            self.show()
        self.update()

    paintOpacity = Property(float, _get_paint_opacity, _set_paint_opacity)
