"""Form widget for editing tag fields."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout, QLineEdit, QSpinBox, QWidget,
)

from musicorg.core.tagger import TagData


class TagForm(QWidget):
    """A form layout showing all editable tag fields."""

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

        layout.addRow("Title:", self.title_edit)
        layout.addRow("Artist:", self.artist_edit)
        layout.addRow("Album:", self.album_edit)
        layout.addRow("Album Artist:", self.albumartist_edit)
        layout.addRow("Track #:", self.track_spin)
        layout.addRow("Disc #:", self.disc_spin)
        layout.addRow("Year:", self.year_spin)
        layout.addRow("Genre:", self.genre_edit)
        layout.addRow("Composer:", self.composer_edit)

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

    def set_enabled(self, enabled: bool) -> None:
        for child in self.findChildren(QLineEdit):
            child.setEnabled(enabled)
        for child in self.findChildren(QSpinBox):
            child.setEnabled(enabled)
