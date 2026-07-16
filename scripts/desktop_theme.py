from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

try:
    from desktop_status import StatusSnapshot
except ImportError:
    from scripts.desktop_status import StatusSnapshot


APP_BACKGROUND = "#F6F7F9"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#EEF2F6"
BORDER = "#D0D5DD"
TEXT = "#101828"
MUTED_TEXT = "#475467"
PRIMARY = "#175CD3"
SUCCESS = "#067647"
DANGER = "#B42318"
WARNING = "#B54708"


@dataclass(frozen=True)
class StatusCardSpec:
    key: str
    title: str
    value: str
    caption: str
    accent: str


def build_status_card_specs(snapshot: StatusSnapshot) -> list[StatusCardSpec]:
    return [
        StatusCardSpec("inbox", "Inbox", str(snapshot.inbox_count), "Ready to process", PRIMARY),
        StatusCardSpec("captions", "Captions", str(snapshot.caption_count), "Copy exports", "#6941C6"),
        StatusCardSpec("processed", "Processed", str(snapshot.processed_count), "Primary finished media", SUCCESS),
        StatusCardSpec("outputs", "Outputs", str(snapshot.output_count), "Review workspaces", "#0E7090"),
    ]


def semantic_status_color(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in {"failed", "error"}:
        return DANGER
    if normalized in {"ready", "processed", "success"}:
        return SUCCESS
    if normalized in {"stale", "stale_drafts", "warning"}:
        return WARNING
    if normalized in {"draft", "running", "in_progress"}:
        return PRIMARY
    return MUTED_TEXT


def apply_theme(root) -> None:
    root.configure(bg=APP_BACKGROUND)
    try:
        from tkinter import ttk
    except Exception:
        return
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TNotebook", background=APP_BACKGROUND, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 10, "bold"))
    style.configure("TFrame", background=APP_BACKGROUND)
    style.configure("TLabelframe", background=APP_BACKGROUND)
    style.configure("TLabelframe.Label", font=("Segoe UI", 11, "bold"), foreground=TEXT)


def configure_widget_tree_background(widgets: Iterable, background: str = APP_BACKGROUND) -> None:
    for widget in widgets:
        try:
            widget.configure(bg=background)
        except Exception:
            pass
