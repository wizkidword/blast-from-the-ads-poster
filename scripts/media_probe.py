"""Inspect actual local media before the workflow spends time or writes output."""
from __future__ import annotations

import json
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class MediaProbeError(ValueError):
    """Raised when a path cannot be identified as valid image or video media."""


class MediaValidationError(MediaProbeError):
    """Raised when valid media exceeds the conservative local-workflow limits."""


@dataclass(frozen=True)
class MediaLimits:
    max_file_bytes: int = 1_000_000_000
    max_image_pixels: int = 40_000_000
    max_image_dimension: int = 10_000
    max_video_duration_seconds: int = 900
    max_carousel_images: int = 20
    max_analysis_payload_bytes: int = 100_000_000
    allow_animated_images: bool = False


@dataclass(frozen=True)
class MediaMetadata:
    path: Path
    actual_type: str
    format_name: str
    width: int | None
    height: int | None
    duration_seconds: float | None
    codec: str | None
    stream_count: int
    has_audio: bool
    audio_codec: str | None
    byte_size: int
    animated: bool
    extension_matches: bool


@dataclass(frozen=True)
class MediaPreflightIssue:
    path: Path
    message: str


@dataclass(frozen=True)
class MediaPreflightReport:
    accepted: tuple[MediaMetadata, ...]
    rejected: tuple[MediaPreflightIssue, ...]


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def is_candidate_media_file(path: Path) -> bool:
    """Use the filename as a cheap first filter, then accept recognizable media signatures."""

    candidate = Path(path)
    return candidate.suffix.lower() in _IMAGE_SUFFIXES | _VIDEO_SUFFIXES or _signature_kind(candidate) is not None


def limits_from_settings(settings) -> MediaLimits:
    """Build the probe policy from the app's validated, non-secret settings."""

    return MediaLimits(
        max_file_bytes=settings.max_media_file_bytes,
        max_image_pixels=settings.max_image_pixels,
        max_image_dimension=settings.max_image_dimension,
        max_video_duration_seconds=settings.max_video_duration_seconds,
        max_carousel_images=settings.max_carousel_images,
        max_analysis_payload_bytes=settings.max_analysis_payload_bytes,
    )


def probe_media(path: Path) -> MediaMetadata:
    """Return actual media metadata without trusting the filename extension."""

    source = Path(path)
    try:
        byte_size = source.stat().st_size
    except OSError as exc:
        raise MediaProbeError(f"Cannot read media file: {source.name} ({exc})") from exc
    if byte_size <= 0:
        raise MediaProbeError(f"Media file is empty: {source.name}")

    image = _probe_image_header(source, byte_size)
    if image is not None:
        return image
    return _probe_with_ffprobe(source, byte_size)


def validate_media(path: Path, limits: MediaLimits) -> MediaMetadata:
    metadata = probe_media(path)
    _validate_metadata(metadata, limits)
    return metadata


def preflight_media_files(paths: Iterable[Path], limits: MediaLimits) -> MediaPreflightReport:
    """Validate files independently, then apply carousel and payload limits as a group."""

    accepted: list[MediaMetadata] = []
    rejected: list[MediaPreflightIssue] = []
    seen: set[Path] = set()
    for raw_path in paths:
        path = Path(raw_path)
        key = path.resolve(strict=False)
        if key in seen:
            continue
        seen.add(key)
        try:
            accepted.append(validate_media(path, limits))
        except MediaProbeError as exc:
            rejected.append(MediaPreflightIssue(path, str(exc)))

    image_count = sum(1 for item in accepted if item.actual_type == "image")
    if image_count > limits.max_carousel_images:
        message = f"Carousel has {image_count} images; limit is {limits.max_carousel_images}"
        for item in tuple(accepted):
            if item.actual_type == "image":
                accepted.remove(item)
                rejected.append(MediaPreflightIssue(item.path, message))
    total_payload = sum(item.byte_size for item in accepted)
    if total_payload > limits.max_analysis_payload_bytes:
        message = f"Analysis payload is {total_payload} bytes; limit is {limits.max_analysis_payload_bytes}"
        for item in tuple(accepted):
            accepted.remove(item)
            rejected.append(MediaPreflightIssue(item.path, message))
    return MediaPreflightReport(tuple(accepted), tuple(rejected))


def verify_generated_media(path: Path, *, expected_type: str, width: int | None = None, height: int | None = None) -> MediaMetadata:
    """Probe an FFmpeg result before a transaction is allowed to commit it."""

    metadata = probe_media(path)
    if metadata.actual_type != expected_type:
        raise MediaValidationError(f"Generated {path.name} is {metadata.actual_type}, expected {expected_type}")
    if width is not None and metadata.width != width:
        raise MediaValidationError(f"Generated {path.name} width is {metadata.width}, expected {width}")
    if height is not None and metadata.height != height:
        raise MediaValidationError(f"Generated {path.name} height is {metadata.height}, expected {height}")
    return metadata


def _validate_metadata(metadata: MediaMetadata, limits: MediaLimits) -> None:
    if metadata.byte_size > limits.max_file_bytes:
        raise MediaValidationError(f"{metadata.path.name} is {metadata.byte_size} bytes; limit is {limits.max_file_bytes}")
    if metadata.actual_type == "image":
        if metadata.animated and not limits.allow_animated_images:
            raise MediaValidationError(f"Animated {metadata.format_name.upper()} files are not supported; export a still image first")
        if metadata.width is None or metadata.height is None:
            raise MediaValidationError(f"Image dimensions could not be read: {metadata.path.name}")
        if metadata.width > limits.max_image_dimension or metadata.height > limits.max_image_dimension:
            raise MediaValidationError(f"Image dimensions exceed {limits.max_image_dimension}px: {metadata.path.name}")
        if metadata.width * metadata.height > limits.max_image_pixels:
            raise MediaValidationError(f"Image pixel count exceeds {limits.max_image_pixels}: {metadata.path.name}")
    elif metadata.actual_type == "video":
        if metadata.width is None or metadata.height is None:
            raise MediaValidationError(f"Video dimensions could not be read: {metadata.path.name}")
        if metadata.duration_seconds is not None and metadata.duration_seconds > limits.max_video_duration_seconds:
            raise MediaValidationError(
                f"Video duration is {metadata.duration_seconds:.1f}s; limit is {limits.max_video_duration_seconds}s"
            )
    else:
        raise MediaValidationError(f"Unsupported actual media type: {metadata.actual_type}")


def _probe_image_header(path: Path, byte_size: int) -> MediaMetadata | None:
    try:
        with path.open("rb") as handle:
            payload = handle.read(1024 * 1024)
    except OSError as exc:
        raise MediaProbeError(f"Cannot read media file: {path.name} ({exc})") from exc
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(payload) < 33 or payload[8:16] != b"\x00\x00\x00\rIHDR":
            raise MediaProbeError(f"Malformed PNG image: {path.name}")
        if byte_size <= len(payload) and b"IEND\xaeB`\x82" not in payload:
            raise MediaProbeError(f"Malformed PNG image: {path.name}")
        width, height = struct.unpack(">II", payload[16:24])
        return _image_metadata(path, "png", "png", width, height, byte_size, b"acTL" in payload)
    if payload.startswith((b"GIF87a", b"GIF89a")):
        if len(payload) < 10:
            raise MediaProbeError(f"Malformed GIF image: {path.name}")
        if byte_size <= len(payload) and not payload.endswith(b";"):
            raise MediaProbeError(f"Malformed GIF image: {path.name}")
        width, height = struct.unpack("<HH", payload[6:10])
        animated = b"NETSCAPE2.0" in payload or payload.count(b"\x2c") > 1
        return _image_metadata(path, "gif", "gif", width, height, byte_size, animated)
    if payload.startswith(b"\xff\xd8"):
        dimensions = _jpeg_dimensions(payload)
        if dimensions is None:
            raise MediaProbeError(f"Malformed JPEG image: {path.name}")
        if byte_size <= len(payload) and not payload.endswith(b"\xff\xd9"):
            raise MediaProbeError(f"Malformed JPEG image: {path.name}")
        return _image_metadata(path, "jpeg", "mjpeg", dimensions[0], dimensions[1], byte_size, False)
    if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        dimensions, animated = _webp_dimensions(payload)
        if dimensions is None:
            raise MediaProbeError(f"Malformed WEBP image: {path.name}")
        return _image_metadata(path, "webp", "webp", dimensions[0], dimensions[1], byte_size, animated)
    return None


def _image_metadata(path: Path, format_name: str, codec: str, width: int, height: int, byte_size: int, animated: bool) -> MediaMetadata:
    if width <= 0 or height <= 0:
        raise MediaProbeError(f"Malformed {format_name.upper()} image: {path.name}")
    return MediaMetadata(
        path=path,
        actual_type="image",
        format_name=format_name,
        width=width,
        height=height,
        duration_seconds=None,
        codec=codec,
        stream_count=1,
        has_audio=False,
        audio_codec=None,
        byte_size=byte_size,
        animated=animated,
        extension_matches=path.suffix.lower() in _IMAGE_SUFFIXES,
    )


def _probe_with_ffprobe(path: Path, byte_size: int) -> MediaMetadata:
    command = ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    except FileNotFoundError as exc:
        raise MediaProbeError("ffprobe is unavailable; install FFmpeg and add it to PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaProbeError(f"ffprobe timed out while reading {path.name}") from exc
    if result.returncode != 0:
        detail = (result.stderr or "unrecognized or malformed media")[:240].strip()
        raise MediaProbeError(f"Media probe failed for {path.name}: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProbeError(f"ffprobe returned invalid metadata for {path.name}") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise MediaProbeError(f"ffprobe returned no streams for {path.name}")
    video_streams = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"]
    if not video_streams:
        raise MediaProbeError(f"Media has no video or image stream: {path.name}")
    video = video_streams[0]
    actual_type = "video"
    format_info = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    duration = _float_or_none(video.get("duration")) or _float_or_none(format_info.get("duration"))
    return MediaMetadata(
        path=path,
        actual_type=actual_type,
        format_name=str(format_info.get("format_name") or "unknown"),
        width=_positive_int_or_none(video.get("width")),
        height=_positive_int_or_none(video.get("height")),
        duration_seconds=duration,
        codec=str(video.get("codec_name")) if video.get("codec_name") else None,
        stream_count=len(streams),
        has_audio=bool(audio_streams),
        audio_codec=str(audio_streams[0].get("codec_name")) if audio_streams and audio_streams[0].get("codec_name") else None,
        byte_size=byte_size,
        animated=False,
        extension_matches=path.suffix.lower() in _VIDEO_SUFFIXES,
    )


def _signature_kind(path: Path) -> str | None:
    try:
        with Path(path).open("rb") as handle:
            payload = handle.read(32)
    except OSError:
        return None
    if payload.startswith((b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"\xff\xd8")):
        return "image"
    if payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return "image"
    if len(payload) >= 12 and payload[4:8] == b"ftyp":
        return "video"
    if payload.startswith(b"\x1aE\xdf\xa3"):
        return "video"
    return None


def _jpeg_dimensions(payload: bytes) -> tuple[int, int] | None:
    index = 2
    while index + 9 < len(payload):
        if payload[index] != 0xFF:
            index += 1
            continue
        while index < len(payload) and payload[index] == 0xFF:
            index += 1
        marker = payload[index]
        index += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(payload):
            return None
        length = struct.unpack(">H", payload[index:index + 2])[0]
        if length < 2 or index + length > len(payload):
            return None
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if length < 7:
                return None
            height, width = struct.unpack(">HH", payload[index + 3:index + 7])
            return width, height
        index += length
    return None


def _webp_dimensions(payload: bytes) -> tuple[tuple[int, int] | None, bool]:
    if len(payload) < 30:
        return None, False
    chunk = payload[12:16]
    if chunk == b"VP8X" and len(payload) >= 30:
        flags = payload[20]
        width = int.from_bytes(payload[24:27], "little") + 1
        height = int.from_bytes(payload[27:30], "little") + 1
        return (width, height), bool(flags & 0x02)
    if chunk == b"VP8 " and len(payload) >= 30 and payload[23:26] == b"\x9d\x01\x2a":
        width = struct.unpack("<H", payload[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", payload[28:30])[0] & 0x3FFF
        return (width, height), False
    if chunk == b"VP8L" and len(payload) >= 25 and payload[20] == 0x2F:
        bits = int.from_bytes(payload[21:25], "little")
        return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1), False
    return None, False


def _positive_int_or_none(value: object) -> int | None:
    return int(value) if isinstance(value, int) and value > 0 else None


def _float_or_none(value: object) -> float | None:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
