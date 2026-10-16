"""Playback engine and queue state for the Pulse Player plugin."""

from __future__ import annotations

import os
import random
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from musicorg.core.tagger import TagManager
from musicorg.plugins.context import PluginContext
from musicorg.plugins.models import PluginCapability

SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac"}


class RepeatMode(str, Enum):
    OFF = "off"
    ALL = "all"
    ONE = "one"


@dataclass(frozen=True, slots=True)
class QueueTrack:
    path: Path
    title: str
    artist: str
    album: str
    duration_seconds: float
    artwork_data: bytes | None = None


class PlayerEngine(QObject):
    """Queue + playback behavior for the player plugin."""

    queue_changed = Signal(object)  # list[QueueTrack]
    now_playing_changed = Signal(object)  # QueueTrack | None
    position_changed = Signal(int, int)  # position_ms, duration_ms
    playback_state_changed = Signal(str)
    volume_changed = Signal(int, bool)  # volume_pct, muted
    modes_changed = Signal(str, bool)  # repeat_mode, shuffle_enabled

    _BACKEND_MPV = "mpv"
    _BACKEND_QT = "qt"

    def __init__(self, context: PluginContext, parent: QObject | None = None) -> None:
        super().__init__(parent)
        context.require_capability(PluginCapability.AUDIO_OUTPUT)
        self._context = context
        self._tagger = TagManager()

        self._queue: list[QueueTrack] = []
        self._current_index = -1
        self._loaded_index = -1
        self._duration_ms = 0
        self._position_ms = 0
        self._playback_state = "stopped"
        self._shuffle_enabled = self._coerce_bool_setting("shuffle_enabled", False)
        self._repeat_mode = self._coerce_repeat_mode(
            str(self._context.get_setting("repeat_mode", RepeatMode.OFF.value))
        )
        self._restore_queue_enabled = self._coerce_bool_setting("restore_queue", False)

        self._backend = self._BACKEND_QT
        self._mpv_error = ""
        self._mpv_player: Any | None = None
        self._mpv_end_guard = False
        self._dll_handles: list[object] = []
        self._qt_player: QMediaPlayer | None = None
        self._qt_audio_output: QAudioOutput | None = None

        self._mpv_poll_timer = QTimer(self)
        self._mpv_poll_timer.setInterval(220)
        self._mpv_poll_timer.timeout.connect(self._poll_mpv_state)

        self._init_playback_backend()

        self._set_volume(int(self._context.get_setting("volume", 70)), persist=False)
        self._set_muted(self._coerce_bool_setting("muted", False), persist=False)

        if self._restore_queue_enabled:
            self._restore_queue()
        self._emit_state_signals()

    def dispose(self) -> None:
        self.stop()
        self._mpv_poll_timer.stop()
        if self._backend == self._BACKEND_MPV and self._mpv_player is not None:
            try:
                self._mpv_player.terminate()
            except Exception:
                pass
            self._mpv_player = None
        self._queue.clear()
        self._current_index = -1
        self._loaded_index = -1
        self.now_playing_changed.emit(None)
        self.queue_changed.emit([])

    def add_selected_paths(self) -> int:
        paths = self._context.selected_paths()
        return self.add_paths(paths)

    def add_paths(self, paths: list[Path]) -> int:
        added_count = 0
        for path in paths:
            if not path.exists() or not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
                continue
            track = self._read_track(path)
            self._queue.append(track)
            added_count += 1
        if added_count <= 0:
            return 0
        if self._current_index < 0 and self._queue:
            self._current_index = 0
            self._load_current(auto_play=False)
        self._persist_queue()
        self.queue_changed.emit(list(self._queue))
        return added_count

    def clear_queue(self) -> None:
        self.stop()
        self._queue = []
        self._current_index = -1
        self._loaded_index = -1
        self._duration_ms = 0
        self._position_ms = 0
        self.queue_changed.emit([])
        self.now_playing_changed.emit(None)
        self.position_changed.emit(0, 0)
        self._persist_queue()

    def remove_indices(self, indices: list[int]) -> None:
        unique = sorted({idx for idx in indices if 0 <= idx < len(self._queue)}, reverse=True)
        if not unique:
            return
        for idx in unique:
            self._queue.pop(idx)
            if idx < self._current_index:
                self._current_index -= 1
            elif idx == self._current_index:
                self._current_index = min(self._current_index, len(self._queue) - 1)
                self._loaded_index = -1
        if not self._queue:
            self.stop()
            self._current_index = -1
            self._loaded_index = -1
            self.now_playing_changed.emit(None)
        else:
            self._load_current(auto_play=False)
        self._persist_queue()
        self.queue_changed.emit(list(self._queue))

    def move_up(self, index: int) -> int:
        if index <= 0 or index >= len(self._queue):
            return index
        self._queue[index - 1], self._queue[index] = self._queue[index], self._queue[index - 1]
        self._adjust_current_index_after_move(index, index - 1)
        self._persist_queue()
        self.queue_changed.emit(list(self._queue))
        return index - 1

    def move_down(self, index: int) -> int:
        if index < 0 or index >= len(self._queue) - 1:
            return index
        self._queue[index], self._queue[index + 1] = self._queue[index + 1], self._queue[index]
        self._adjust_current_index_after_move(index, index + 1)
        self._persist_queue()
        self.queue_changed.emit(list(self._queue))
        return index + 1

    def play_pause(self) -> None:
        if self._playback_state == "playing":
            self.pause()
            return
        self.play()

    def play(self) -> None:
        if not self._queue:
            self._context.show_status("Queue is empty", 1800)
            return
        if self._current_index < 0:
            self._current_index = 0
        if self._loaded_index != self._current_index:
            self._load_current(auto_play=True)
            return
        if self._backend == self._BACKEND_MPV:
            self._mpv_set_property("pause", False)
            self._set_playback_state("playing")
            return
        if self._qt_player is not None:
            self._qt_player.play()

    def pause(self) -> None:
        if self._backend == self._BACKEND_MPV:
            self._mpv_set_property("pause", True)
            self._set_playback_state("paused")
            return
        if self._qt_player is not None:
            self._qt_player.pause()

    def stop(self) -> None:
        if self._backend == self._BACKEND_MPV:
            if self._mpv_player is not None:
                try:
                    self._mpv_player.stop()
                except Exception:
                    pass
            self._position_ms = 0
            self._set_playback_state("stopped")
            self.position_changed.emit(0, int(self._duration_ms))
            return
        if self._qt_player is not None:
            self._qt_player.stop()

    def play_index(self, index: int) -> None:
        if not (0 <= index < len(self._queue)):
            return
        self._current_index = index
        self._loaded_index = -1
        self._load_current(auto_play=True)
        self._persist_queue()

    def next_track(self, *, manual: bool = True) -> None:
        next_index = self._compute_next_index(manual=manual)
        if next_index is None:
            self.stop()
            return
        self._current_index = next_index
        self._loaded_index = -1
        self._load_current(auto_play=True)
        self._persist_queue()

    def previous_track(self) -> None:
        if self._current_position_ms() > 3000:
            self.seek(0)
            return
        if not self._queue:
            return
        if self._current_index <= 0:
            if self._repeat_mode == RepeatMode.ALL:
                self._current_index = len(self._queue) - 1
            else:
                self._current_index = 0
        else:
            self._current_index -= 1
        self._loaded_index = -1
        self._load_current(auto_play=True)
        self._persist_queue()

    def seek(self, position_ms: int) -> None:
        safe_ms = max(0, int(position_ms))
        if self._backend == self._BACKEND_MPV:
            seconds = safe_ms / 1000.0
            if self._mpv_player is None:
                return
            try:
                self._mpv_player.seek(seconds, reference="absolute")
            except Exception:
                try:
                    self._mpv_player.command("seek", seconds, "absolute")
                except Exception:
                    return
            self._position_ms = safe_ms
            self.position_changed.emit(self._position_ms, self._duration_ms)
            return
        if self._qt_player is not None:
            self._qt_player.setPosition(safe_ms)

    def set_repeat_mode(self, mode: str) -> None:
        self._repeat_mode = self._coerce_repeat_mode(mode)
        self._context.set_setting("repeat_mode", self._repeat_mode.value)
        self.modes_changed.emit(self._repeat_mode.value, self._shuffle_enabled)

    def repeat_mode(self) -> RepeatMode:
        return self._repeat_mode

    def set_shuffle_enabled(self, enabled: bool) -> None:
        self._shuffle_enabled = bool(enabled)
        self._context.set_setting("shuffle_enabled", self._shuffle_enabled)
        self.modes_changed.emit(self._repeat_mode.value, self._shuffle_enabled)

    def shuffle_enabled(self) -> bool:
        return self._shuffle_enabled

    def set_restore_queue_enabled(self, enabled: bool) -> None:
        self._restore_queue_enabled = bool(enabled)
        self._context.set_setting("restore_queue", self._restore_queue_enabled)
        self._persist_queue()

    def restore_queue_enabled(self) -> bool:
        return self._restore_queue_enabled

    def set_volume(self, value: int) -> None:
        self._set_volume(value, persist=True)

    def set_muted(self, muted: bool) -> None:
        self._set_muted(muted, persist=True)

    def queue(self) -> list[QueueTrack]:
        return list(self._queue)

    def current_index(self) -> int:
        return self._current_index

    def backend_name(self) -> str:
        return self._backend

    def refresh_state(self) -> None:
        """Re-emit current engine state so newly attached UI reflects real values."""
        self._emit_state_signals()

    def _init_playback_backend(self) -> None:
        if self._init_mpv_backend():
            self._backend = self._BACKEND_MPV
            return
        self._backend = self._BACKEND_QT
        self._init_qt_backend()

    def _init_mpv_backend(self) -> bool:
        self._prepare_mpv_runtime_paths()
        try:
            import mpv  # type: ignore[import-not-found]
        except Exception as exc:
            self._mpv_error = str(exc)
            return False
        try:
            # Keep playback audio-only. We render UI artwork ourselves.
            self._mpv_player = mpv.MPV(video=False)
        except Exception as exc:
            self._mpv_error = str(exc)
            self._mpv_player = None
            return False
        self._mpv_poll_timer.start()
        return True

    def _init_qt_backend(self) -> None:
        self._qt_audio_output = QAudioOutput(self)
        self._qt_player = QMediaPlayer(self)
        self._qt_player.setAudioOutput(self._qt_audio_output)
        self._qt_player.positionChanged.connect(self._on_qt_position_changed)
        self._qt_player.durationChanged.connect(self._on_qt_duration_changed)
        self._qt_player.playbackStateChanged.connect(self._on_qt_playback_state_changed)
        self._qt_player.mediaStatusChanged.connect(self._on_qt_media_status_changed)

    def _prepare_mpv_runtime_paths(self) -> None:
        plugin_root = Path(__file__).resolve().parents[1]
        site_packages = plugin_root / "site-packages"
        if site_packages.exists() and site_packages.is_dir():
            site_packages_str = str(site_packages)
            if site_packages_str not in sys.path:
                sys.path.insert(0, site_packages_str)

        bin_dir = plugin_root / "bin"
        if not bin_dir.exists() or not bin_dir.is_dir():
            return

        if "MPV_DYLIB_PATH" not in os.environ:
            libmpv_path = self._find_libmpv_path(bin_dir)
            if libmpv_path is not None:
                os.environ["MPV_DYLIB_PATH"] = str(libmpv_path)

        # python-mpv on Windows resolves libmpv through %PATH%.
        bin_dir_str = str(bin_dir)
        current_path = os.environ.get("PATH", "")
        path_parts = current_path.split(os.pathsep) if current_path else []
        if bin_dir_str not in path_parts:
            os.environ["PATH"] = f"{bin_dir_str}{os.pathsep}{current_path}" if current_path else bin_dir_str

        if os.name != "nt":
            return
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is None:
            return
        try:
            handle = add_dll_directory(str(bin_dir))
        except OSError:
            return
        self._dll_handles.append(handle)

    @staticmethod
    def _find_libmpv_path(bin_dir: Path) -> Path | None:
        if sys.platform.startswith("win"):
            names = ("libmpv-2.dll", "libmpv.dll", "mpv-2.dll", "mpv-1.dll")
        elif sys.platform == "darwin":
            names = ("libmpv.dylib",)
        else:
            names = ("libmpv.so", "libmpv.so.2", "libmpv.so.1")
        for name in names:
            candidate = bin_dir / name
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _load_current(self, *, auto_play: bool) -> None:
        if not (0 <= self._current_index < len(self._queue)):
            self.now_playing_changed.emit(None)
            return
        track = self._queue[self._current_index]
        self._duration_ms = max(0, int(track.duration_seconds * 1000))
        self._position_ms = 0
        self.now_playing_changed.emit(track)
        self.position_changed.emit(0, self._duration_ms)

        if self._backend == self._BACKEND_MPV:
            self._mpv_play_file(track.path, pause=not auto_play)
            self._loaded_index = self._current_index
            self._set_playback_state("playing" if auto_play else "paused")
            return

        if self._qt_player is not None:
            self._qt_player.setSource(QUrl.fromLocalFile(str(track.path)))
            self._loaded_index = self._current_index
            if auto_play:
                self._qt_player.play()
            else:
                self._qt_player.pause()

    def _mpv_play_file(self, path: Path, *, pause: bool) -> None:
        player = self._mpv_player
        if player is None:
            return
        try:
            player.play(str(path))
        except Exception:
            try:
                player.command("loadfile", str(path), "replace")
            except Exception:
                return
        self._mpv_set_property("pause", pause)

    def _read_track(self, path: Path) -> QueueTrack:
        tags = self._tagger.read(path)
        title = tags.title or path.stem
        artist = tags.artist or tags.albumartist or "Unknown Artist"
        album = tags.album or "Unknown Album"
        return QueueTrack(
            path=path,
            title=title,
            artist=artist,
            album=album,
            duration_seconds=max(0.0, float(tags.duration or 0.0)),
            artwork_data=tags.artwork_data if tags.artwork_data else None,
        )

    def _compute_next_index(self, *, manual: bool) -> int | None:
        if not self._queue:
            return None
        if self._shuffle_enabled and len(self._queue) > 1:
            candidates = [idx for idx in range(len(self._queue)) if idx != self._current_index]
            return random.choice(candidates)
        if not manual and self._repeat_mode == RepeatMode.ONE:
            return self._current_index if self._current_index >= 0 else 0
        next_index = self._current_index + 1
        if next_index < len(self._queue):
            return next_index
        if self._repeat_mode == RepeatMode.ALL:
            return 0
        return None

    def _adjust_current_index_after_move(self, old_index: int, new_index: int) -> None:
        if self._current_index == old_index:
            self._current_index = new_index
            self._loaded_index = -1
            return
        if old_index < self._current_index <= new_index:
            self._current_index -= 1
            self._loaded_index = -1
            return
        if new_index <= self._current_index < old_index:
            self._current_index += 1
            self._loaded_index = -1

    def _persist_queue(self) -> None:
        if not self._restore_queue_enabled:
            self._context.set_setting("queue_paths", [])
            self._context.set_setting("queue_index", -1)
            return
        self._context.set_setting("queue_paths", [str(track.path) for track in self._queue])
        self._context.set_setting("queue_index", self._current_index)

    def _restore_queue(self) -> None:
        raw = self._context.get_setting("queue_paths", [])
        if not isinstance(raw, list):
            return
        restored_paths = [Path(str(item)) for item in raw]
        self.add_paths(restored_paths)
        index_raw = self._context.get_setting("queue_index", -1)
        try:
            index = int(index_raw)
        except (TypeError, ValueError):
            index = -1
        if 0 <= index < len(self._queue):
            self._current_index = index
            self._loaded_index = -1
            self._load_current(auto_play=False)

    def _coerce_repeat_mode(self, value: str) -> RepeatMode:
        lowered = (value or "").strip().lower()
        if lowered == RepeatMode.ALL.value:
            return RepeatMode.ALL
        if lowered == RepeatMode.ONE.value:
            return RepeatMode.ONE
        return RepeatMode.OFF

    def _coerce_bool_setting(self, key: str, default: bool) -> bool:
        raw = self._context.get_setting(key, default)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return bool(raw) if raw is not None else default

    def _set_volume(self, value: int, *, persist: bool) -> None:
        clamped = max(0, min(100, int(value)))
        if self._backend == self._BACKEND_MPV:
            self._mpv_set_property("volume", float(clamped))
            muted = self._mpv_property_bool("mute", False)
            if persist:
                self._context.set_setting("volume", clamped)
            self.volume_changed.emit(clamped, muted)
            return

        if self._qt_audio_output is not None:
            self._qt_audio_output.setVolume(clamped / 100.0)
            muted = self._qt_audio_output.isMuted()
        else:
            muted = False
        if persist:
            self._context.set_setting("volume", clamped)
        self.volume_changed.emit(clamped, muted)

    def _set_muted(self, muted: bool, *, persist: bool) -> None:
        if self._backend == self._BACKEND_MPV:
            self._mpv_set_property("mute", bool(muted))
            volume = int(round(self._mpv_property_float("volume", 100.0)))
            if persist:
                self._context.set_setting("muted", bool(muted))
            self.volume_changed.emit(volume, bool(muted))
            return

        if self._qt_audio_output is not None:
            self._qt_audio_output.setMuted(bool(muted))
            volume = int(round(self._qt_audio_output.volume() * 100))
            real_muted = self._qt_audio_output.isMuted()
        else:
            volume = 100
            real_muted = bool(muted)
        if persist:
            self._context.set_setting("muted", bool(muted))
        self.volume_changed.emit(volume, real_muted)

    def _poll_mpv_state(self) -> None:
        if self._backend != self._BACKEND_MPV or self._mpv_player is None:
            return
        self._position_ms = max(0, int(self._mpv_property_float("time-pos", 0.0) * 1000))
        duration = max(0, int(self._mpv_property_float("duration", 0.0) * 1000))
        if duration > 0:
            self._duration_ms = duration
        self.position_changed.emit(self._position_ms, self._duration_ms)

        idle = self._mpv_property_bool("idle-active", False)
        paused = self._mpv_property_bool("pause", False)
        state = "stopped" if idle else ("paused" if paused else "playing")
        self._set_playback_state(state)

        if (
            state == "playing"
            and self._duration_ms > 0
            and self._position_ms >= (self._duration_ms - 180)
        ):
            if not self._mpv_end_guard:
                self._mpv_end_guard = True
                self.next_track(manual=False)
                return
        else:
            self._mpv_end_guard = False

    def _mpv_get_property(self, name: str) -> Any:
        player = self._mpv_player
        if player is None:
            return None
        attr_name = name.replace("-", "_")
        try:
            return getattr(player, attr_name)
        except Exception:
            pass
        try:
            return player.command("get_property", name)
        except Exception:
            return None

    def _mpv_set_property(self, name: str, value: Any) -> None:
        player = self._mpv_player
        if player is None:
            return
        attr_name = name.replace("-", "_")
        try:
            setattr(player, attr_name, value)
            return
        except Exception:
            pass
        try:
            player.command("set_property", name, value)
        except Exception:
            return

    def _mpv_property_float(self, name: str, default: float) -> float:
        raw = self._mpv_get_property(name)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float(default)

    def _mpv_property_bool(self, name: str, default: bool) -> bool:
        raw = self._mpv_get_property(name)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in {"yes", "true", "1", "on"}:
                return True
            if lowered in {"no", "false", "0", "off"}:
                return False
        return default

    def _current_position_ms(self) -> int:
        if self._backend == self._BACKEND_MPV:
            return int(self._position_ms)
        if self._qt_player is None:
            return 0
        return int(self._qt_player.position())

    def _set_playback_state(self, value: str) -> None:
        normalized = value if value in {"playing", "paused", "stopped"} else "stopped"
        if normalized == self._playback_state:
            return
        self._playback_state = normalized
        self.playback_state_changed.emit(normalized)

    def _on_qt_position_changed(self, position: int) -> None:
        self._position_ms = max(0, int(position))
        self.position_changed.emit(self._position_ms, int(self._duration_ms))

    def _on_qt_duration_changed(self, duration: int) -> None:
        self._duration_ms = max(0, int(duration))
        current = int(self._qt_player.position()) if self._qt_player is not None else self._position_ms
        self.position_changed.emit(current, self._duration_ms)

    def _on_qt_playback_state_changed(self, _state: QMediaPlayer.PlaybackState) -> None:
        if self._qt_player is None:
            self._set_playback_state("stopped")
            return
        state = self._qt_player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._set_playback_state("playing")
            return
        if state == QMediaPlayer.PlaybackState.PausedState:
            self._set_playback_state("paused")
            return
        self._set_playback_state("stopped")

    def _on_qt_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if self._qt_player is None:
            return
        if status in {
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        }:
            # MP3s may contain attached-picture streams; keep playback audio-only.
            try:
                self._qt_player.setActiveVideoTrack(-1)
                self._qt_player.setActiveSubtitleTrack(-1)
            except Exception:
                pass
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.next_track(manual=False)

    def _emit_state_signals(self) -> None:
        self.queue_changed.emit(list(self._queue))
        current = self._queue[self._current_index] if 0 <= self._current_index < len(self._queue) else None
        self.now_playing_changed.emit(current)
        if self._backend == self._BACKEND_QT and self._qt_player is not None:
            self._position_ms = int(self._qt_player.position())
        self.position_changed.emit(self._position_ms, int(self._duration_ms))
        self.playback_state_changed.emit(self._playback_state)

        if self._backend == self._BACKEND_MPV:
            volume = int(round(self._mpv_property_float("volume", 100.0)))
            muted = self._mpv_property_bool("mute", False)
        elif self._qt_audio_output is not None:
            volume = int(round(self._qt_audio_output.volume() * 100))
            muted = self._qt_audio_output.isMuted()
        else:
            volume = 100
            muted = False
        self.volume_changed.emit(volume, muted)
        self.modes_changed.emit(self._repeat_mode.value, self._shuffle_enabled)
