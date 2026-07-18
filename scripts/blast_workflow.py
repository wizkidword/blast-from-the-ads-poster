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

try:
    from recovery_service import build_retry_plan, execute_retry_plan
except ImportError:
    from scripts.recovery_service import build_retry_plan, execute_retry_plan

try:
    from safe_paths import UnsafePathError, resolve_existing_under
except ImportError:
    from scripts.safe_paths import UnsafePathError, resolve_existing_under


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

    retry = subparsers.add_parser("retry", help="Retry failed inbox media from run ledgers")
    retry.add_argument("--run", help="Run-log filename to retry; defaults to all inbox-run logs")
    retry.add_argument("--mode", choices=("all", "videos", "images"), default="all", help="Limit retries by media type")

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

    if args.command == "retry":
        try:
            context = build_app_context()
            prepare_app_context(context)
            if args.run:
                log_paths = [resolve_existing_under(context.logs_dir, args.run)]
            else:
                log_paths = sorted(context.logs_dir.glob("inbox-run-*.json"), key=lambda path: path.name, reverse=True)
            plan = build_retry_plan(log_paths, context.inbox_dir, outputs_dir=context.outputs_dir, mode=args.mode)
        except (OSError, ValueError, UnsafePathError) as exc:
            print(f"Configuration error: {exc}")
            return 1

        for error in plan.errors:
            print(f"Recovery warning: {error}")
        if not plan.retry_files:
            print("No failed files are currently safe to retry.")
            if plan.missing_files:
                print("Missing: " + ", ".join(plan.missing_files))
            if plan.skipped_files:
                print("Skipped: " + ", ".join(plan.skipped_files))
            return 1 if plan.errors else 0
        print(f"Retrying {len(plan.retry_files)} failed file(s) in {args.mode} mode.")
        summary = execute_retry_plan(
            plan,
            lambda target_files: run_inbox_processing(target_files=target_files, context=context),
        )
        return 1 if summary is not None and has_failed_results(summary) else 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
