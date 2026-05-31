"""Fetch Spotify Audio Features and map to configurable tags via thresholds."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from musicorg.core.tagger import TagData, TagManager

SPOTIFY_FEATURE_NAMES = (
    "danceability",
    "energy",
    "key",
    "loudness",
    "mode",
    "speechiness",
    "acousticness",
    "instrumentalness",
    "liveness",
    "valence",
    "tempo",
    "duration_ms",
    "time_signature",
)

FEATURE_LABELS: dict[str, str] = {
    "danceability": "Danceability",
    "energy": "Energy",
    "key": "Key",
    "loudness": "Loudness",
    "mode": "Mode",
    "speechiness": "Speechiness",
    "acousticness": "Acousticness",
    "instrumentalness": "Instrumentalness",
    "liveness": "Liveness",
    "valence": "Valence",
    "tempo": "Tempo (BPM)",
    "duration_ms": "Duration (ms)",
    "time_signature": "Time Signature",
}


@dataclass
class FeatureThreshold:
    """Maps a Spotify feature value range to a descriptive tag."""

    min_value: float = 0.0
    label: str = ""

    def matches(self, value: float) -> bool:
        return value >= self.min_value


@dataclass
class FeatureMapping:
    """Mapping of a Spotify feature to a target tag field with thresholds."""

    feature_name: str = ""
    tag_field: str = ""  # e.g. "comment", "genre", "mood"
    thresholds: list[FeatureThreshold] = field(default_factory=list)
    include_raw_value: bool = False

    def resolve(self, value: float) -> str:
        parts: list[str] = []
        for thresh in sorted(
            self.thresholds, key=lambda t: t.min_value, reverse=True
        ):
            if value >= thresh.min_value:
                parts.append(thresh.label)
                break
        if self.include_raw_value:
            formatted = f"{round(value * 100)}%"
            parts.append(formatted)
        return "; ".join(parts)


@dataclass
class SpotityFeaturesConfig:
    """User configuration for Spotify Audio Features tagging."""

    client_id: str = ""
    client_secret: str = ""
    enabled_features: list[str] = field(default_factory=list)
    feature_mappings: list[FeatureMapping] = field(default_factory=list)
    search_by_isrc: bool = True
    use_artist_title_fallback: bool = True

    DEFAULT_MAPPINGS: tuple[FeatureMapping, ...] = (
        FeatureMapping(
            feature_name="danceability",
            tag_field="comment",
            thresholds=[
                FeatureThreshold(0.7, "very danceable"),
                FeatureThreshold(0.3, "danceable"),
                FeatureThreshold(0.0, "not danceable"),
            ],
        ),
        FeatureMapping(
            feature_name="energy",
            tag_field="comment",
            thresholds=[
                FeatureThreshold(0.7, "high energy"),
                FeatureThreshold(0.3, "medium energy"),
                FeatureThreshold(0.0, "low energy"),
            ],
        ),
        FeatureMapping(
            feature_name="valence",
            tag_field="comment",
            thresholds=[
                FeatureThreshold(0.7, "happy"),
                FeatureThreshold(0.3, "neutral"),
                FeatureThreshold(0.0, "sad"),
            ],
        ),
        FeatureMapping(
            feature_name="acousticness",
            tag_field="comment",
            thresholds=[
                FeatureThreshold(0.5, "acoustic"),
            ],
        ),
        FeatureMapping(
            feature_name="instrumentalness",
            tag_field="comment",
            thresholds=[
                FeatureThreshold(0.5, "instrumental"),
            ],
        ),
    )


class SpotifyFeaturesFetcher:
    """Fetches audio features from Spotify and returns resolved tag values."""

    def __init__(self, client_id: str = "", client_secret: str = "") -> None:
        self._client_id = client_id.strip()
        self._client_secret = client_secret.strip()
        self._sp: Any = None

    def _ensure_authenticated(self) -> Any:
        if self._sp is not None:
            return self._sp
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials

        auth = SpotifyClientCredentials(
            client_id=self._client_id,
            client_secret=self._client_secret,
        )
        self._sp = spotipy.Spotify(auth_manager=auth)
        return self._sp

    def fetch_by_isrc(self, isrc: str, feature_names: list[str]) -> dict[str, Any] | None:
        sp = self._ensure_authenticated()
        if not isrc:
            return None
        try:
            results = sp.search(q=f"isrc:{isrc}", type="track", limit=1)
        except Exception:
            return None
        tracks = results.get("tracks", {}).get("items", [])
        if not tracks:
            return None
        track_id = tracks[0].get("id", "")
        return self._fetch_features(track_id, feature_names)

    def fetch_by_artist_title(
        self, artist: str, title: str, feature_names: list[str]
    ) -> dict[str, Any] | None:
        sp = self._ensure_authenticated()
        q_parts = []
        if artist:
            q_parts.append(f"artist:{artist}")
        if title:
            q_parts.append(f"track:{title}")
        if not q_parts:
            return None
        try:
            results = sp.search(q=" ".join(q_parts), type="track", limit=1)
        except Exception:
            return None
        tracks = results.get("tracks", {}).get("items", [])
        if not tracks:
            return None
        track_id = tracks[0].get("id", "")
        return self._fetch_features(track_id, feature_names)

    def _fetch_features(
        self, track_id: str, feature_names: list[str]
    ) -> dict[str, Any] | None:
        if not track_id:
            return None
        sp = self._ensure_authenticated()
        try:
            features = sp.audio_features([track_id])
        except Exception:
            return None
        if not features or features[0] is None:
            return None
        full = features[0]
        result: dict[str, Any] = {}
        valid = set(feature_names)
        for name in SPOTIFY_FEATURE_NAMES:
            if name in valid and name in full:
                result[name] = full[name]
        return result if result else None

    def resolve_tags(
        self,
        features: dict[str, Any],
        config: SpotityFeaturesConfig,
    ) -> dict[str, str]:
        resolved: dict[str, str] = {}
        for mapping in config.feature_mappings:
            value = features.get(mapping.feature_name, None)
            if value is None:
                continue
            resolved[mapping.tag_field] = mapping.resolve(float(value))
        return resolved

    def apply_to_file(
        self,
        path: str | Path,
        config: SpotityFeaturesConfig,
    ) -> bool:
        path = Path(path)
        tm = TagManager()
        try:
            tags = tm.read(path)
        except Exception:
            return False

        features = None
        isrc = ""
        if config.search_by_isrc:
            isrc = tm.read_custom_tag(path, "isrc") or ""
            if isrc:
                features = self.fetch_by_isrc(
                    isrc, [m.feature_name for m in config.feature_mappings]
                )
        if features is None and config.use_artist_title_fallback:
            features = self.fetch_by_artist_title(
                tags.artist,
                tags.title,
                [m.feature_name for m in config.feature_mappings],
            )
        if features is None:
            return False

        resolved = self.resolve_tags(features, config)
        if not resolved:
            return False

        tag_data = TagData(
            title=tags.title,
            artist=tags.artist,
            album=tags.album,
            albumartist=tags.albumartist,
            track=tags.track,
            disc=tags.disc,
            year=tags.year,
            genre=tags.genre,
            composer=tags.composer,
            comment=resolved.get("comment", tags.comment),
            lyrics=tags.lyrics,
        )
        tm.write(path, tag_data)
        return True
