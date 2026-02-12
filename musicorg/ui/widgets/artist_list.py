"""Artist list widget with thumbnail delegate."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

ROLE_ARTIST_KEY = Qt.ItemDataRole.UserRole
ROLE_THUMBNAIL = int(Qt.ItemDataRole.UserRole) + 1
ROLE_ALBUM_COUNT = int(Qt.ItemDataRole.UserRole) + 2

_THUMB_SIZE = 32
_ROW_HEIGHT = 48
_PADDING = 6


class ArtistItemDelegate(QStyledItemDelegate):
    """Custom delegate: 32x32 thumbnail | artist name | album count."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw selection/hover background
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#252a35"))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor("#191c21"))

        # Selection accent border
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(
                QRect(option.rect.left(), option.rect.top(), 3, option.rect.height()),
                QColor("#d4a44a"),
            )

        x = option.rect.left() + _PADDING + 3  # after accent border space
        y = option.rect.top()

        # Thumbnail
        thumb: QPixmap | None = index.data(ROLE_THUMBNAIL)
        thumb_rect = QRect(x, y + (_ROW_HEIGHT - _THUMB_SIZE) // 2, _THUMB_SIZE, _THUMB_SIZE)
        if thumb and not thumb.isNull():
            painter.drawPixmap(thumb_rect, thumb)
        else:
            painter.fillRect(thumb_rect, QColor("#1e2228"))
            painter.setPen(QColor("#4a5260"))
            painter.drawRect(thumb_rect)

        text_x = x + _THUMB_SIZE + _PADDING

        # Artist name
        artist_name = index.data(Qt.ItemDataRole.DisplayRole) or ""
        name_font = QFont(option.font)
        name_font.setPointSize(10)
        name_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(name_font)
        painter.setPen(QColor("#dcdfe4"))
        name_rect = QRect(text_x, y + 6, option.rect.right() - text_x - _PADDING, 20)
        painter.drawText(name_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, artist_name)

        # Album count
        album_count = index.data(ROLE_ALBUM_COUNT)
        if album_count is not None:
            count_font = QFont(option.font)
            count_font.setPointSize(8)
            painter.setFont(count_font)
            painter.setPen(QColor("#7a8494"))
            count_text = f"{album_count} album{'s' if album_count != 1 else ''}"
            count_rect = QRect(text_x, y + 26, option.rect.right() - text_x - _PADDING, 16)
            painter.drawText(count_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, count_text)

        # Bottom border
        painter.setPen(QColor("#1a1d22"))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(option.rect.width(), _ROW_HEIGHT)


class ArtistListWidget(QListWidget):
    """Artist list with custom thumbnail delegate."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setItemDelegate(ArtistItemDelegate(self))
        self.setUniformItemSizes(True)
        self.setMouseTracking(True)

    def add_artist(
        self,
        name: str,
        artist_key: str,
        thumbnail: QPixmap | None,
        album_count: int,
    ) -> None:
        item = QListWidgetItem(name)
        item.setData(ROLE_ARTIST_KEY, artist_key)
        item.setData(ROLE_ALBUM_COUNT, album_count)
        if thumbnail and not thumbnail.isNull():
            scaled = thumbnail.scaled(
                _THUMB_SIZE, _THUMB_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            item.setData(ROLE_THUMBNAIL, scaled)
        else:
            item.setData(ROLE_THUMBNAIL, QPixmap())
        self.addItem(item)
