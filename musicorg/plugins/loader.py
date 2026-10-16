"""Plugin package discovery, validation, and module loading."""

from __future__ import annotations

import importlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Mapping

from musicorg.plugins.models import (
    PluginDescriptor,
    PluginManifest,
    PluginValidationError,
    coerce_capabilities,
    to_mapping,
)

PLUGIN_SCHEMA_VERSION = "1"

_PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")
_ENTRYPOINT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_SHORT_FIELD_LEN = 120
_MAX_DESC_LEN = 400
_MAX_PLUGIN_ID_LEN = 64


@dataclass(frozen=True, slots=True)
class PluginSearchRoot:
    """Search root metadata for discovery precedence and source labeling."""

    path: Path
    is_builtin: bool


class PluginLoader:
    """Load plugin manifests and entrypoints from search roots."""

    def __init__(self, roots: list[PluginSearchRoot], *, allow_symlinks: bool = False) -> None:
        self._roots = roots
        self._allow_symlinks = allow_symlinks
        self._dll_dir_handles: list[object] = []

    def discover(self) -> tuple[list[PluginDescriptor], list[str]]:
        discovered: dict[str, PluginDescriptor] = {}
        errors: list[str] = []

        for root in self._roots:
            root_path = root.path
            if not root_path.exists():
                if not root.is_builtin:
                    root_path.mkdir(parents=True, exist_ok=True)
                else:
                    continue
            if not root_path.is_dir():
                errors.append(f"Plugin root is not a directory: {root_path}")
                continue

            for plugin_dir in sorted(root_path.iterdir(), key=lambda p: p.name.lower()):
                if not plugin_dir.is_dir():
                    continue
                try:
                    descriptor = self._load_descriptor(plugin_dir, is_builtin=root.is_builtin)
                except PluginValidationError as exc:
                    errors.append(str(exc))
                    continue

                plugin_id = descriptor.manifest.plugin_id
                existing = discovered.get(plugin_id)
                if existing is None:
                    discovered[plugin_id] = descriptor
                    continue
                # User plugins can override built-ins with the same plugin_id.
                if existing.is_builtin and not descriptor.is_builtin:
                    discovered[plugin_id] = descriptor
                    errors.append(
                        f"Plugin {plugin_id!r} from {descriptor.source_dir} overrides "
                        f"built-in plugin at {existing.source_dir}"
                    )
                    continue
                errors.append(
                    f"Duplicate plugin_id {plugin_id!r}; keeping {existing.source_dir}, "
                    f"ignoring {descriptor.source_dir}"
                )

        ordered = sorted(discovered.values(), key=lambda d: d.manifest.name.lower())
        return ordered, errors

    def load_entrypoint(self, descriptor: PluginDescriptor) -> object:
        module = self._import_entry_module(descriptor)
        class_name = descriptor.entry_class
        plugin_cls = getattr(module, class_name, None)
        if plugin_cls is None:
            raise PluginValidationError(
                f"{descriptor.source_dir}: entrypoint class {class_name!r} not found"
            )
        try:
            instance = plugin_cls()
        except Exception as exc:
            raise PluginValidationError(
                f"{descriptor.source_dir}: failed instantiating {class_name}: {exc}"
            ) from exc
        return instance

    def _load_descriptor(self, plugin_dir: Path, *, is_builtin: bool) -> PluginDescriptor:
        if plugin_dir.is_symlink() and not self._allow_symlinks:
            raise PluginValidationError(f"{plugin_dir}: symlink plugins are not allowed")
        manifest = self._parse_manifest(self._load_json(plugin_dir / "manifest.json"), plugin_dir)
        module_name, class_name = self._parse_entrypoint(manifest.entrypoint, plugin_dir)
        module_path = plugin_dir / (module_name.replace(".", "/") + ".py")
        if not module_path.exists():
            raise PluginValidationError(
                f"{plugin_dir}: entry module file not found for {module_name!r}"
            )
        if module_path.is_symlink() and not self._allow_symlinks:
            raise PluginValidationError(f"{plugin_dir}: entry module may not be a symlink")
        return PluginDescriptor(
            manifest=manifest,
            source_dir=plugin_dir,
            entry_module=module_name,
            entry_class=class_name,
            is_builtin=is_builtin,
        )

    def _import_entry_module(self, descriptor: PluginDescriptor) -> ModuleType:
        self._activate_plugin_runtime_paths(descriptor.source_dir)
        source_root = str(descriptor.source_dir)
        if source_root not in sys.path:
            sys.path.insert(0, source_root)
        importlib.invalidate_caches()
        # Ensure plugin reloads pick up current files.
        package_root = descriptor.entry_module.split(".", 1)[0]
        stale_modules = [
            name
            for name in list(sys.modules.keys())
            if name == package_root or name.startswith(f"{package_root}.")
        ]
        for name in stale_modules:
            sys.modules.pop(name, None)
        try:
            module = importlib.import_module(descriptor.entry_module)
        except Exception as exc:
            raise PluginValidationError(
                f"{descriptor.source_dir}: failed importing plugin module {descriptor.entry_module!r}: {exc}"
            ) from exc
        return module

    def _activate_plugin_runtime_paths(self, plugin_root: Path) -> None:
        """Activate plugin-local Python/native dependency paths before import."""
        site_packages = plugin_root / "site-packages"
        if site_packages.exists() and site_packages.is_dir():
            site_packages_str = str(site_packages)
            if site_packages_str not in sys.path:
                sys.path.insert(0, site_packages_str)

        bin_dir = plugin_root / "bin"
        if not bin_dir.exists() or not bin_dir.is_dir():
            return

        # Hint mpv bindings where a bundled libmpv can be found.
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
        add_dll_dir = getattr(os, "add_dll_directory", None)
        if add_dll_dir is None:
            return
        try:
            handle = add_dll_dir(str(bin_dir))
        except OSError:
            return
        self._dll_dir_handles.append(handle)

    @staticmethod
    def _find_libmpv_path(bin_dir: Path) -> Path | None:
        candidates: tuple[str, ...]
        if sys.platform.startswith("win"):
            candidates = ("libmpv-2.dll", "libmpv.dll", "mpv-2.dll", "mpv-1.dll")
        elif sys.platform == "darwin":
            candidates = ("libmpv.dylib",)
        else:
            candidates = ("libmpv.so", "libmpv.so.2", "libmpv.so.1")
        for name in candidates:
            candidate = bin_dir / name
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _load_json(self, path: Path) -> Mapping[str, object]:
        if not path.exists():
            raise PluginValidationError(f"{path.parent}: missing required file {path.name}")
        if path.is_symlink() and not self._allow_symlinks:
            raise PluginValidationError(f"{path}: symlink files are not allowed")
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise PluginValidationError(f"Could not stat {path}: {exc}") from exc
        if size > _MAX_MANIFEST_BYTES:
            raise PluginValidationError(f"{path}: file exceeds max size ({_MAX_MANIFEST_BYTES} bytes)")
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise PluginValidationError(f"Unable to read {path}: {exc}") from exc
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise PluginValidationError(f"Invalid JSON in {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise PluginValidationError(f"{path}: expected JSON object")
        return data

    def _parse_manifest(self, data: Mapping[str, object], plugin_dir: Path) -> PluginManifest:
        self._reject_unknown_keys(
            data,
            {
                "schema_version",
                "plugin_id",
                "name",
                "version",
                "author",
                "description",
                "target_app_min",
                "entrypoint",
                "capabilities",
                "ui",
            },
            f"{plugin_dir}/manifest.json",
        )

        schema_version = self._required_str(data, "schema_version", plugin_dir, max_len=8)
        if schema_version != PLUGIN_SCHEMA_VERSION:
            raise PluginValidationError(
                f"{plugin_dir}: unsupported schema_version {schema_version!r}; "
                f"expected {PLUGIN_SCHEMA_VERSION!r}"
            )

        plugin_id = self._required_str(data, "plugin_id", plugin_dir, max_len=_MAX_PLUGIN_ID_LEN)
        if len(plugin_id) > _MAX_PLUGIN_ID_LEN:
            raise PluginValidationError(f"{plugin_dir}: plugin_id too long")
        if not _PLUGIN_ID_RE.match(plugin_id):
            raise PluginValidationError(
                f"{plugin_dir}: plugin_id must match [a-z0-9-], got {plugin_id!r}"
            )

        version = self._required_str(data, "version", plugin_dir, max_len=40)
        target_app_min = self._required_str(data, "target_app_min", plugin_dir, max_len=40)
        entrypoint = self._required_str(data, "entrypoint", plugin_dir, max_len=180)
        if not _SEMVER_RE.match(version):
            raise PluginValidationError(f"{plugin_dir}: version must be semver-like, got {version!r}")
        if not _SEMVER_RE.match(target_app_min):
            raise PluginValidationError(
                f"{plugin_dir}: target_app_min must be semver-like, got {target_app_min!r}"
            )
        if not _ENTRYPOINT_RE.match(entrypoint):
            raise PluginValidationError(
                f"{plugin_dir}: entrypoint must look like module:Class, got {entrypoint!r}"
            )

        raw_capabilities = data.get("capabilities")
        if not isinstance(raw_capabilities, list):
            raise PluginValidationError(f"{plugin_dir}: capabilities must be an array")
        capability_values: list[str] = []
        for value in raw_capabilities:
            if not isinstance(value, str) or not value.strip():
                raise PluginValidationError(
                    f"{plugin_dir}: capabilities must contain non-empty strings"
                )
            capability_values.append(value.strip())
        capabilities = coerce_capabilities(capability_values)

        return PluginManifest(
            schema_version=schema_version,
            plugin_id=plugin_id,
            name=self._required_str(data, "name", plugin_dir, max_len=_MAX_SHORT_FIELD_LEN),
            version=version,
            author=self._required_str(data, "author", plugin_dir, max_len=_MAX_SHORT_FIELD_LEN),
            description=self._required_str(data, "description", plugin_dir, max_len=_MAX_DESC_LEN),
            target_app_min=target_app_min,
            entrypoint=entrypoint,
            capabilities=capabilities,
            ui=to_mapping(data.get("ui")),
        )

    @staticmethod
    def _parse_entrypoint(entrypoint: str, plugin_dir: Path) -> tuple[str, str]:
        if ":" not in entrypoint:
            raise PluginValidationError(
                f"{plugin_dir}: entrypoint must include ':' separator, got {entrypoint!r}"
            )
        module_name, class_name = entrypoint.split(":", 1)
        module_name = module_name.strip()
        class_name = class_name.strip()
        if not module_name or not class_name:
            raise PluginValidationError(
                f"{plugin_dir}: invalid entrypoint {entrypoint!r}; expected module:Class"
            )
        return module_name, class_name

    @staticmethod
    def _required_str(
        data: Mapping[str, object],
        key: str,
        plugin_dir: Path,
        *,
        max_len: int,
    ) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise PluginValidationError(f"{plugin_dir}: field {key!r} must be a non-empty string")
        cleaned = value.strip()
        if len(cleaned) > max_len:
            raise PluginValidationError(f"{plugin_dir}: field {key!r} exceeds max length {max_len}")
        if any(ch in cleaned for ch in ("\n", "\r", "\t")):
            raise PluginValidationError(
                f"{plugin_dir}: field {key!r} must be a single-line string"
            )
        return cleaned

    @staticmethod
    def _reject_unknown_keys(data: Mapping[str, object], allowed: set[str], context: str) -> None:
        unknown = sorted(key for key in data.keys() if key not in allowed)
        if unknown:
            joined = ", ".join(unknown)
            raise PluginValidationError(f"{context}: unsupported keys found: {joined}")
