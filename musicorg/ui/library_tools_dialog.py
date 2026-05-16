"""Library analysis tools: statistics, health scan, and CSV export."""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from musicorg.core.library_db import LibraryDatabase


class LibraryToolsDialog(QDialog):
    """Library analysis: statistics, health scan, and export."""

    def __init__(self, library_db: LibraryDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Library Tools")
        self.resize(700, 500)
        self._db = library_db
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # Stats tab
        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        self._stats_text = QTextEdit()
        self._stats_text.setReadOnly(True)
        stats_layout.addWidget(self._stats_text)
        tabs.addTab(stats_tab, "Statistics")
        self._refresh_stats()

        # Health tab
        health_tab = QWidget()
        health_layout = QVBoxLayout(health_tab)
        self._health_table = QTableWidget(0, 3)
        self._health_table.setHorizontalHeaderLabels(["Issue", "Count", "Details"])
        self._health_table.horizontalHeader().setStretchLastSection(True)
        health_layout.addWidget(self._health_table)
        scan_btn = QPushButton("Run Health Scan")
        scan_btn.clicked.connect(self._run_health_scan)
        health_layout.addWidget(scan_btn)
        tabs.addTab(health_tab, "Health Scan")

        # Export tab
        export_tab = QWidget()
        export_layout = QVBoxLayout(export_tab)
        self._export_info = QLabel("Export all library tracks to CSV.")
        export_layout.addWidget(self._export_info)
        export_btn = QPushButton("Export to CSV...")
        export_btn.clicked.connect(self._export_csv)
        export_layout.addWidget(export_btn)
        export_layout.addStretch()
        tabs.addTab(export_tab, "Export")

        layout.addWidget(tabs)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _refresh_stats(self) -> None:
        db = self._db
        text = [
            f"Tracks: {db.total_tracks():,}",
            f"Albums: {db.total_albums():,}",
            f"Artists: {db.total_artists():,}",
            f"Total Duration: {db.total_duration() / 3600:.1f} hours",
            f"Total Size: {db.total_size() / (1024**3):.2f} GB",
            "",
        ]
        # Genre distribution
        conn = db._conn_or_raise()
        rows = conn.execute(
            "SELECT a.genre, COUNT(DISTINCT a.album_id) FROM albums a WHERE a.genre != '' GROUP BY a.genre ORDER BY COUNT(*) DESC LIMIT 15"
        ).fetchall()
        if rows:
            text.append("Top Genres:")
            for genre, count in rows:
                text.append(f"  {genre or 'Unknown'}: {count} albums")
            text.append("")

        # Format distribution
        rows = conn.execute(
            "SELECT format, COUNT(*) FROM tracks GROUP BY format ORDER BY COUNT(*) DESC"
        ).fetchall()
        if rows:
            text.append("Format Distribution:")
            for fmt, count in rows:
                text.append(f"  .{fmt}: {count:,} files")
            text.append("")

        # Year distribution
        rows = conn.execute(
            "SELECT year, COUNT(*) FROM albums WHERE year > 0 GROUP BY year ORDER BY year DESC LIMIT 10"
        ).fetchall()
        if rows:
            text.append("Recent Years:")
            for year, count in rows:
                text.append(f"  {year}: {count} albums")

        self._stats_text.setText("\n".join(text))

    def _run_health_scan(self) -> None:
        self._health_table.setRowCount(0)
        issues: list[tuple[str, str, str]] = []
        conn = self._db._conn_or_raise()

        # Corrupt/missing tags: tracks with empty title
        count = conn.execute(
            "SELECT COUNT(*) FROM tracks WHERE title = ''"
        ).fetchone()[0]
        if count:
            issues.append(("Missing Title", str(count), "Tracks with empty title field"))

        # Inconsistent album artists within albums
        rows = conn.execute(
            """SELECT a.title, ar.name, COUNT(DISTINCT t.artist)
               FROM tracks t
               JOIN albums a ON t.album_id = a.album_id
               JOIN artists ar ON a.artist_id = ar.artist_id
               GROUP BY a.album_id
               HAVING COUNT(DISTINCT t.artist) > 1
               LIMIT 20"""
        ).fetchall()
        if rows:
            for album, expected_artist, actual_count in rows:
                issues.append(
                    ("Mixed Artists",
                     str(actual_count),
                     f"'{album}' has {actual_count} artists (expected '{expected_artist}')")
                )

        # Low bitrate tracks (likely low quality)
        count = conn.execute(
            "SELECT COUNT(*) FROM tracks WHERE bitrate > 0 AND bitrate < 96"
        ).fetchone()[0]
        if count:
            issues.append(("Low Bitrate (<96kbps)", str(count), "May indicate low quality encodes"))

        # Missing artwork
        count = conn.execute(
            "SELECT COUNT(DISTINCT album_id) FROM tracks WHERE artwork_id IS NULL"
        ).fetchone()[0]
        if count:
            issues.append(("Albums Without Artwork", str(count), "No embedded cover art"))

        if not issues:
            issues.append(("No issues found", "0", "Library looks healthy"))

        self._health_table.setRowCount(len(issues))
        for i, (issue, count, detail) in enumerate(issues):
            self._health_table.setItem(i, 0, QTableWidgetItem(issue))
            self._health_table.setItem(i, 1, QTableWidgetItem(count))
            self._health_table.setItem(i, 2, QTableWidgetItem(detail))
        self._health_table.resizeColumnsToContents()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Library", "music_library.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        conn = self._db._conn_or_raise()
        rows = conn.execute(
            """SELECT t.path, t.title, t.artist, a.title, ar.name,
                      t.track_number, t.disc_number, a.year, a.genre,
                      t.duration, t.bitrate, t.format, t.file_size,
                      t.rating, t.play_count
               FROM tracks t
               JOIN albums a ON t.album_id = a.album_id
               JOIN artists ar ON a.artist_id = ar.artist_id
               ORDER BY ar.name, a.year, a.title, t.disc_number, t.track_number"""
        ).fetchall()
        fieldnames = [
            "path", "title", "artist", "album", "albumartist",
            "track", "disc", "year", "genre",
            "duration_s", "bitrate", "format", "size_bytes",
            "rating", "play_count",
        ]
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(fieldnames)
                for row in rows:
                    writer.writerow(row)
            self._export_info.setText(f"Exported {len(rows)} tracks to {path}")
        except Exception as e:
            self._export_info.setText(f"Export failed: {e}")