"""Bottom mini-player bar widget."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QWidget,
)

from .player_engine import PlayerEngine, QueueTrack, RepeatMode


def _format_time(ms: int) -> str:
    total = max(0, int(ms) // 1000)
    minutes, seconds = divmod(total, 60)
    return f"{minutes}:{seconds:02d}"


class PlayerMiniBar(QFrame):
    """Compact transport bar shown above the status strip."""

    def __init__(self, engine: PlayerEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._seeking = False
        self._repeat_mode = RepeatMode.OFF.value
        self.setObjectName("PlayerMiniBar")
        self._setup_ui()
        self._connect_signals()
        self._engine.refresh_state()

    def _setup_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedHeight(66)
        self.setStyleSheet(
            """
            QFrame#PlayerMiniBar {
                background: #0f131a;
                border: 1px solid #252c37;
                border-radius: 8px;
            }
            QPushButton#TransportButton {
                background: transparent;
                border: 1px solid #334055;
                color: #cfd8e8;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#TransportButton:hover {
                background: #1c2230;
                border-color: #4f6183;
            }
            QPushButton#TransportButton:pressed {
                background: #171d29;
            }
            QPushButton#TransportToggle:checked {
                background: #2f4f89;
                border: 1px solid #77a2ff;
                color: #f6f8ff;
            }
            QPushButton#TransportButtonPrimary {
                background: #d74a4a;
                border: 1px solid #f06f6f;
                color: #fbfdff;
                border-radius: 9px;
                font-size: 15px;
                font-weight: 700;
            }
            QPushButton#TransportButtonPrimary:hover {
                background: #e15a5a;
                border-color: #ff8b8b;
            }
            QLabel#MiniTitle {
                color: #e9eef9;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#MiniTime {
                color: #96a3bb;
                font-size: 11px;
                min-width: 40px;
            }
            QSlider#ProgressSlider::groove:horizontal {
                height: 3px;
                border-radius: 1px;
                background: #2a3342;
            }
            QSlider#ProgressSlider::sub-page:horizontal {
                background: #d74a4a;
                border-radius: 1px;
            }
            QSlider#ProgressSlider::add-page:horizontal {
                background: #2a3342;
                border-radius: 1px;
            }
            QSlider#ProgressSlider::handle:horizontal {
                background: #f5f7fb;
                width: 10px;
                height: 10px;
                margin: -4px 0;
                border-radius: 5px;
            }
            QSlider#VolumeSlider::groove:horizontal {
                height: 3px;
                border-radius: 1px;
                background: #2a3342;
            }
            QSlider#VolumeSlider::sub-page:horizontal {
                background: #9fb4de;
                border-radius: 1px;
            }
            QSlider#VolumeSlider::add-page:horizontal {
                background: #2a3342;
                border-radius: 1px;
            }
            QSlider#VolumeSlider::handle:horizontal {
                background: #dbe5f7;
                width: 9px;
                height: 9px;
                margin: -4px 0;
                border-radius: 4px;
            }
            """
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        self._prev_btn = QPushButton("<<")
        self._play_btn = QPushButton(">")
        self._next_btn = QPushButton(">>")
        self._prev_btn.setObjectName("TransportButton")
        self._play_btn.setObjectName("TransportButtonPrimary")
        self._next_btn.setObjectName("TransportButton")
        self._prev_btn.setToolTip("Previous track")
        self._play_btn.setToolTip("Play or pause")
        self._next_btn.setToolTip("Next track")
        self._prev_btn.setAccessibleName("Previous")
        self._play_btn.setAccessibleName("Play Pause")
        self._next_btn.setAccessibleName("Next")
        self._prev_btn.setFixedSize(40, 34)
        self._play_btn.setFixedSize(44, 36)
        self._next_btn.setFixedSize(40, 34)
        layout.addWidget(self._prev_btn)
        layout.addWidget(self._play_btn)
        layout.addWidget(self._next_btn)

        self._shuffle_btn = QPushButton("SHF")
        self._shuffle_btn.setObjectName("TransportButton")
        self._shuffle_btn.setCheckable(True)
        self._shuffle_btn.setToolTip("Shuffle")
        self._shuffle_btn.setFixedSize(42, 30)
        self._shuffle_btn.setAccessibleName("Shuffle")
        self._repeat_btn = QPushButton("REP OFF")
        self._repeat_btn.setObjectName("TransportButton")
        self._repeat_btn.setToolTip("Repeat mode")
        self._repeat_btn.setFixedSize(62, 30)
        self._repeat_btn.setAccessibleName("Repeat")
        layout.addWidget(self._shuffle_btn)
        layout.addWidget(self._repeat_btn)

        self._title_label = QLabel("Nothing queued")
        self._title_label.setObjectName("MiniTitle")
        self._title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._title_label.setMinimumWidth(280)
        layout.addWidget(self._title_label, 1)

        self._position_label = QLabel("0:00")
        self._position_label.setObjectName("MiniTime")
        self._duration_label = QLabel("0:00")
        self._duration_label.setObjectName("MiniTime")
        self._seek = QSlider(Qt.Orientation.Horizontal)
        self._seek.setObjectName("ProgressSlider")
        self._seek.setRange(0, 0)
        layout.addWidget(self._position_label)
        layout.addWidget(self._seek, 2)
        layout.addWidget(self._duration_label)

        self._mute_btn = QPushButton("M")
        self._mute_btn.setObjectName("TransportButton")
        self._mute_btn.setCheckable(True)
        self._mute_btn.setToolTip("Mute")
        self._mute_btn.setFixedSize(30, 28)
        volume_label = QLabel("VOL")
        volume_label.setObjectName("MiniTime")
        self._volume = QSlider(Qt.Orientation.Horizontal)
        self._volume.setObjectName("VolumeSlider")
        self._volume.setRange(0, 100)
        self._volume.setFixedWidth(110)
        layout.addWidget(self._mute_btn)
        layout.addWidget(volume_label)
        layout.addWidget(self._volume)

    def _connect_signals(self) -> None:
        self._prev_btn.clicked.connect(self._engine.previous_track)
        self._play_btn.clicked.connect(self._engine.play_pause)
        self._next_btn.clicked.connect(self._engine.next_track)
        self._shuffle_btn.toggled.connect(self._engine.set_shuffle_enabled)
        self._repeat_btn.clicked.connect(self._on_repeat_clicked)
        self._mute_btn.toggled.connect(self._engine.set_muted)
        self._volume.valueChanged.connect(self._engine.set_volume)
        self._seek.sliderPressed.connect(self._on_seek_press)
        self._seek.sliderReleased.connect(self._on_seek_release)

        self._engine.now_playing_changed.connect(self._on_now_playing_changed)
        self._engine.playback_state_changed.connect(self._on_playback_state_changed)
        self._engine.position_changed.connect(self._on_position_changed)
        self._engine.volume_changed.connect(self._on_volume_changed)
        self._engine.modes_changed.connect(self._on_modes_changed)

    def _on_seek_press(self) -> None:
        self._seeking = True

    def _on_seek_release(self) -> None:
        self._seeking = False
        self._engine.seek(self._seek.value())

    def _on_repeat_clicked(self) -> None:
        if self._repeat_mode == RepeatMode.OFF.value:
            self._engine.set_repeat_mode(RepeatMode.ALL.value)
            return
        if self._repeat_mode == RepeatMode.ALL.value:
            self._engine.set_repeat_mode(RepeatMode.ONE.value)
            return
        self._engine.set_repeat_mode(RepeatMode.OFF.value)

    def _on_now_playing_changed(self, track_obj: object) -> None:
        if not isinstance(track_obj, QueueTrack):
            self._title_label.setText("Nothing queued")
            return
        self._title_label.setText(f"{track_obj.artist} - {track_obj.title}")

    def _on_playback_state_changed(self, state: str) -> None:
        self._play_btn.setText("||" if state == "playing" else ">")

    def _on_position_changed(self, position_ms: int, duration_ms: int) -> None:
        self._seek.setMaximum(max(0, int(duration_ms)))
        if not self._seeking:
            self._seek.setValue(max(0, int(position_ms)))
        self._position_label.setText(_format_time(position_ms))
        self._duration_label.setText(_format_time(duration_ms))

    def _on_volume_changed(self, value: int, _muted: bool) -> None:
        blocked = self._volume.blockSignals(True)
        self._volume.setValue(int(value))
        self._volume.blockSignals(blocked)
        blocked_mute = self._mute_btn.blockSignals(True)
        self._mute_btn.setChecked(bool(_muted))
        self._mute_btn.blockSignals(blocked_mute)

    def _on_modes_changed(self, repeat_mode: str, shuffle_enabled: bool) -> None:
        self._repeat_mode = repeat_mode if repeat_mode in {
            RepeatMode.OFF.value,
            RepeatMode.ALL.value,
            RepeatMode.ONE.value,
        } else RepeatMode.OFF.value

        blocked_shuffle = self._shuffle_btn.blockSignals(True)
        self._shuffle_btn.setChecked(bool(shuffle_enabled))
        self._shuffle_btn.blockSignals(blocked_shuffle)
        self._shuffle_btn.setObjectName("TransportToggle" if shuffle_enabled else "TransportButton")
        self._shuffle_btn.style().unpolish(self._shuffle_btn)
        self._shuffle_btn.style().polish(self._shuffle_btn)

        if self._repeat_mode == RepeatMode.ALL.value:
            self._repeat_btn.setText("REP ALL")
        elif self._repeat_mode == RepeatMode.ONE.value:
            self._repeat_btn.setText("REP 1")
        else:
            self._repeat_btn.setText("REP OFF")
