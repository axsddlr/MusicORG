"""Spotify Audio Features panel for fetching energy/danceability/valence tags."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from musicorg.core.spotify_features import (
    SPOTIFY_FEATURE_NAMES,
    FEATURE_LABELS,
    SpotityFeaturesConfig,
)
from musicorg.ui.widgets.progress_bar import ProgressIndicator
from musicorg.ui.utils import safe_disconnect_multiple
from musicorg.workers.spotify_features_worker import SpotifyFeaturesWorker


class SpotifyFeaturesPanel(QDialog):
    tags_applied = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Spotify Audio Features")
        self.setMinimumSize(520, 420)
        self._files: list[Path] = []
        self._worker: SpotifyFeaturesWorker | None = None
        self._thread: QThread | None = None
        self._feature_checkboxes: dict[str, QCheckBox] = {}

        self._setup_ui()

    def load_files(self, paths: list[Path]) -> None:
        self._files = list(paths)
        self._update_label()

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
        self._cleanup_thread()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._files_label = QLabel("No files selected")
        layout.addWidget(self._files_label)

        auth_group = QGroupBox("Spotify API Credentials")
        auth_form = QFormLayout(auth_group)
        self._client_id_edit = QLineEdit()
        self._client_id_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._client_secret_edit = QLineEdit()
        self._client_secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        auth_form.addRow("Client ID:", self._client_id_edit)
        auth_form.addRow("Client Secret:", self._client_secret_edit)
        layout.addWidget(auth_group)

        features_group = QGroupBox("Audio Features to Fetch")
        features_layout = QVBoxLayout(features_group)
        for name, label in FEATURE_LABELS.items():
            cb = QCheckBox(label)
            cb.setChecked(name in {"danceability", "energy", "valence", "acousticness"})
            features_layout.addWidget(cb)
            self._feature_checkboxes[name] = cb
        layout.addWidget(features_group)

        search_group = QGroupBox("Matching Mode")
        search_layout = QVBoxLayout(search_group)
        self._isrc_checkbox = QCheckBox("Search by ISRC tag (preferred)")
        self._isrc_checkbox.setChecked(True)
        search_layout.addWidget(self._isrc_checkbox)
        self._artist_title_fallback = QCheckBox("Fallback to Artist + Title search")
        self._artist_title_fallback.setChecked(True)
        search_layout.addWidget(self._artist_title_fallback)
        layout.addWidget(search_group)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._fetch_btn = QPushButton("Fetch & Apply Audio Features")
        self._fetch_btn.setEnabled(False)
        self._fetch_btn.clicked.connect(self._fetch_features)
        self._fetch_btn.setStyleSheet("QPushButton { padding: 6px 24px; font-weight: bold; }")
        btn_layout.addWidget(self._fetch_btn)
        layout.addLayout(btn_layout)

        self._progress = ProgressIndicator()
        layout.addWidget(self._progress)

    def _update_label(self) -> None:
        self._files_label.setText(f"{len(self._files)} files selected")
        self._fetch_btn.setEnabled(bool(self._files and self._client_id_edit.text() and self._client_secret_edit.text()))

    def load_files(self, paths: list[Path]) -> None:
        self._files = list(paths)
        self._update_label()

    def _fetch_features(self) -> None:
        if not self._files:
            return

        config = SpotityFeaturesConfig(
            client_id=self._client_id_edit.text().strip(),
            client_secret=self._client_secret_edit.text().strip(),
            enabled_features=[
                name for name, cb in self._feature_checkboxes.items()
                if cb.isChecked()
            ],
            search_by_isrc=self._isrc_checkbox.isChecked(),
            use_artist_title_fallback=self._artist_title_fallback.isChecked(),
            feature_mappings=SpotityFeaturesConfig.DEFAULT_MAPPINGS,
        )

        self._cleanup_thread()
        self._worker = SpotifyFeaturesWorker(self._files, config)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(lambda c, t, m: self._progress.set_progress(c, t, m))
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.cancelled.connect(self._on_cancelled)
        self._thread.start()

    def _on_finished(self, result: dict) -> None:
        self._cleanup_thread()
        applied = result.get("applied", 0)
        total = result.get("total", 0)
        errors = result.get("errors", [])
        self._progress.set_progress(total, total, f"Applied features to {applied}/{total} files")
        self.tags_applied.emit()

    def _on_error(self, message: str) -> None:
        self._cleanup_thread()
        self._progress.set_progress(0, 1, f"Error: {message}")

    def _on_cancelled(self) -> None:
        self._cleanup_thread()
        self._progress.set_progress(0, 1, "Cancelled")

    def _cleanup_thread(self) -> None:
        if self._worker is not None:
            safe_disconnect_multiple(
                (self._worker.progress, lambda c, t, m: None),
                (self._worker.finished, self._on_finished),
                (self._worker.error, self._on_error),
                (self._worker.cancelled, self._on_cancelled),
            )
            self._worker = None
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None
