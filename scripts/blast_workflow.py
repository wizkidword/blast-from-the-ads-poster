#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import sys

try:
    from process_inbox_social import get_openai_model, has_failed_results, load_env, run_inbox_processing
except ImportError:
    from scripts.process_inbox_social import get_openai_model, has_failed_results, load_env, run_inbox_processing

try:
    from app_context import AppContext, build_app_context, prepare_app_context
except ImportError:
    from scripts.app_context import AppContext, build_app_context, prepare_app_context

try:
    from app_metadata import build_version_label
except ImportError:
    from scripts.app_metadata import build_version_label

try:
    from publishing import list_provider_names
except ImportError:
    from scripts.publishing import list_provider_names


def configure_standard_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="replace")


def setup_check(context: AppContext | None = None) -> int:
    load_env()
    try:
        active_context = context or build_app_context()
        prepare_app_context(active_context)
    except Exception as exc:
        print(f"Configuration error: {exc}")
        return 1

    checks: list[tuple[str, bool, str]] = []
    checks.append(("OPENAI_API_KEY configured", bool(os.environ.get("OPENAI_API_KEY")), "Add it to .env"))
    checks.append(("ffmpeg available", shutil.which("ffmpeg") is not None, "Install ffmpeg and add it to PATH"))
    checks.append(("ffprobe available", shutil.which("ffprobe") is not None, "Install ffmpeg and add it to PATH"))

    try:
        import requests  # noqa: F401

        requests_ok = True
    except ImportError:
        requests_ok = False
    checks.append(("Python package 'requests'", requests_ok, "Run pip install -r requirements.txt"))
    checks.append(("Project folders ready", active_context.inbox_dir.exists(), "Fix the reported directory configuration"))
    checks.append(("Outputs folder ready", active_context.outputs_dir.exists(), "Fix the reported directory configuration"))

    print(f"\n{build_version_label()} Setup Check\n")
    failures = 0
    for label, ok, help_text in checks:
        prefix = "OK" if ok else "MISSING"
        print(f"[{prefix}] {label}")
        if not ok:
            failures += 1
            print(f"         {help_text}")

    print(f"\nProject folder: {active_context.project_dir}")
    print(f"Caption exports: {active_context.captions_dir}")
    print(f"Processed media: {active_context.processed_dir}")
    print(f"OpenAI model: {get_openai_model()}")
    print(f"Publish providers: {', '.join(list_provider_names()) or 'None'}")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Blast From the Ads local workflow")
    subparsers = parser.add_subparsers(dest="command")

    inbox = subparsers.add_parser("inbox", help="Process files from inbox/")
    inbox.add_argument("--limit", type=int, help="Limit number of files processed")
    inbox.add_argument("--dry-run", action="store_true", help="Analyze without writing or moving files")

    subparsers.add_parser("setup", help="Check local dependencies and config")
    return parser


def main() -> int:
    configure_standard_streams()
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "inbox":
        try:
            context = build_app_context()
            summary = run_inbox_processing(limit=args.limit, dry_run=args.dry_run, context=context)
        except Exception as exc:
            print(f"Configuration error: {exc}")
            return 1
        return 1 if has_failed_results(summary) else 0

    if args.command == "setup":
        return setup_check()

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
