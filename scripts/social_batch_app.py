#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import os
import shutil
import threading
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from queue import Empty, Queue
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    W,
    X,
    Y,
    BooleanVar,
    Button,
    Checkbutton,
    Entry,
    Frame,
    Label,
    Listbox,
    OptionMenu,
    PanedWindow,
    Scrollbar,
    StringVar,
    Text,
    Tk,
    filedialog,
    messagebox,
    ttk,
)
from tkinter.scrolledtext import ScrolledText

try:
    from app_paths import get_project_root
except ImportError:
    from scripts.app_paths import get_project_root

try:
    from app_context import AppContext, build_app_context, prepare_app_context
except ImportError:
    from scripts.app_context import AppContext, build_app_context, prepare_app_context

try:
    from app_metadata import PACKAGE_HIDDEN_IMPORTS, build_version_label
except ImportError:
    from scripts.app_metadata import PACKAGE_HIDDEN_IMPORTS, build_version_label

try:
    from process_inbox_social import get_openai_api_key, has_failed_results, load_env
except ImportError:
    from scripts.process_inbox_social import get_openai_api_key, has_failed_results, load_env

try:
    from blast_workflow import setup_check
except ImportError:
    from scripts.blast_workflow import setup_check

try:
    from process_inbox_social import run_inbox_processing
except ImportError:
    from scripts.process_inbox_social import run_inbox_processing

try:
    from workspace_lock import CancellationToken, WorkspaceBusyError
except ImportError:
    from scripts.workspace_lock import CancellationToken, WorkspaceBusyError

try:
    from media_rules import is_supported_media_file, unique_destination
except ImportError:
    from scripts.media_rules import is_supported_media_file, unique_destination

try:
    from safe_paths import require_plain_filename, resolve_output_under
except ImportError:
    from scripts.safe_paths import require_plain_filename, resolve_output_under

try:
    from cleanup import CleanupSettings, execute_cleanup, format_cleanup_plan, plan_cleanup
except ImportError:
    from scripts.cleanup import CleanupSettings, execute_cleanup, format_cleanup_plan, plan_cleanup

try:
    from export_packs import create_posting_pack
except ImportError:
    from scripts.export_packs import create_posting_pack

try:
    from run_history import format_run_details, format_run_history, list_recent_inbox_runs, load_inbox_run_details
except ImportError:
    from scripts.run_history import format_run_details, format_run_history, list_recent_inbox_runs, load_inbox_run_details

try:
    from recovery_queue import build_recovery_queue, format_recovery_queue, plan_retry_targets
except ImportError:
    from scripts.recovery_queue import build_recovery_queue, format_recovery_queue, plan_retry_targets

try:
    from recovery_service import build_retry_plan, execute_retry_plan, filter_retry_plan
except ImportError:
    from scripts.recovery_service import build_retry_plan, execute_retry_plan, filter_retry_plan

try:
    from review_queue import bulk_update_status, format_review_preview, query_review_items, readiness_reports_for_review
except ImportError:
    from scripts.review_queue import bulk_update_status, format_review_preview, query_review_items, readiness_reports_for_review

try:
    from readiness import format_readiness_reports
except ImportError:
    from scripts.readiness import format_readiness_reports

try:
    from settings_store import save_settings
except ImportError:
    from scripts.settings_store import save_settings

try:
    from publishing import PublishStatus, list_provider_names, load_manifest, normalize_hashtag_list, save_manifest, update_manifest_review
except ImportError:
    from scripts.publishing import PublishStatus, list_provider_names, load_manifest, normalize_hashtag_list, save_manifest, update_manifest_review

try:
    from requeue import collect_requeue_plan, requeue_output_workspace
except ImportError:
    from scripts.requeue import collect_requeue_plan, requeue_output_workspace

try:
    from desktop_status import build_status_snapshot, format_status_line
except ImportError:
    from scripts.desktop_status import build_status_snapshot, format_status_line

try:
    from desktop_review import build_review_editor_state
except ImportError:
    from scripts.desktop_review import build_review_editor_state

try:
    from desktop_requeue import build_requeue_confirmation, execute_requeue_plan
except ImportError:
    from scripts.desktop_requeue import build_requeue_confirmation, execute_requeue_plan

try:
    from desktop_workflow import format_workflow_label, parse_limit_value, run_workflow_action
except ImportError:
    from scripts.desktop_workflow import format_workflow_label, parse_limit_value, run_workflow_action

try:
    from desktop_theme import APP_BACKGROUND, BORDER, MUTED_TEXT, PRIMARY, SURFACE, TEXT, apply_theme, build_status_card_specs
except ImportError:
    from scripts.desktop_theme import APP_BACKGROUND, BORDER, MUTED_TEXT, PRIMARY, SURFACE, TEXT, apply_theme, build_status_card_specs

try:
    from desktop_settings import SettingsFormState, build_settings_form_state, parse_settings_form_state
except ImportError:
    from scripts.desktop_settings import SettingsFormState, build_settings_form_state, parse_settings_form_state


BASE_DIR = get_project_root()
INBOX_DIR = BASE_DIR / "inbox"
SETTINGS_PATH = BASE_DIR / "settings.json"
CAPTIONS_DIR = BASE_DIR / "captions"
PROCESSED_DIR = BASE_DIR / "!processed"
OUTPUTS_DIR = BASE_DIR / "outputs"
LOGS_DIR = BASE_DIR / "logs"
EXPORTS_DIR = BASE_DIR / "exports"


def get_runtime_context() -> AppContext:
    return build_app_context(BASE_DIR, settings_path=SETTINGS_PATH)


def configure_output_dirs_from_settings() -> AppContext:
    """Deprecated compatibility helper; operations use SocialBatchApp.context."""

    return get_runtime_context()


def ensure_project_dirs(context: AppContext | None = None) -> AppContext:
    return prepare_app_context(context or get_runtime_context())


class QueueWriter:
    def __init__(self, log_queue: Queue[tuple[str, str]]) -> None:
        self.log_queue = log_queue
        self.buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self.log_queue.put(("line", line))
        return len(text)

    def flush(self) -> None:
        if self.buffer:
            self.log_queue.put(("line", self.buffer))
            self.buffer = ""


class SocialBatchApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.context = get_runtime_context()
        self.root.title("Blast From the Ads")
        self.root.geometry("1320x900")
        self.root.minsize(1120, 760)

        self.status_var = StringVar()
        self.run_history_var = StringVar(value="Latest Run: none yet")
        self.limit_var = StringVar()
        self.run_detail_var = StringVar(value="Select a run to inspect details.")
        self.recovery_status_var = StringVar(value="Recovery Queue: no failed files found.")
        self.review_filter_var = StringVar(value="all")
        self.review_search_var = StringVar()
        self.review_status_var = StringVar(value="Review Queue: 0 post(s)")
        self.review_meta_var = StringVar(value="Select a post to review.")
        self.review_selection_var = StringVar(value="No post selected.")
        self.settings_status_var = StringVar(value="Settings are loaded from settings.json; secrets stay in .env.")
        self.settings_env_status_var = StringVar(value="OpenAI API key: not checked yet")
        self.settings_openai_model_var = StringVar()
        self.settings_default_providers_var = StringVar()
        self.settings_logs_retention_var = StringVar()
        self.settings_pack_retention_var = StringVar()
        self.settings_orphan_retention_var = StringVar()
        self.settings_stale_draft_var = StringVar()
        self.settings_preferred_platforms_var = StringVar()
        self.settings_captions_dir_var = StringVar()
        self.settings_processed_dir_var = StringVar()
        self.settings_max_media_file_bytes_var = StringVar()
        self.settings_max_image_pixels_var = StringVar()
        self.settings_max_image_dimension_var = StringVar()
        self.settings_max_video_duration_var = StringVar()
        self.settings_max_carousel_images_var = StringVar()
        self.settings_max_analysis_payload_var = StringVar()
        self.settings_max_analysis_images_var = StringVar()
        self.settings_max_analysis_dimension_var = StringVar()
        self.settings_max_analysis_request_bytes_var = StringVar()
        self.settings_max_analysis_video_frames_var = StringVar()
        self.settings_ai_enabled_var = BooleanVar(value=True)
        self.settings_allow_fallback_var = BooleanVar(value=False)
        self.status_card_vars: dict[str, StringVar] = {}
        self.running = False
        self.log_queue: Queue[tuple[str, str]] = Queue()
        self.run_summaries = []
        self.selected_run_log_path: Path | None = None
        self.recovery_queue = None
        self.review_items = []
        self.selected_manifest_path: Path | None = None
        self.provider_vars: dict[str, BooleanVar] = {}
        self.cancellation_token: CancellationToken | None = None
        self.accepting_work = True
        self.shutting_down = False
        self.root.protocol("WM_DELETE_WINDOW", self.request_shutdown)

        self._build_ui()
        self.refresh_status()
        self.refresh_run_history()
        self.refresh_recovery_queue()
        self.refresh_review_queue()
        self.root.after(150, self._drain_log_queue)

    def _build_ui(self) -> None:
        apply_theme(self.root)
        header = Frame(self.root, padx=16, pady=14, bg=APP_BACKGROUND)
        header.pack(fill="x")
        Label(header, text=build_version_label(), font=("Segoe UI", 19, "bold"), bg=APP_BACKGROUND, fg=TEXT).pack(anchor=W)
        Label(
            header,
            text="Process daily drops, review finished posts, recover failed runs, and tune local settings.",
            font=("Segoe UI", 10),
            bg=APP_BACKGROUND,
            fg=MUTED_TEXT,
        ).pack(anchor=W)

        self.main_notebook = ttk.Notebook(self.root)
        self.main_notebook.pack(fill=BOTH, expand=True, padx=12, pady=(0, 12))
        process_tab = Frame(self.main_notebook, bg=APP_BACKGROUND, padx=12, pady=12)
        review_tab = Frame(self.main_notebook, bg=APP_BACKGROUND, padx=12, pady=12)
        recovery_tab = Frame(self.main_notebook, bg=APP_BACKGROUND, padx=12, pady=12)
        settings_tab = Frame(self.main_notebook, bg=APP_BACKGROUND, padx=12, pady=12)
        self.main_notebook.add(process_tab, text="Process")
        self.main_notebook.add(review_tab, text="Review")
        self.main_notebook.add(recovery_tab, text="Recovery")
        self.main_notebook.add(settings_tab, text="Settings")

        status_frame = Frame(process_tab, padx=0, pady=4, bg=APP_BACKGROUND)
        status_frame.pack(fill="x")
        Label(status_frame, text="Daily Processing", font=("Segoe UI", 13, "bold"), bg=APP_BACKGROUND, fg=TEXT).pack(anchor=W)
        Label(status_frame, textvariable=self.status_var, font=("Consolas", 10), bg=APP_BACKGROUND, fg=MUTED_TEXT).pack(anchor=W, pady=(2, 0))
        Label(status_frame, textvariable=self.run_history_var, font=("Consolas", 10), justify=LEFT, bg=APP_BACKGROUND, fg=MUTED_TEXT).pack(anchor=W, pady=(3, 0))
        self.status_cards_frame = Frame(process_tab, bg=APP_BACKGROUND)
        self.status_cards_frame.pack(fill=X, pady=(8, 4))
        self._build_status_cards()

        controls = Frame(process_tab, padx=0, pady=10, bg=APP_BACKGROUND)
        controls.pack(fill="x")

        self.add_button = Button(controls, text="Add Files to Inbox", width=18, command=self.add_files_to_inbox)
        self.add_button.pack(side=LEFT, padx=(0, 8))
        self.process_button = Button(controls, text="Process Inbox", width=14, command=self.process_inbox)
        self.process_button.pack(side=LEFT, padx=(0, 8))
        self.dry_run_button = Button(controls, text="Dry Run", width=10, command=self.dry_run_inbox)
        self.dry_run_button.pack(side=LEFT, padx=(0, 8))
        self.requeue_button = Button(controls, text="Requeue Processed", width=16, command=self.requeue_processed_files)
        self.requeue_button.pack(side=LEFT, padx=(0, 8))
        self.setup_button = Button(controls, text="Check Setup", width=12, command=self.check_setup)
        self.setup_button.pack(side=LEFT, padx=(0, 8))
        self.cleanup_button = Button(controls, text="Safe Cleanup", width=12, command=self.cleanup_safe_artifacts)
        self.cleanup_button.pack(side=LEFT, padx=(0, 8))

        Label(controls, text="Limit:", font=("Segoe UI", 10), bg=APP_BACKGROUND, fg=TEXT).pack(side=LEFT, padx=(12, 6))
        Entry(controls, width=8, textvariable=self.limit_var).pack(side=LEFT)

        open_row = Frame(process_tab, padx=0, pady=4, bg=APP_BACKGROUND)
        open_row.pack(fill="x")
        self.open_inbox_button = Button(open_row, text="Open Inbox", width=12, command=lambda: self.open_folder(self.context.inbox_dir))
        self.open_inbox_button.pack(side=LEFT, padx=(0, 8))
        self.open_captions_button = Button(open_row, text="Open Captions", width=12, command=lambda: self.open_folder(self.context.captions_dir))
        self.open_captions_button.pack(side=LEFT, padx=(0, 8))
        self.open_processed_button = Button(open_row, text="Open Processed", width=14, command=lambda: self.open_folder(self.context.processed_dir))
        self.open_processed_button.pack(side=LEFT, padx=(0, 8))
        self.open_outputs_button = Button(open_row, text="Open Outputs", width=12, command=lambda: self.open_folder(self.context.outputs_dir))
        self.open_outputs_button.pack(side=LEFT, padx=(0, 8))
        self.open_logs_button = Button(open_row, text="Open Logs", width=10, command=lambda: self.open_folder(self.context.logs_dir))
        self.open_logs_button.pack(side=LEFT, padx=(0, 8))
        self.open_exports_button = Button(open_row, text="Open Exports", width=12, command=lambda: self.open_folder(self.context.exports_dir))
        self.open_exports_button.pack(side=LEFT, padx=(0, 8))

        run_frame = Frame(recovery_tab, padx=0, pady=0, bg=APP_BACKGROUND)
        run_frame.pack(fill=X)
        Label(run_frame, text="Run Details / Recovery", font=("Segoe UI", 13, "bold"), bg=APP_BACKGROUND, fg=TEXT).pack(anchor=W)
        run_toolbar = Frame(run_frame, bg=APP_BACKGROUND)
        run_toolbar.pack(fill=X, pady=(0, 6))
        self.refresh_runs_button = Button(run_toolbar, text="Refresh Runs", width=12, command=self.refresh_run_history)
        self.refresh_runs_button.pack(side=LEFT, padx=(0, 8))
        self.open_run_log_button = Button(run_toolbar, text="Open Run Log", width=12, command=self.open_selected_run_log)
        self.open_run_log_button.pack(side=LEFT, padx=(0, 8))
        self.retry_failed_button = Button(run_toolbar, text="Retry Failed", width=12, command=self.retry_failed_from_selected_run)
        self.retry_failed_button.pack(side=LEFT, padx=(0, 8))
        self.retry_all_failed_button = Button(run_toolbar, text="Retry All", width=10, command=lambda: self.retry_recovery_queue("all"))
        self.retry_all_failed_button.pack(side=LEFT, padx=(0, 8))
        self.retry_failed_videos_button = Button(run_toolbar, text="Retry Videos", width=12, command=lambda: self.retry_recovery_queue("videos"))
        self.retry_failed_videos_button.pack(side=LEFT, padx=(0, 8))
        self.retry_failed_images_button = Button(run_toolbar, text="Retry Images", width=12, command=lambda: self.retry_recovery_queue("images"))
        self.retry_failed_images_button.pack(side=LEFT, padx=(0, 8))
        Label(run_toolbar, textvariable=self.recovery_status_var, font=("Consolas", 9), bg=APP_BACKGROUND, fg=MUTED_TEXT).pack(side=LEFT, padx=(8, 0))
        run_body = Frame(run_frame, bg=APP_BACKGROUND)
        run_body.pack(fill=X)
        run_scrollbar = Scrollbar(run_body)
        run_scrollbar.pack(side=RIGHT, fill=Y)
        self.run_listbox = Listbox(run_body, height=4, font=("Consolas", 10), exportselection=False)
        self.run_listbox.pack(side=LEFT, fill=X, expand=True)
        self.run_listbox.configure(yscrollcommand=run_scrollbar.set)
        run_scrollbar.configure(command=self.run_listbox.yview)
        self.run_listbox.bind("<<ListboxSelect>>", self._on_run_select)
        self.run_details_text = ScrolledText(run_frame, height=5, wrap="word", font=("Consolas", 9))
        self.run_details_text.pack(fill=X, pady=(6, 0))
        self.run_details_text.configure(state="disabled")

        review_frame = Frame(review_tab, padx=0, pady=0, bg=APP_BACKGROUND)
        review_frame.pack(fill=BOTH, expand=True)
        Label(review_frame, text="Review Queue", font=("Segoe UI", 13, "bold"), bg=APP_BACKGROUND, fg=TEXT).pack(anchor=W)
        Label(review_frame, textvariable=self.review_status_var, font=("Consolas", 10), bg=APP_BACKGROUND, fg=MUTED_TEXT).pack(anchor=W, pady=(0, 6))

        review_pane = PanedWindow(review_frame, orient="horizontal", sashrelief="raised")
        review_pane.pack(fill=BOTH, expand=True)

        queue_frame = Frame(review_pane, padx=4, pady=4, bg=APP_BACKGROUND)
        review_pane.add(queue_frame, minsize=280)
        queue_toolbar = Frame(queue_frame, bg=APP_BACKGROUND)
        queue_toolbar.pack(fill=X, pady=(0, 6))
        self.refresh_queue_button = Button(queue_toolbar, text="Refresh Queue", width=12, command=self.refresh_review_queue)
        self.refresh_queue_button.pack(side=LEFT, padx=(0, 8))
        self.open_selected_button = Button(queue_toolbar, text="Open Workspace", width=14, command=self.open_selected_workspace)
        self.open_selected_button.pack(side=LEFT, padx=(0, 8))
        self.requeue_selected_button = Button(queue_toolbar, text="Requeue Post", width=12, command=self.requeue_selected_post)
        self.requeue_selected_button.pack(side=LEFT)

        filter_row = Frame(queue_frame, bg=APP_BACKGROUND)
        filter_row.pack(fill=X, pady=(0, 6))
        Label(filter_row, text="Status:", font=("Segoe UI", 9), bg=APP_BACKGROUND, fg=TEXT).pack(side=LEFT, padx=(0, 4))
        OptionMenu(filter_row, self.review_filter_var, "all", "ready", "draft", "failed", "stale_drafts", command=lambda _value: self.refresh_review_queue()).pack(side=LEFT, padx=(0, 8))
        Label(filter_row, text="Search:", font=("Segoe UI", 9), bg=APP_BACKGROUND, fg=TEXT).pack(side=LEFT, padx=(0, 4))
        self.review_search_entry = Entry(filter_row, textvariable=self.review_search_var, font=("Segoe UI", 9))
        self.review_search_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        self.review_search_button = Button(filter_row, text="Apply", width=7, command=self.refresh_review_queue)
        self.review_search_button.pack(side=LEFT)

        queue_list_frame = Frame(queue_frame, bg=APP_BACKGROUND)
        queue_list_frame.pack(fill=BOTH, expand=True)
        queue_scrollbar = Scrollbar(queue_list_frame)
        queue_scrollbar.pack(side=RIGHT, fill=Y)
        self.review_listbox = Listbox(queue_list_frame, font=("Consolas", 10), exportselection=False)
        self.review_listbox.pack(side=LEFT, fill=BOTH, expand=True)
        self.review_listbox.configure(yscrollcommand=queue_scrollbar.set)
        queue_scrollbar.configure(command=self.review_listbox.yview)
        self.review_listbox.bind("<<ListboxSelect>>", self._on_review_select)

        editor_frame = Frame(review_pane, padx=8, pady=4, bg=APP_BACKGROUND)
        review_pane.add(editor_frame, minsize=620)
        Label(editor_frame, textvariable=self.review_selection_var, font=("Segoe UI", 11, "bold"), bg=APP_BACKGROUND, fg=TEXT).pack(anchor=W)
        Label(editor_frame, textvariable=self.review_meta_var, font=("Consolas", 10), justify=LEFT, wraplength=780, bg=APP_BACKGROUND, fg=MUTED_TEXT).pack(anchor=W, pady=(2, 8))

        title_row = Frame(editor_frame, bg=APP_BACKGROUND)
        title_row.pack(fill=X, pady=(0, 8))
        Label(title_row, text="Title", width=10, anchor=W, bg=APP_BACKGROUND, fg=TEXT).pack(side=LEFT)
        self.title_entry = Entry(title_row, font=("Segoe UI", 10))
        self.title_entry.pack(side=LEFT, fill=X, expand=True)

        desc_label = Label(editor_frame, text="Description", anchor=W, bg=APP_BACKGROUND, fg=TEXT)
        desc_label.pack(anchor=W)
        self.description_text = ScrolledText(editor_frame, height=8, wrap="word", font=("Segoe UI", 10))
        self.description_text.pack(fill=X, pady=(0, 8))

        hashtags_row = Frame(editor_frame, bg=APP_BACKGROUND)
        hashtags_row.pack(fill=X, pady=(0, 8))
        Label(hashtags_row, text="Hashtags", width=10, anchor=W, bg=APP_BACKGROUND, fg=TEXT).pack(side=LEFT)
        self.hashtags_entry = Entry(hashtags_row, font=("Segoe UI", 10))
        self.hashtags_entry.pack(side=LEFT, fill=X, expand=True)

        providers_frame = Frame(editor_frame, bg=APP_BACKGROUND)
        providers_frame.pack(fill=X, pady=(0, 8))
        Label(providers_frame, text="Destinations", width=10, anchor=W, bg=APP_BACKGROUND, fg=TEXT).pack(side=LEFT)
        providers_checks_frame = Frame(providers_frame, bg=APP_BACKGROUND)
        providers_checks_frame.pack(side=LEFT, fill=X, expand=True)
        for provider_name in list_provider_names():
            var = BooleanVar(value=False)
            self.provider_vars[provider_name] = var
            Checkbutton(providers_checks_frame, text=provider_name, variable=var, bg=APP_BACKGROUND, fg=TEXT, activebackground=APP_BACKGROUND).pack(side=LEFT, padx=(0, 10))

        actions_row = Frame(editor_frame, bg=APP_BACKGROUND)
        actions_row.pack(fill=X, pady=(0, 8))
        self.save_review_button = Button(actions_row, text="Save Review", width=12, command=self.save_review)
        self.save_review_button.pack(side=LEFT, padx=(0, 8))
        self.mark_draft_button = Button(actions_row, text="Mark Draft", width=12, command=lambda: self.save_review(PublishStatus.DRAFT.value))
        self.mark_draft_button.pack(side=LEFT, padx=(0, 8))
        self.mark_ready_button = Button(actions_row, text="Mark Ready", width=12, command=lambda: self.save_review(PublishStatus.READY.value))
        self.mark_ready_button.pack(side=LEFT, padx=(0, 8))
        self.create_pack_button = Button(actions_row, text="Create Pack", width=12, command=self.create_posting_pack_for_selected)
        self.create_pack_button.pack(side=LEFT, padx=(0, 8))
        self.bulk_ready_button = Button(actions_row, text="Bulk Ready", width=12, command=self.bulk_mark_filtered_ready)
        self.bulk_ready_button.pack(side=LEFT, padx=(0, 8))

        context_label = Label(editor_frame, text="Context", anchor=W, bg=APP_BACKGROUND, fg=TEXT)
        context_label.pack(anchor=W)
        self.context_text = ScrolledText(editor_frame, height=12, wrap="word", font=("Consolas", 10))
        self.context_text.pack(fill=BOTH, expand=True)
        self.context_text.configure(state="disabled")

        self._build_settings_tab(settings_tab)

        log_frame = Frame(process_tab, padx=0, pady=12, bg=APP_BACKGROUND)
        log_frame.pack(fill=BOTH, expand=True)
        self.log_text = ScrolledText(log_frame, wrap="word", font=("Consolas", 10))
        self.log_text.pack(fill=BOTH, expand=True)
        self.log("Ready. Add files or run a setup check.")
        load_env()
        if not get_openai_api_key():
            self.log("WARNING: OPENAI_API_KEY is not configured yet. Add it to .env before processing.")

    def _build_status_cards(self) -> None:
        context = self.context
        snapshot = build_status_snapshot(context.inbox_dir, context.captions_dir, context.processed_dir, context.outputs_dir)
        for card in build_status_card_specs(snapshot):
            value_var = StringVar(value=card.value)
            self.status_card_vars[card.key] = value_var
            card_frame = Frame(
                self.status_cards_frame,
                bg=SURFACE,
                padx=12,
                pady=10,
                highlightbackground=BORDER,
                highlightthickness=1,
            )
            card_frame.pack(side=LEFT, fill=X, expand=True, padx=(0, 10))
            Frame(card_frame, bg=card.accent, height=3).pack(fill=X, pady=(0, 8))
            Label(card_frame, text=card.title, font=("Segoe UI", 9, "bold"), bg=SURFACE, fg=MUTED_TEXT).pack(anchor=W)
            Label(card_frame, textvariable=value_var, font=("Segoe UI", 20, "bold"), bg=SURFACE, fg=TEXT).pack(anchor=W)
            Label(card_frame, text=card.caption, font=("Segoe UI", 8), bg=SURFACE, fg=MUTED_TEXT).pack(anchor=W)

    def _build_settings_tab(self, parent: Frame) -> None:
        Label(parent, text="Settings", font=("Segoe UI", 13, "bold"), bg=APP_BACKGROUND, fg=TEXT).pack(anchor=W)
        Label(
            parent,
            text="Non-secret preferences for the local workstation. API keys remain in .env and are never displayed here.",
            font=("Segoe UI", 10),
            bg=APP_BACKGROUND,
            fg=MUTED_TEXT,
        ).pack(anchor=W, pady=(2, 12))

        settings_body = Frame(parent, bg=SURFACE, padx=14, pady=14, highlightbackground=BORDER, highlightthickness=1)
        settings_body.pack(fill=X)

        def add_entry(label_text: str, variable: StringVar, width: int = 46) -> None:
            row = Frame(settings_body, bg=SURFACE)
            row.pack(fill=X, pady=(0, 8))
            Label(row, text=label_text, width=28, anchor=W, bg=SURFACE, fg=TEXT, font=("Segoe UI", 9, "bold")).pack(side=LEFT)
            Entry(row, textvariable=variable, width=width, font=("Segoe UI", 10)).pack(side=LEFT, fill=X, expand=True)

        add_entry("OpenAI model", self.settings_openai_model_var)
        Checkbutton(
            settings_body,
            text="Use OpenAI analysis (disable to create editable local drafts)",
            variable=self.settings_ai_enabled_var,
            bg=SURFACE,
            fg=TEXT,
            activebackground=SURFACE,
        ).pack(anchor=W, pady=(0, 8))
        Checkbutton(
            settings_body,
            text="Allow generic emergency fallback captions",
            variable=self.settings_allow_fallback_var,
            bg=SURFACE,
            fg=TEXT,
            activebackground=SURFACE,
        ).pack(anchor=W, pady=(0, 8))
        add_entry("Default providers", self.settings_default_providers_var)
        add_entry("Preferred platforms", self.settings_preferred_platforms_var)
        add_entry("Captions folder", self.settings_captions_dir_var)
        add_entry("Processed folder", self.settings_processed_dir_var)
        add_entry("Max media file bytes", self.settings_max_media_file_bytes_var, width=16)
        add_entry("Max image pixels", self.settings_max_image_pixels_var, width=16)
        add_entry("Max image dimension", self.settings_max_image_dimension_var, width=16)
        add_entry("Max video seconds", self.settings_max_video_duration_var, width=16)
        add_entry("Max carousel images", self.settings_max_carousel_images_var, width=16)
        add_entry("Max analysis bytes", self.settings_max_analysis_payload_var, width=16)
        add_entry("Max AI analysis images", self.settings_max_analysis_images_var, width=16)
        add_entry("Max AI analysis dimension", self.settings_max_analysis_dimension_var, width=16)
        add_entry("Max AI request bytes", self.settings_max_analysis_request_bytes_var, width=16)
        add_entry("Max AI video frames", self.settings_max_analysis_video_frames_var, width=16)
        add_entry("Log retention days", self.settings_logs_retention_var, width=16)
        add_entry("Posting pack retention days", self.settings_pack_retention_var, width=16)
        add_entry("Orphan output retention days", self.settings_orphan_retention_var, width=16)
        add_entry("Stale draft days", self.settings_stale_draft_var, width=16)

        Label(settings_body, textvariable=self.settings_env_status_var, bg=SURFACE, fg=MUTED_TEXT, font=("Consolas", 9)).pack(anchor=W, pady=(4, 8))
        settings_actions = Frame(settings_body, bg=SURFACE)
        settings_actions.pack(fill=X)
        self.reload_settings_button = Button(settings_actions, text="Reload Settings", width=14, command=self.load_settings_tab)
        self.reload_settings_button.pack(side=LEFT, padx=(0, 8))
        self.save_settings_button = Button(settings_actions, text="Save Settings", width=14, command=self.save_settings_tab)
        self.save_settings_button.pack(side=LEFT)
        Label(parent, textvariable=self.settings_status_var, bg=APP_BACKGROUND, fg=MUTED_TEXT, font=("Consolas", 9)).pack(anchor=W, pady=(10, 0))
        self.load_settings_tab()

    def log(self, message: str) -> None:
        self.log_text.insert(END, message.rstrip() + "\n")
        self.log_text.see(END)

    def refresh_status(self) -> None:
        context = self.context
        snapshot = build_status_snapshot(context.inbox_dir, context.captions_dir, context.processed_dir, context.outputs_dir)
        self.status_var.set(format_status_line(snapshot))
        for card in build_status_card_specs(snapshot):
            if card.key in self.status_card_vars:
                self.status_card_vars[card.key].set(card.value)
        self.run_history_var.set(format_run_history(list_recent_inbox_runs(context.logs_dir, limit=3)))

    def refresh_run_history(self) -> None:
        self.run_summaries = list_recent_inbox_runs(self.context.logs_dir, limit=8)
        self.run_listbox.delete(0, END)
        for index, summary in enumerate(self.run_summaries):
            self.run_listbox.insert(END, format_run_history([summary]).replace("Latest Run", f"Run {summary.run_id}") if index == 0 else f"Run {summary.run_id}: {summary.status.upper()} | {summary.processed_count} processed | {summary.failed_count} failed | {summary.media_count} media")

        if not self.run_summaries:
            self.selected_run_log_path = None
            self._set_run_details_text("No run logs yet.")
            return

        self.run_listbox.selection_clear(0, END)
        self.run_listbox.selection_set(0)
        self.run_listbox.activate(0)
        self._load_run_details(self.run_summaries[0].path)
        self.run_history_var.set(format_run_history(self.run_summaries[:3]))

    def refresh_recovery_queue(self) -> None:
        self.recovery_queue = build_recovery_queue(
            self.context.logs_dir,
            self.context.inbox_dir,
            self.context.outputs_dir,
        )
        self.recovery_status_var.set(
            f"Recovery Queue: {self.recovery_queue.available_count} available, {self.recovery_queue.stale_count} stale"
        )

    def _on_run_select(self, _event: object | None = None) -> None:
        selection = self.run_listbox.curselection()
        if not selection:
            return
        index = int(selection[0])
        if index < 0 or index >= len(self.run_summaries):
            return
        self._load_run_details(self.run_summaries[index].path)

    def _load_run_details(self, log_path: Path) -> None:
        self.selected_run_log_path = log_path
        self._set_run_details_text(format_run_details(load_inbox_run_details(log_path)))

    def _set_run_details_text(self, text: str) -> None:
        self.run_details_text.configure(state="normal")
        self.run_details_text.delete("1.0", END)
        self.run_details_text.insert("1.0", text)
        self.run_details_text.configure(state="disabled")

    def refresh_review_queue(self, select_path: Path | None = None) -> None:
        context = self.context
        self.review_items = query_review_items(
            context.outputs_dir,
            status_filter=self.review_filter_var.get(),
            search_text=self.review_search_var.get(),
            stale_days=context.settings.stale_draft_days,
        )
        self.review_listbox.delete(0, END)
        for item in self.review_items:
            self.review_listbox.insert(END, item.label)

        self.review_status_var.set(
            f"Review Queue: {len(self.review_items)} post(s)    Filter: {self.review_filter_var.get()}    Search: {self.review_search_var.get() or '-'}"
        )

        target_path = select_path or self.selected_manifest_path
        if not self.review_items:
            self.selected_manifest_path = None
            self._clear_review_form()
            return

        selected_index = 0
        if target_path:
            for index, item in enumerate(self.review_items):
                if item.manifest_path == target_path:
                    selected_index = index
                    break

        self.review_listbox.selection_clear(0, END)
        self.review_listbox.selection_set(selected_index)
        self.review_listbox.activate(selected_index)
        self._load_manifest_into_editor(self.review_items[selected_index].manifest_path)

    def _clear_review_form(self) -> None:
        self.review_selection_var.set("No post selected.")
        self.review_meta_var.set("Run a batch or refresh the queue to load manifests.")
        self.title_entry.delete(0, END)
        self.description_text.delete("1.0", END)
        self.hashtags_entry.delete(0, END)
        for var in self.provider_vars.values():
            var.set(False)
        self._set_context_text("No post selected.")

    def _set_context_text(self, text: str) -> None:
        self.context_text.configure(state="normal")
        self.context_text.delete("1.0", END)
        self.context_text.insert("1.0", text)
        self.context_text.configure(state="disabled")

    def _load_manifest_into_editor(self, manifest_path: Path) -> None:
        manifest = load_manifest(manifest_path)
        self.selected_manifest_path = manifest_path
        review_item = self._find_review_item(manifest_path)
        preview = format_review_preview(review_item) if review_item else ""
        readiness_text = format_readiness_reports(readiness_reports_for_review(manifest_path, manifest))
        state = build_review_editor_state(manifest, manifest_path, review_preview=preview, readiness_text=readiness_text)

        self.review_selection_var.set(state.selection_text)
        self.review_meta_var.set(state.meta_text)
        self.title_entry.delete(0, END)
        self.title_entry.insert(0, state.title)
        self.description_text.delete("1.0", END)
        self.description_text.insert("1.0", state.description)
        self.hashtags_entry.delete(0, END)
        self.hashtags_entry.insert(0, state.hashtags_text)
        for provider_name, var in self.provider_vars.items():
            var.set(provider_name in state.selected_providers)
        self._set_context_text(state.context_text)

    def _on_review_select(self, _event: object | None = None) -> None:
        selection = self.review_listbox.curselection()
        if not selection:
            return
        index = int(selection[0])
        if index < 0 or index >= len(self.review_items):
            return
        self._load_manifest_into_editor(self.review_items[index].manifest_path)

    def _find_review_item(self, manifest_path: Path):
        for item in self.review_items:
            if item.manifest_path == manifest_path:
                return item
        matches = query_review_items(manifest_path.parent.parent, status_filter="all", search_text="")
        for item in matches:
            if item.manifest_path == manifest_path:
                return item
        return None

    def open_selected_workspace(self) -> None:
        if not self.selected_manifest_path:
            messagebox.showinfo("No selection", "Choose a post from the review queue first.")
            return
        self.open_folder(self.selected_manifest_path.parent)

    def open_selected_run_log(self) -> None:
        if not self.selected_run_log_path:
            messagebox.showinfo("No run selected", "Choose a run from the recovery list first.")
            return
        self.open_path(self.selected_run_log_path)

    def retry_failed_from_selected_run(self) -> None:
        if not self.selected_run_log_path:
            messagebox.showinfo("No run selected", "Choose a run from the recovery list first.")
            return
        plan = build_retry_plan(
            [self.selected_run_log_path],
            self.context.inbox_dir,
            outputs_dir=self.context.outputs_dir,
        )
        if not plan.retry_files:
            unavailable = "\n".join([*plan.missing_files, *plan.skipped_files]) or "No failed files were listed."
            details = "\n".join(plan.errors)
            message = f"No failed files from this run are currently safe to retry.\n\nUnavailable:\n{unavailable}"
            if details:
                message += f"\n\nDetails:\n{details}"
            messagebox.showinfo("Nothing to retry", message)
            return
        confirmed = messagebox.askyesno(
            "Retry failed files",
            f"Retry {len(plan.retry_files)} failed file(s) from this run?\n\nOnly these inbox files will be processed.",
        )
        if not confirmed:
            return
        execute_retry_plan(plan, lambda targets: self._run_workflow("inbox", target_files=targets))

    def retry_recovery_queue(self, mode: str) -> None:
        self.refresh_recovery_queue()
        if not self.recovery_queue:
            return
        plan = filter_retry_plan(self.recovery_queue.plan, mode=mode) if self.recovery_queue.plan else None
        targets = list(plan.retry_files) if plan else plan_retry_targets(self.recovery_queue, mode=mode)
        if not targets:
            messagebox.showinfo("Nothing to retry", format_recovery_queue(self.recovery_queue))
            return
        confirmed = messagebox.askyesno(
            "Retry recovery queue",
            f"Retry {len(targets)} available failed file(s) in mode '{mode}'?\n\nThis will process only those inbox files.",
        )
        if confirmed:
            if plan is not None:
                execute_retry_plan(plan, lambda retry_targets: self._run_workflow("inbox", target_files=retry_targets))
            else:
                self._run_workflow("inbox", target_files=targets)

    def requeue_selected_post(self) -> None:
        if not self.selected_manifest_path:
            messagebox.showinfo("No selection", "Choose a post from the review queue first.")
            return
        confirmed = messagebox.askyesno(
            "Requeue selected post",
            "Move this selected post's primary processed media back to inbox and remove its output workspace?",
        )
        if not confirmed:
            return
        try:
            context = self.context
            result = requeue_output_workspace(
                self.selected_manifest_path.parent,
                context.inbox_dir,
                context.processed_dir,
                context.project_dir,
                captions_dir=context.captions_dir,
            )
        except WorkspaceBusyError as exc:
            messagebox.showinfo("Workspace busy", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Requeue failed", f"Could not requeue selected post:\n{exc}")
            return
        self.log(f"Requeued selected post with {len(result.moved_files)} file(s).")
        self.refresh_status()
        self.refresh_review_queue()

    def create_posting_pack_for_selected(self) -> None:
        if not self.selected_manifest_path:
            messagebox.showinfo("No selection", "Choose a post from the review queue first.")
            return
        try:
            result = create_posting_pack(
                self.selected_manifest_path,
                self.context.exports_dir,
                captions_root=self.context.captions_dir,
            )
        except Exception as exc:
            messagebox.showerror("Export failed", f"Could not create posting pack:\n{exc}")
            return
        self.log(f"Created posting pack with {result.media_count} media file(s): {result.pack_dir}")
        self.open_folder(result.pack_dir)

    def bulk_mark_filtered_ready(self) -> None:
        if not self.review_items:
            messagebox.showinfo("No posts", "There are no visible review queue posts to update.")
            return
        confirmed = messagebox.askyesno("Bulk mark ready", f"Mark all {len(self.review_items)} visible post(s) as ready?")
        if not confirmed:
            return
        try:
            count = bulk_update_status(
                [item.manifest_path for item in self.review_items],
                PublishStatus.READY.value,
                "Bulk marked ready in review queue.",
                captions_root=self.context.captions_dir,
            )
        except Exception as exc:
            messagebox.showerror("Readiness blocked", str(exc))
            return
        self.log(f"Bulk marked {count} visible post(s) ready.")
        self.refresh_review_queue(select_path=self.selected_manifest_path)

    def cleanup_safe_artifacts(self) -> None:
        context = self.context
        cleanup_plan = plan_cleanup(
            context.project_dir,
            CleanupSettings(
                logs_retention_days=context.settings.logs_retention_days,
                exports_retention_days=context.settings.posting_pack_retention_days,
                orphan_outputs_retention_days=context.settings.orphan_output_retention_days,
            ),
        )
        preview = format_cleanup_plan(cleanup_plan)
        if not cleanup_plan.items:
            messagebox.showinfo("Safe cleanup", preview)
            self.log(preview)
            return
        confirmed = messagebox.askyesno("Safe cleanup", preview + "\n\nDelete these safe retention targets now?")
        if not confirmed:
            self.log(preview)
            return
        try:
            result = execute_cleanup(cleanup_plan)
        except WorkspaceBusyError as exc:
            messagebox.showinfo("Workspace busy", str(exc))
            return
        self.log(f"Safe cleanup deleted {result.deleted_count} item(s); {result.failed_count} failed.")
        self.refresh_status()
        self.refresh_run_history()
        self.refresh_recovery_queue()
        self.refresh_review_queue(select_path=self.selected_manifest_path)

    def load_settings_tab(self) -> None:
        try:
            self.context = get_runtime_context()
        except Exception as exc:
            self.settings_status_var.set(f"Settings error: {exc}")
            return
        settings = self.context.settings
        state = build_settings_form_state(settings)
        self.settings_openai_model_var.set(state.openai_model)
        self.settings_ai_enabled_var.set(state.ai_analysis_enabled)
        self.settings_allow_fallback_var.set(state.allow_generic_fallback_captions)
        self.settings_default_providers_var.set(state.default_providers)
        self.settings_logs_retention_var.set(state.logs_retention_days)
        self.settings_pack_retention_var.set(state.posting_pack_retention_days)
        self.settings_orphan_retention_var.set(state.orphan_output_retention_days)
        self.settings_stale_draft_var.set(state.stale_draft_days)
        self.settings_preferred_platforms_var.set(state.preferred_platforms)
        self.settings_captions_dir_var.set(state.captions_dir)
        self.settings_processed_dir_var.set(state.processed_dir)
        self.settings_max_media_file_bytes_var.set(state.max_media_file_bytes)
        self.settings_max_image_pixels_var.set(state.max_image_pixels)
        self.settings_max_image_dimension_var.set(state.max_image_dimension)
        self.settings_max_video_duration_var.set(state.max_video_duration_seconds)
        self.settings_max_carousel_images_var.set(state.max_carousel_images)
        self.settings_max_analysis_payload_var.set(state.max_analysis_payload_bytes)
        self.settings_max_analysis_images_var.set(state.max_analysis_images)
        self.settings_max_analysis_dimension_var.set(state.max_analysis_image_dimension)
        self.settings_max_analysis_request_bytes_var.set(state.max_analysis_request_bytes)
        self.settings_max_analysis_video_frames_var.set(state.max_analysis_video_frames)
        load_env()
        self.settings_env_status_var.set("OpenAI API key: configured in .env" if get_openai_api_key() else "OpenAI API key: missing from .env")
        self.settings_status_var.set(f"Loaded settings from {self.context.settings_path}")

    def save_settings_tab(self) -> None:
        state = SettingsFormState(
            openai_model=self.settings_openai_model_var.get(),
            ai_analysis_enabled=self.settings_ai_enabled_var.get(),
            allow_generic_fallback_captions=self.settings_allow_fallback_var.get(),
            default_providers=self.settings_default_providers_var.get(),
            logs_retention_days=self.settings_logs_retention_var.get(),
            posting_pack_retention_days=self.settings_pack_retention_var.get(),
            orphan_output_retention_days=self.settings_orphan_retention_var.get(),
            stale_draft_days=self.settings_stale_draft_var.get(),
            preferred_platforms=self.settings_preferred_platforms_var.get(),
            captions_dir=self.settings_captions_dir_var.get(),
            processed_dir=self.settings_processed_dir_var.get(),
            max_media_file_bytes=self.settings_max_media_file_bytes_var.get(),
            max_image_pixels=self.settings_max_image_pixels_var.get(),
            max_image_dimension=self.settings_max_image_dimension_var.get(),
            max_video_duration_seconds=self.settings_max_video_duration_var.get(),
            max_carousel_images=self.settings_max_carousel_images_var.get(),
            max_analysis_payload_bytes=self.settings_max_analysis_payload_var.get(),
            max_analysis_images=self.settings_max_analysis_images_var.get(),
            max_analysis_image_dimension=self.settings_max_analysis_dimension_var.get(),
            max_analysis_request_bytes=self.settings_max_analysis_request_bytes_var.get(),
            max_analysis_video_frames=self.settings_max_analysis_video_frames_var.get(),
        )
        try:
            settings = parse_settings_form_state(state)
            candidate_context = build_app_context(BASE_DIR, settings_path=SETTINGS_PATH, settings=settings)
            prepare_app_context(candidate_context)
            save_settings(candidate_context.settings_path, settings)
            self.context = candidate_context
        except Exception as exc:
            messagebox.showerror("Settings error", str(exc))
            return
        self.settings_status_var.set(f"Saved settings to {self.context.settings_path}; the next operation uses these folders.")
        self.log("Saved non-secret settings.")
        self.refresh_status()
        self.refresh_review_queue(select_path=self.selected_manifest_path)
        self.refresh_recovery_queue()

    def save_review(self, workflow_status: str | None = None) -> None:
        if not self.selected_manifest_path:
            messagebox.showinfo("No selection", "Choose a post from the review queue first.")
            return

        try:
            manifest = load_manifest(self.selected_manifest_path)
        except Exception as exc:
            messagebox.showerror("Manifest error", f"Could not load manifest:\n{exc}")
            return

        title = self.title_entry.get().strip()
        description = self.description_text.get("1.0", END).strip()
        hashtags = self.hashtags_entry.get().strip()
        selected_providers = [name for name, var in self.provider_vars.items() if var.get()]
        next_status = workflow_status or manifest.get("publishing", {}).get("workflow_status", PublishStatus.DRAFT.value)

        if not title:
            messagebox.showerror("Missing title", "Add a title before saving the review.")
            return
        if not description:
            messagebox.showerror("Missing description", "Add a description before saving the review.")
            return

        try:
            updated_manifest = update_manifest_review(
                manifest,
                title=title,
                description=description,
                hashtags=hashtags,
                selected_providers=selected_providers,
                workflow_status=next_status,
                note=f"Updated in desktop review queue with {len(normalize_hashtag_list(hashtags))} hashtag(s).",
                readiness_validator=lambda candidate: readiness_reports_for_review(self.selected_manifest_path, candidate),
            )
        except Exception as exc:
            messagebox.showerror("Readiness blocked", str(exc))
            return

        try:
            save_manifest(self.selected_manifest_path, updated_manifest, captions_root=self.context.captions_dir)
        except Exception as exc:
            messagebox.showerror("Save failed", f"Could not save review changes:\n{exc}")
            return

        self.log(
            f"Saved review for {updated_manifest.get('post_id', self.selected_manifest_path.parent.name)} "
            f"with status {next_status}."
        )
        self.refresh_review_queue(select_path=self.selected_manifest_path)

    def add_files_to_inbox(self) -> None:
        context = ensure_project_dirs(self.context)
        selected = filedialog.askopenfilenames(
            title="Choose files for the inbox",
            filetypes=[
                ("Supported media", "*.png *.jpg *.jpeg *.gif *.webp *.mp4 *.mov *.avi *.mkv *.webm"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return

        copied = 0
        skipped = 0
        for raw_path in selected:
            source = Path(raw_path)
            if not is_supported_media_file(source):
                skipped += 1
                continue
            try:
                destination = self._unique_destination(resolve_output_under(context.inbox_dir, require_plain_filename(source.name)))
                destination = resolve_output_under(context.inbox_dir, destination)
            except ValueError:
                skipped += 1
                continue
            shutil.copy2(source, destination)
            copied += 1

        self.refresh_status()
        self.log(f"Added {copied} file(s) to inbox.")
        if skipped:
            self.log(f"Skipped {skipped} unsupported file(s).")

    def _unique_destination(self, destination: Path) -> Path:
        return unique_destination(destination)

    def process_inbox(self) -> None:
        self._run_workflow("inbox")

    def dry_run_inbox(self) -> None:
        self._run_workflow("inbox", dry_run=True)

    def check_setup(self) -> None:
        self._run_workflow("setup")

    def requeue_processed_files(self) -> None:
        context = ensure_project_dirs(self.context)
        plan = collect_requeue_plan(context.outputs_dir, context.processed_dir)
        output_folders = plan.output_folders
        processed_files = plan.processed_files
        if not output_folders and not processed_files:
            messagebox.showinfo("Nothing to requeue", "There are no output workspaces or legacy processed files to move back into inbox.")
            return

        confirmed = messagebox.askyesno(
            "Requeue processed files",
            build_requeue_confirmation(plan),
        )
        if not confirmed:
            return

        try:
            result = execute_requeue_plan(
                plan,
                context.inbox_dir,
                context.captions_dir,
                context.project_dir,
                processed_dir=context.processed_dir,
            )
        except WorkspaceBusyError as exc:
            messagebox.showinfo("Workspace busy", str(exc))
            return

        self.refresh_status()
        self.refresh_review_queue()
        self.log(f"Requeued {result.moved_count} file(s) from processed outputs back to inbox.")
        if result.removed_workspaces:
            self.log(f"Removed {result.removed_workspaces} output workspace(s).")
        if result.removed_captions:
            self.log(f"Removed {result.removed_captions} old caption file(s) so the next run starts clean.")

    def _run_workflow(self, action: str, dry_run: bool = False, target_files: list[Path] | None = None) -> None:
        if not self.accepting_work:
            messagebox.showinfo("Closing", "The app is waiting for the current operation to stop.")
            return
        if self.running:
            messagebox.showinfo("Busy", "A batch is already running.")
            return

        try:
            limit = parse_limit_value(self.limit_var.get())
        except ValueError as exc:
            messagebox.showerror("Invalid limit", str(exc))
            return

        self.running = True
        self.cancellation_token = CancellationToken()
        self._set_buttons_enabled(False)
        self.log("")
        self.log(format_workflow_label(action, limit, dry_run, target_files))
        thread = threading.Thread(
            target=self._worker,
            args=(action, limit, dry_run, target_files, self.cancellation_token),
            daemon=True,
        )
        thread.start()

    def _worker(
        self,
        action: str,
        limit: int | None,
        dry_run: bool,
        target_files: list[Path] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        context = ensure_project_dirs(self.context)
        writer = QueueWriter(self.log_queue)
        exit_code = 0
        try:
            with redirect_stdout(writer), redirect_stderr(writer):
                exit_code = run_workflow_action(
                    action,
                    limit=limit,
                    dry_run=dry_run,
                    target_files=target_files,
                    setup_check_func=lambda: setup_check(context),
                    run_inbox_processing_func=lambda **kwargs: run_inbox_processing(
                        **kwargs,
                        context=context,
                        cancellation_token=cancellation_token,
                    ),
                    has_failed_results_func=has_failed_results,
                )
        except Exception as exc:
            writer.write(f"ERROR: {exc}\n")
            exit_code = 1
        finally:
            writer.flush()
        self.log_queue.put(("done", str(exit_code)))

    def _drain_log_queue(self) -> None:
        try:
            while True:
                kind, payload = self.log_queue.get_nowait()
                if kind == "line":
                    self.log(payload.rstrip())
                elif kind == "done":
                    self.running = False
                    self.cancellation_token = None
                    self._set_buttons_enabled(True)
                    self.refresh_status()
                    self.refresh_run_history()
                    self.refresh_recovery_queue()
                    self.refresh_review_queue(select_path=self.selected_manifest_path)
                    self.log("Finished." if payload == "0" else f"Finished with exit code {payload}.")
                    if self.shutting_down:
                        self.root.after_idle(self.root.destroy)
                        return
        except Empty:
            pass
        if not self.shutting_down or self.running:
            self.root.after(150, self._drain_log_queue)

    def request_shutdown(self) -> None:
        """Stop accepting new work and wait for the active safe boundary before closing."""

        self.accepting_work = False
        if not self.running:
            self.root.destroy()
            return
        self.shutting_down = True
        if self.cancellation_token is not None:
            self.cancellation_token.request()
        self.log("Cancellation requested. The app will close after the current safe step finishes.")

    def _set_buttons_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in (
            self.add_button,
            self.process_button,
            self.dry_run_button,
            self.requeue_button,
            self.setup_button,
            self.cleanup_button,
            self.open_inbox_button,
            self.open_captions_button,
            self.open_processed_button,
            self.open_outputs_button,
            self.open_logs_button,
            self.open_exports_button,
            self.refresh_runs_button,
            self.open_run_log_button,
            self.retry_failed_button,
            self.retry_all_failed_button,
            self.retry_failed_videos_button,
            self.retry_failed_images_button,
            self.refresh_queue_button,
            self.open_selected_button,
            self.requeue_selected_button,
            self.save_review_button,
            self.mark_draft_button,
            self.mark_ready_button,
            self.create_pack_button,
            self.bulk_ready_button,
            self.reload_settings_button,
            self.save_settings_button,
        ):
            button.configure(state=state)

    def open_folder(self, path: Path) -> None:
        ensure_project_dirs(self.context)
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # type: ignore[attr-defined]

    def open_path(self, path: Path) -> None:
        if not path.exists():
            messagebox.showerror("Missing path", f"Could not find:\n{path}")
            return
        os.startfile(path)  # type: ignore[attr-defined]


def run_packaged_smoke_test(context: AppContext | None = None) -> int:
    """Verify the frozen application's imports and writable local layout.

    This deliberately avoids constructing ``Tk`` so CI can verify the onefile
    executable on a clean Windows runner without a visible desktop window.
    """

    active_context = ensure_project_dirs(context or get_runtime_context())
    for module_name in PACKAGE_HIDDEN_IMPORTS:
        importlib.import_module(module_name)
    print(f"Packaged smoke test passed for {build_version_label()} at {active_context.project_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Blast From the Ads desktop app")
    parser.add_argument("--smoke-test", action="store_true", help="Verify packaged imports and exit without opening the UI")
    args = parser.parse_args(argv)

    if args.smoke_test:
        return run_packaged_smoke_test()

    ensure_project_dirs(get_runtime_context())
    root = Tk()
    SocialBatchApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
