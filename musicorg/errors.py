"""Error codes and error handling utilities for MusicOrg."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any


class ErrorCode(Enum):
    """Standardized error codes for MusicOrg operations."""
    
    # File system errors (1000-1999)
    FILE_NOT_FOUND = auto()
    FILE_ACCESS_DENIED = auto()
    FILE_LOCKED = auto()
    FILE_CORRUPT = auto()
    DISK_FULL = auto()
    PATH_INVALID = auto()
    
    # Tag errors (2000-2999)
    TAG_READ_FAILED = auto()
    TAG_WRITE_FAILED = auto()
    TAG_CORRUPT = auto()
    TAG_UNSUPPORTED_FORMAT = auto()
    TAG_MISSING_REQUIRED = auto()
    
    # Network errors (3000-3999)
    NETWORK_TIMEOUT = auto()
    NETWORK_UNAVAILABLE = auto()
    NETWORK_AUTH_FAILED = auto()
    NETWORK_NOT_FOUND = auto()
    NETWORK_RATE_LIMITED = auto()
    
    # Operation errors (4000-4999)
    OPERATION_CANCELLED = auto()
    OPERATION_FAILED = auto()
    OPERATION_PARTIAL = auto()
    
    # Configuration errors (5000-5999)
    CONFIG_INVALID = auto()
    CONFIG_MISSING = auto()
    CONFIG_PERMISSION_DENIED = auto()


ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.FILE_NOT_FOUND: "The file was not found. It may have been moved or deleted.",
    ErrorCode.FILE_ACCESS_DENIED: "Access denied. Check file permissions or if the file is read-only.",
    ErrorCode.FILE_LOCKED: "The file is locked. It may be open in another program.",
    ErrorCode.FILE_CORRUPT: "The file appears to be corrupt or incomplete.",
    ErrorCode.DISK_FULL: "The destination disk is full. Free up space and try again.",
    ErrorCode.PATH_INVALID: "The specified path is invalid or inaccessible.",
    
    ErrorCode.TAG_READ_FAILED: "Failed to read tags. The file format may not be supported.",
    ErrorCode.TAG_WRITE_FAILED: "Failed to write tags. The file may be locked or read-only.",
    ErrorCode.TAG_CORRUPT: "The tag metadata is corrupt. Try re-encoding the file.",
    ErrorCode.TAG_UNSUPPORTED_FORMAT: "This file format is not supported for tagging.",
    ErrorCode.TAG_MISSING_REQUIRED: "Required tag fields are missing.",
    
    ErrorCode.NETWORK_TIMEOUT: "Network request timed out. Check your internet connection.",
    ErrorCode.NETWORK_UNAVAILABLE: "Network unavailable. Check your internet connection.",
    ErrorCode.NETWORK_AUTH_FAILED: "Authentication failed. Check your API token in Preferences.",
    ErrorCode.NETWORK_NOT_FOUND: "No matching results found online.",
    ErrorCode.NETWORK_RATE_LIMITED: "Rate limited. Please wait a moment and try again.",
    
    ErrorCode.OPERATION_CANCELLED: "Operation was cancelled by user.",
    ErrorCode.OPERATION_FAILED: "Operation failed. See details for more information.",
    ErrorCode.OPERATION_PARTIAL: "Operation completed with some errors. Review the log.",
    
    ErrorCode.CONFIG_INVALID: "Configuration is invalid. Reset to defaults?",
    ErrorCode.CONFIG_MISSING: "Configuration file not found. Using defaults.",
    ErrorCode.CONFIG_PERMISSION_DENIED: "Cannot save configuration. Check folder permissions.",
}


@dataclass
class MusicOrgError(Exception):
    """Base exception for MusicOrg with error code and context."""
    
    code: ErrorCode
    message: str = ""
    path: Path | None = None
    details: dict[str, Any] = field(default_factory=dict)
    suggestion: str = ""
    
    def __post_init__(self) -> None:
        if not self.message:
            self.message = ERROR_MESSAGES.get(self.code, "An unexpected error occurred.")
        if not self.suggestion and self.code in ERROR_MESSAGES:
            self.suggestion = ERROR_MESSAGES[self.code]
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.path:
            parts.append(f"\nFile: {self.path}")
        if self.details:
            details_str = " | ".join(f"{k}={v}" for k, v in self.details.items())
            parts.append(f"\nDetails: {details_str}")
        return "".join(parts)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging or UI display."""
        return {
            "code": self.code.name,
            "message": self.message,
            "path": str(self.path) if self.path else None,
            "details": self.details,
            "suggestion": self.suggestion,
        }


def classify_exception(exc: Exception, path: Path | None = None) -> MusicOrgError:
    """Classify a generic exception into a MusicOrgError with appropriate code."""
    exc_name = type(exc).__name__
    exc_str = str(exc).lower()
    
    # File system errors
    if "FileNotFoundError" in exc_name or "no such file" in exc_str:
        return MusicOrgError(ErrorCode.FILE_NOT_FOUND, path=path, details={"original": exc_str})
    if "PermissionError" in exc_name or "access is denied" in exc_str or "permission denied" in exc_str:
        return MusicOrgError(ErrorCode.FILE_ACCESS_DENIED, path=path, details={"original": exc_str})
    if "locked" in exc_str or "in use" in exc_str:
        return MusicOrgError(ErrorCode.FILE_LOCKED, path=path, details={"original": exc_str})
    if "disk full" in exc_str or "no space left" in exc_str:
        return MusicOrgError(ErrorCode.DISK_FULL, path=path, details={"original": exc_str})
    
    # Network errors
    if "timeout" in exc_str:
        return MusicOrgError(ErrorCode.NETWORK_TIMEOUT, details={"original": exc_str})
    if "401" in exc_str or "unauthorized" in exc_str or "authentication" in exc_str:
        return MusicOrgError(ErrorCode.NETWORK_AUTH_FAILED, details={"original": exc_str})
    if "404" in exc_str or "not found" in exc_str:
        return MusicOrgError(ErrorCode.NETWORK_NOT_FOUND, details={"original": exc_str})
    if "429" in exc_str or "rate limit" in exc_str:
        return MusicOrgError(ErrorCode.NETWORK_RATE_LIMITED, details={"original": exc_str})
    if "network" in exc_str or "connection" in exc_str or "unreachable" in exc_str:
        return MusicOrgError(ErrorCode.NETWORK_UNAVAILABLE, details={"original": exc_str})
    
    # Tag errors - check for specific mutagen/music-tag errors
    if "HeaderNotFoundError" in exc_name or "sync" in exc_str or "frame" in exc_str:
        return MusicOrgError(ErrorCode.TAG_CORRUPT, path=path, details={"original": exc_str})
    if "NotImplementedError" in exc_name or "mutagen type" in exc_str or "not implemented" in exc_str:
        return MusicOrgError(ErrorCode.TAG_UNSUPPORTED_FORMAT, path=path, details={"original": exc_str})
    if "tag" in exc_str and "read" in exc_str:
        return MusicOrgError(ErrorCode.TAG_READ_FAILED, path=path, details={"original": exc_str})
    if "tag" in exc_str and "write" in exc_str:
        return MusicOrgError(ErrorCode.TAG_WRITE_FAILED, path=path, details={"original": exc_str})
    if "corrupt" in exc_str or "invalid" in exc_str:
        return MusicOrgError(ErrorCode.TAG_CORRUPT, path=path, details={"original": exc_str})
    
    # Default
    return MusicOrgError(
        ErrorCode.OPERATION_FAILED,
        message=f"{exc_name}: {exc}",
        path=path,
        details={"original": exc_str},
    )


def format_error_for_user(error: MusicOrgError | Exception) -> str:
    """Format an error for display to the user with actionable suggestions."""
    if isinstance(error, MusicOrgError):
        parts = [error.message]
        if error.suggestion and error.suggestion != error.message:
            parts.append(f"\n\n💡 {error.suggestion}")
        if error.path:
            parts.append(f"\n\nFile: {error.path.name}")
        return "".join(parts)
    
    # For generic exceptions, classify and format
    classified = classify_exception(error)
    return format_error_for_user(classified)
