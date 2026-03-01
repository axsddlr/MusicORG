"""Common utilities for UI components."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import SignalInstance
from PySide6.QtWidgets import QLabel

from musicorg.core.autotagger import MatchCandidate


def safe_disconnect(signal: SignalInstance, slot: Optional[Callable] = None) -> None:
    """Safely disconnect a signal from a slot.
    
    Args:
        signal: The Qt signal to disconnect from.
        slot: The slot/callable to disconnect. If None, disconnects all slots.
    """
    try:
        if slot is not None:
            signal.disconnect(slot)
        else:
            signal.disconnect()
    except (RuntimeError, TypeError):
        pass  # Signal/slot already disconnected or invalid


def safe_disconnect_multiple(
    connections: list[tuple[SignalInstance, Optional[Callable]]]
) -> None:
    """Safely disconnect multiple signal/slot pairs.
    
    Args:
        connections: List of (signal, slot) tuples. Slot can be None to disconnect all.
    """
    for signal, slot in connections:
        safe_disconnect(signal, slot)


def format_file_size(size_bytes: int) -> str:
    """Format file size in bytes to human-readable string.
    
    Args:
        size_bytes: File size in bytes.
    
    Returns:
        Formatted string like "1.5 MB", "256 KB", or "100 B".
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def normalize_path(path: str) -> str:
    """Normalize a file path by resolving it.
    
    Args:
        path: File path string to normalize.
    
    Returns:
        Resolved path as string, or original if resolution fails.
    """
    try:
        return str(Path(path).resolve())
    except Exception:
        return str(Path(path))


def coerce_search_payload(
    payload: object,
) -> tuple[list[MatchCandidate], dict[str, str], dict[str, int]]:
    """Coerce and validate search result payloads from workers into typed tuples.
    
    Args:
        payload: Raw payload object from worker.
    
    Returns:
        Tuple of (candidates, source_errors, source_counts).
    """
    if not isinstance(payload, dict):
        return [], {}, {}

    candidates_obj = payload.get("candidates", [])
    source_errors_obj = payload.get("source_errors", {})
    source_counts_obj = payload.get("source_counts", {})

    candidates = [c for c in candidates_obj if isinstance(c, MatchCandidate)]
    source_errors: dict[str, str] = {}
    if isinstance(source_errors_obj, dict):
        source_errors = {
            str(source): str(message)
            for source, message in source_errors_obj.items()
        }
    source_counts: dict[str, int] = {}
    if isinstance(source_counts_obj, dict):
        for source, count in source_counts_obj.items():
            try:
                source_counts[str(source)] = max(0, int(count))
            except (TypeError, ValueError):
                continue
    return candidates, source_errors, source_counts


def format_source_errors(source_errors: dict[str, str]) -> str:
    """Format source error messages for display, truncating and normalizing common patterns.
    
    Args:
        source_errors: Dict mapping source name to error message.
    
    Returns:
        Formatted error string for display.
    """
    parts: list[str] = []
    for source, message in source_errors.items():
        normalized = " ".join(str(message).split())
        lowered = normalized.lower()
        if "forcibly closed" in lowered or "winerror 10054" in lowered:
            normalized = "connection reset by remote host"
        elif "timed out" in lowered or "timeout" in lowered:
            normalized = "request timed out"
        elif "http error 429" in lowered:
            normalized = "rate limited (HTTP 429)"
        elif "http error 503" in lowered:
            normalized = "service unavailable (HTTP 503)"
        if len(normalized) > 90:
            normalized = normalized[:87] + "..."
        parts.append(f"{source} unavailable: {normalized}")
    return "; ".join(parts)


def set_source_status_label(
    label: QLabel,
    source_counts: dict[str, int],
    source_errors: dict[str, str],
    candidates: list[MatchCandidate] | None = None,
) -> None:
    """Update a source status label showing MusicBrainz/Discogs availability and counts.
    
    Args:
        label: QLabel to update.
        source_counts: Dict mapping source name to result count.
        source_errors: Dict mapping source name to error message.
        candidates: Optional list of candidates to count if source_counts is empty.
    """
    source_names = ("MusicBrainz", "Discogs")
    counts: dict[str, int] = {name: 0 for name in source_names}
    for name in source_names:
        raw = source_counts.get(name, 0)
        try:
            counts[name] = max(0, int(raw))
        except (TypeError, ValueError):
            counts[name] = 0
    if not source_counts and candidates:
        for candidate in candidates:
            if candidate.source in counts:
                counts[candidate.source] += 1
    parts: list[str] = []
    for name in source_names:
        part = f"{name}: {counts[name]}"
        if name in source_errors:
            part += " (failed)"
        parts.append(part)
    label.setText(" | ".join(parts))
