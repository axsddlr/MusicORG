"""Player page widget for MusicBee-style playback UX."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from musicorg.plugins.context import PluginContext
from .player_mini_bar import _format_time
from .player_engine import (
    PlayerEngine,
    QueueTrack,
)


class PlayerPage(QWidget):
    """Queue management page; transport controls live in the bottom mini-player."""

    def __init__(
        self,
        engine: PlayerEngine,
        context: PluginContext,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._context = context
        self._setup_ui()
        self._connect_signals()
        self._engine.refresh_state()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        now_playing = QFrame()
        now_playing.setObjectName("Card")
        now_layout = QHBoxLayout(now_playing)
        now_layout.setContentsMargins(12, 12, 12, 12)
        now_layout.setSpacing(12)
        self._artwork = QLabel("No Art")
        self._artwork.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._artwork.setFixedSize(100, 100)
        self._artwork.setObjectName("ArtworkThumb")
        now_layout.addWidget(self._artwork)

        meta_layout = QVBoxLayout()
        title = QLabel("NOW PLAYING")
        title.setObjectName("SectionHeader")
        self._title_label = QLabel("Nothing queued")
        self._title_label.setObjectName("StatusDetail")
        self._artist_label = QLabel("")
        self._artist_label.setObjectName("StatusMuted")
        self._album_label = QLabel("")
        self._album_label.setObjectName("StatusMuted")
        self._path_label = QLabel("")
        self._path_label.setObjectName("StatusMuted")
        self._path_label.setWordWrap(True)
        meta_layout.addWidget(title)
        meta_layout.addWidget(self._title_label)
        meta_layout.addWidget(self._artist_label)
        meta_layout.addWidget(self._album_label)
        meta_layout.addWidget(self._path_label)
        now_layout.addLayout(meta_layout, 1)
        root.addWidget(now_playing)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(8)
        self._add_selected_btn = QPushButton("Add Selected")
        self._remove_btn = QPushButton("Remove")
        self._move_up_btn = QPushButton("Move Up")
        self._move_down_btn = QPushButton("Move Down")
        self._clear_btn = QPushButton("Clear Queue")
        self._restore_queue_toggle = QCheckBox("Restore Queue")
        controls_row.addWidget(self._add_selected_btn)
        controls_row.addWidget(self._remove_btn)
        controls_row.addWidget(self._move_up_btn)
        controls_row.addWidget(self._move_down_btn)
        controls_row.addWidget(self._clear_btn)
        controls_row.addWidget(self._restore_queue_toggle)
        controls_row.addStretch(1)
        root.addLayout(controls_row)

        hint = QLabel("Playback controls are available in the bottom player bar.")
        hint.setObjectName("StatusMuted")
        root.addWidget(hint)

        self._queue = QListWidget()
        self._queue.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._queue.setAlternatingRowColors(True)
        root.addWidget(self._queue, 1)

    def _connect_signals(self) -> None:
        self._add_selected_btn.clicked.connect(self._on_add_selected_clicked)
        self._remove_btn.clicked.connect(self._on_remove_clicked)
        self._move_up_btn.clicked.connect(self._on_move_up_clicked)
        self._move_down_btn.clicked.connect(self._on_move_down_clicked)
        self._clear_btn.clicked.connect(self._engine.clear_queue)
        self._restore_queue_toggle.toggled.connect(self._engine.set_restore_queue_enabled)

        self._queue.itemDoubleClicked.connect(self._on_item_double_clicked)

        self._engine.queue_changed.connect(self._on_queue_changed)
        self._engine.now_playing_changed.connect(self._on_now_playing_changed)

    def _on_add_selected_clicked(self) -> None:
        count = self._engine.add_selected_paths()
        if count > 0:
            self._context.show_status(f"Added {count} track(s) to queue", 2200)
        else:
            self._context.show_status("No supported files selected", 2200)

    def _on_remove_clicked(self) -> None:
        row = self._queue.currentRow()
        if row < 0:
            return
        self._engine.remove_indices([row])

    def _on_move_up_clicked(self) -> None:
        row = self._queue.currentRow()
        next_row = self._engine.move_up(row)
        self._queue.setCurrentRow(next_row)

    def _on_move_down_clicked(self) -> None:
        row = self._queue.currentRow()
        next_row = self._engine.move_down(row)
        self._queue.setCurrentRow(next_row)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        row = self._queue.row(item)
        self._engine.play_index(row)

    def _on_queue_changed(self, queue_obj: object) -> None:
        queue = queue_obj if isinstance(queue_obj, list) else []
        selected = self._queue.currentRow()
        self._queue.clear()
        for track in queue:
            if not isinstance(track, QueueTrack):
                continue
            duration = _format_time(int(track.duration_seconds * 1000))
            label = f"{track.artist} - {track.title}   ({duration})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(track.path))
            self._queue.addItem(item)
        if self._queue.count() > 0:
            self._queue.setCurrentRow(min(max(selected, 0), self._queue.count() - 1))
        self._remove_btn.setEnabled(self._queue.count() > 0)
        self._move_up_btn.setEnabled(self._queue.count() > 1)
        self._move_down_btn.setEnabled(self._queue.count() > 1)
        self._clear_btn.setEnabled(self._queue.count() > 0)

    def _on_now_playing_changed(self, track_obj: object) -> None:
        if not isinstance(track_obj, QueueTrack):
            self._title_label.setText("Nothing queued")
            self._artist_label.setText("")
            self._album_label.setText("")
            self._path_label.setText("")
            self._artwork.setText("No Art")
            self._artwork.setPixmap(QPixmap())
            return
        self._title_label.setText(track_obj.title)
        self._artist_label.setText(track_obj.artist)
        self._album_label.setText(track_obj.album)
        self._path_label.setText(str(track_obj.path))
        self._set_artwork(track_obj.artwork_data)

    def _set_artwork(self, artwork_data: bytes | None) -> None:
        if not artwork_data:
            self._artwork.setText("No Art")
            self._artwork.setPixmap(QPixmap())
            return
        pix = QPixmap()
        if not pix.loadFromData(artwork_data):
            self._artwork.setText("No Art")
            self._artwork.setPixmap(QPixmap())
            return
        self._artwork.setText("")
        self._artwork.setPixmap(
            pix.scaled(
                100,
                100,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _sync_restore_queue_toggle(self) -> None:
        blocker_restore = self._restore_queue_toggle.blockSignals(True)
        self._restore_queue_toggle.setChecked(self._engine.restore_queue_enabled())
        self._restore_queue_toggle.blockSignals(blocker_restore)

    def showEvent(self, event) -> None:
        self._sync_restore_queue_toggle()
        super().showEvent(event)
