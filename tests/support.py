"""Reusable isolated workspace fixtures for unit tests."""
from __future__ import annotations

import base64
import json
import tempfile
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path


_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL9"
    "HgAAAABJRU5ErkJggg=="
)


@dataclass
class WorkspaceFixture(AbstractContextManager["WorkspaceFixture"]):
    """A disposable layout matching the application's managed directories."""

    temporary_directory: tempfile.TemporaryDirectory[str]
    root: Path
    inbox: Path
    processed: Path
    captions: Path
    outputs: Path
    posting_packs: Path
    logs: Path

    @classmethod
    def create(cls) -> "WorkspaceFixture":
        temporary_directory = tempfile.TemporaryDirectory()
        root = Path(temporary_directory.name)
        inbox = root / "inbox"
        processed = root / "!processed"
        captions = root / "captions"
        outputs = root / "outputs"
        posting_packs = root / "exports" / "posting-packs"
        logs = root / "logs"
        for directory in (inbox, processed, captions, outputs, posting_packs, logs):
            directory.mkdir(parents=True)
        return cls(temporary_directory, root, inbox, processed, captions, outputs, posting_packs, logs)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.temporary_directory.cleanup()

    def write_media(self, directory: Path, name: str, content: bytes = b"test-media") -> Path:
        path = directory / name
        path.write_bytes(content)
        return path

    def write_png(self, directory: Path, name: str = "image.png") -> Path:
        return self.write_media(directory, name, _ONE_PIXEL_PNG)

    def write_ledger(self, name: str, payload: object) -> Path:
        path = self.logs / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path
