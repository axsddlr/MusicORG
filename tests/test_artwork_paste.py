"""Tests for clipboard-based artwork paste flows."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from musicorg.ui.artwork_downloader_panel import ArtworkDownloaderPanel
from musicorg.ui.widgets.artwork_paste import PasteArtworkLabel, clipboard_image_payload
from musicorg.ui.widgets.tag_form import TagForm


def _sample_image() -> QImage:
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    return image


def test_clipboard_image_payload_reads_qimage(qtbot):
    clipboard = QApplication.clipboard()
    clipboard.setImage(_sample_image())

    payload = clipboard_image_payload(clipboard)

    assert payload is not None
    data, mime = payload
    assert mime == "image/png"
    assert len(data) > 0


def test_paste_artwork_label_emits_on_ctrl_v(qtbot):
    label = PasteArtworkLabel("Preview")
    qtbot.addWidget(label)
    label.show()
    label.setFocus()
    triggered: list[bool] = []
    label.paste_requested.connect(lambda: triggered.append(True))

    qtbot.keyClick(label, Qt.Key_V, Qt.KeyboardModifier.ControlModifier)

    assert triggered == [True]


def test_tag_form_accepts_clipboard_paste(qtbot):
    clipboard = QApplication.clipboard()
    clipboard.setImage(_sample_image())
    form = TagForm()
    qtbot.addWidget(form)
    form.show()
    form._artwork_preview.setFocus()

    qtbot.keyClick(form._artwork_preview, Qt.Key_V, Qt.KeyboardModifier.ControlModifier)

    tags = form.get_tags()
    assert tags.artwork_data
    assert tags.artwork_mime == "image/png"
    assert form.artwork_modified() is True


def test_artwork_downloader_accepts_clipboard_paste(qtbot):
    clipboard = QApplication.clipboard()
    clipboard.setImage(_sample_image())
    panel = ArtworkDownloaderPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel._preview_image_label.setFocus()

    qtbot.keyClick(panel._preview_image_label, Qt.Key_V, Qt.KeyboardModifier.ControlModifier)

    assert panel._selected_artwork_data
    assert panel._selected_artwork_mime == "image/png"
    assert panel._preview_title_label.text() == "Pasted artwork"
