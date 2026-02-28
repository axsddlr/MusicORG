"""Common utilities for UI components."""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtCore import SignalInstance


def safe_disconnect(signal: SignalInstance, slot: Optional[Callable] = None) -> bool:
    """Safely disconnect a signal from a slot.
    
    Args:
        signal: The Qt signal to disconnect from.
        slot: The slot/callable to disconnect. If None, disconnects all slots.
    
    Returns:
        True if disconnection succeeded or was unnecessary, False if it failed.
    
    Usage:
        safe_disconnect(worker.progress, self._on_progress)
        safe_disconnect(worker.finished)  # Disconnect all slots
    """
    try:
        if slot is not None:
            signal.disconnect(slot)
        else:
            signal.disconnect()
        return True
    except (RuntimeError, TypeError):
        # Signal/slot already disconnected or invalid
        return False


def safe_disconnect_multiple(
    connections: list[tuple[SignalInstance, Optional[Callable]]]
) -> None:
    """Safely disconnect multiple signal/slot pairs.
    
    Args:
        connections: List of (signal, slot) tuples. Slot can be None to disconnect all.
    
    Usage:
        safe_disconnect_multiple([
            (worker.progress, self._on_progress),
            (worker.finished, self._on_finished),
            (worker.error, self._on_error),
        ])
    """
    for signal, slot in connections:
        safe_disconnect(signal, slot)
