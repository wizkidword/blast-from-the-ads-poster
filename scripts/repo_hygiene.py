#!/usr/bin/env python3
"""Fail CI when tracked runtime data, likely secrets, or huge files appear."""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path, PurePosixPath


DEFAULT_MAX_FILE_BYTES = 25 * 1024 * 1024
_RUNTIME_ROOTS = frozenset({"inbox", "captions", "!processed", "outputs", "exports", "logs", "temp", "cache", "archive", "media"})
_SECRET_ASSIGNMENT = re.compile(
    r"(?m)(?:\b[A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD)\b|[\"'](?:api_key|apiKey|openai_api_key|token|secret|password)[\"'])\s*[:=]\s*[\"']?([^\s\"',}]+)"
)
_TOKEN_PREFIX = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,})\b")


def tracked_paths(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-z"],
        capture_output=True,
        check=True,
    )
    return [Path(item) for item in result.stdout.decode("utf-8").split("\0") if item]


def is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return not normalized or any(marker in normalized for marker in ("your_", "example", "placeholder", "changeme", "<"))


def inspect_tracked_file(repo_root: Path, relative_path: Path, *, max_file_bytes: int) -> list[str]:
    """Return safe diagnostic messages without echoing secret values."""

    path = repo_root / relative_path
    portable = PurePosixPath(relative_path.as_posix())
    parts = portable.parts
    errors: list[str] = []
    if portable.as_posix() in {".env", "settings.json"}:
        errors.append(f"Tracked local configuration is not allowed: {portable}")
    if parts and parts[0] in _RUNTIME_ROOTS and portable.name != ".gitkeep":
        errors.append(f"Tracked runtime data is not allowed: {portable}")
    if path.stat().st_size > max_file_bytes:
        errors.append(f"Tracked file exceeds {max_file_bytes} bytes: {portable}")
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".mp4", ".mov", ".webm", ".zip", ".exe", ".pdf"}:
        return errors
    text = path.read_text(encoding="utf-8", errors="replace")
    if any(not is_placeholder(value) for value in _SECRET_ASSIGNMENT.findall(text)) or _TOKEN_PREFIX.search(text):
        errors.append(f"Possible secret detected in tracked file: {portable}")
    return errors


def check_repository(repo_root: Path, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> list[str]:
    errors: list[str] = []
    for relative_path in tracked_paths(repo_root):
        errors.extend(inspect_tracked_file(repo_root, relative_path, max_file_bytes=max_file_bytes))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the tracked repository for unsafe release inputs")
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    errors = check_repository(root, max_file_bytes=args.max_file_bytes)
    if errors:
        print("Repository hygiene failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Repository hygiene passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
