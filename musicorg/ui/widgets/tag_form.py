"""Form widget for editing tag fields."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QMessageBox, QSpinBox, QWidget,
)

from musicorg.core.tagger import TagData


class TagForm(QWidget):
    """A form layout showing all editable tag fields."""
    _MAX_ARTWORK_BYTES = 10 * 1024 * 1024

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)

        self.title_edit = QLineEdit()
        self.artist_edit = QLineEdit()
        self.album_edit = QLineEdit()
        self.albumartist_edit = QLineEdit()
        self.track_spin = QSpinBox()
        self.track_spin.setRange(0, 999)
        self.disc_spin = QSpinBox()
        self.disc_spin.setRange(0, 99)
        self.year_spin = QSpinBox()
        self.year_spin.setRange(0, 9999)
        self.genre_edit = QLineEdit()
        self.composer_edit = QLineEdit()
        self.comment_edit = QLineEdit()
        self.lyrics_edit = QPlainTextEdit()
        self.lyrics_edit.setFixedHeight(80)
        self._artwork_data: bytes = b""
        self._artwork_mime: str = ""
        self._artwork_modified = False
        self._artwork_preview = QLabel("No Preview")
        self._artwork_preview.setObjectName("AlbumCover")
        self._artwork_preview.setFixedSize(96, 96)
        self._artwork_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._artwork_label = QLabel("No artwork")
        self._choose_artwork_btn = QPushButton("Choose Image...")
        self._choose_artwork_btn.clicked.connect(self._choose_artwork)
        self._clear_artwork_btn = QPushButton("Remove")
        self._clear_artwork_btn.clicked.connect(self._clear_artwork)
        self._clear_artwork_btn.setEnabled(False)

        artwork_widget = QWidget()
        artwork_layout = QHBoxLayout(artwork_widget)
        artwork_layout.setContentsMargins(0, 0, 0, 0)
        artwork_layout.setSpacing(8)
        artwork_layout.addWidget(self._artwork_preview, 0)
        artwork_layout.addWidget(self._artwork_label, 1)
        artwork_layout.addWidget(self._choose_artwork_btn)
        artwork_layout.addWidget(self._clear_artwork_btn)

        layout.addRow("Title:", self.title_edit)
        layout.addRow("Artist:", self.artist_edit)
        layout.addRow("Album:", self.album_edit)
        layout.addRow("Album Artist:", self.albumartist_edit)
        layout.addRow("Track #:", self.track_spin)
        layout.addRow("Disc #:", self.disc_spin)
        layout.addRow("Year:", self.year_spin)
        layout.addRow("Genre:", self.genre_edit)
        layout.addRow("Composer:", self.composer_edit)
        layout.addRow("Comment:", self.comment_edit)
        layout.addRow("Lyrics:", self.lyrics_edit)
        layout.addRow("Artwork:", artwork_widget)

    def set_tags(self, tags: TagData) -> None:
        self.title_edit.setText(tags.title)
        self.artist_edit.setText(tags.artist)
        self.album_edit.setText(tags.album)
        self.albumartist_edit.setText(tags.albumartist)
        self.track_spin.setValue(tags.track)
        self.disc_spin.setValue(tags.disc)
        self.year_spin.setValue(tags.year)
        self.genre_edit.setText(tags.genre)
        self.composer_edit.setText(tags.composer)
        self.comment_edit.setText(tags.comment)
        self.lyrics_edit.setPlainText(tags.lyrics)
        self._artwork_data = tags.artwork_data or b""
        self._artwork_mime = tags.artwork_mime or ""
        self._artwork_modified = False
        self._refresh_artwork_label()

    def get_tags(self) -> TagData:
        return TagData(
            title=self.title_edit.text(),
            artist=self.artist_edit.text(),
            album=self.album_edit.text(),
            albumartist=self.albumartist_edit.text(),
            track=self.track_spin.value(),
            disc=self.disc_spin.value(),
            year=self.year_spin.value(),
            genre=self.genre_edit.text(),
            composer=self.composer_edit.text(),
            comment=self.comment_edit.text(),
            lyrics=self.lyrics_edit.toPlainText(),
            artwork_data=self._artwork_data,
            artwork_mime=self._artwork_mime,
        )

    def clear(self) -> None:
        self.title_edit.clear()
        self.artist_edit.clear()
        self.album_edit.clear()
        self.albumartist_edit.clear()
        self.track_spin.setValue(0)
        self.disc_spin.setValue(0)
        self.year_spin.setValue(0)
        self.genre_edit.clear()
        self.composer_edit.clear()
        self.comment_edit.clear()
        self.lyrics_edit.clear()
        self._artwork_data = b""
        self._artwork_mime = ""
        self._artwork_modified = False
        self._refresh_artwork_label()

    def set_enabled(self, enabled: bool) -> None:
        for child in self.findChildren(QLineEdit):
            child.setEnabled(enabled)
        for child in self.findChildren(QPlainTextEdit):
            child.setEnabled(enabled)
        for child in self.findChildren(QSpinBox):
            child.setEnabled(enabled)
        self._choose_artwork_btn.setEnabled(enabled)
        self._clear_artwork_btn.setEnabled(enabled and bool(self._artwork_data))

    def _choose_artwork(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Artwork Image",
            "",
            "Images (*.jpg *.jpeg *.png *.webp *.bmp);;All Files (*)",
        )
        if not file_path:
            return
        path = Path(file_path)
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if size > self._MAX_ARTWORK_BYTES:
            max_mb = self._MAX_ARTWORK_BYTES // (1024 * 1024)
            QMessageBox.warning(
                self,
                "Artwork Too Large",
                f"Please choose an image smaller than {max_mb} MB.",
            )
            return
        try:
            self._artwork_data = path.read_bytes()
        except OSError:
            self._artwork_data = b""
            self._artwork_mime = ""
            self._refresh_artwork_label()
            return
        mime, _ = mimetypes.guess_type(path.name)
        self._artwork_mime = mime or "image/jpeg"
        self._artwork_modified = True
        self._refresh_artwork_label(path.name)

    def _clear_artwork(self) -> None:
        self._artwork_data = b""
        self._artwork_mime = ""
        self._artwork_modified = True
        self._refresh_artwork_label()

    def artwork_modified(self) -> bool:
        return self._artwork_modified

    def mark_clean(self) -> None:
        self._artwork_modified = False

    def _refresh_artwork_label(self, source_name: str = "") -> None:
        if self._artwork_data:
            size_kb = max(1, len(self._artwork_data) // 1024)
            pixmap = QPixmap()
            if pixmap.loadFromData(self._artwork_data):
                dimensions = f"{pixmap.width()}x{pixmap.height()} px"
                preview = pixmap.scaled(
                    self._artwork_preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._artwork_preview.setPixmap(preview)
                self._artwork_preview.setText("")
            else:
                dimensions = "unknown size"
                self._artwork_preview.setPixmap(QPixmap())
                self._artwork_preview.setText("Invalid")
            if source_name:
                label_text = f"Selected: {source_name} ({dimensions}, {size_kb} KB)"
            else:
                mime = self._artwork_mime or "image/*"
                label_text = f"Current: Embedded artwork ({mime}, {dimensions}, {size_kb} KB)"
            self._artwork_label.setText(label_text)
            self._artwork_label.setToolTip(label_text)
            self._clear_artwork_btn.setEnabled(True)
        else:
            self._artwork_label.setText("No artwork")
            self._artwork_label.setToolTip("")
            self._artwork_preview.setPixmap(QPixmap())
            self._artwork_preview.setText("No Preview")
            self._clear_artwork_btn.setEnabled(False)
