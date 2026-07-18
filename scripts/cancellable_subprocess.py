"""Subprocess helpers that let a caller stop long local media work safely."""
from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from typing import Sequence


def run_command(
    command: Sequence[str],
    *,
    timeout: float,
    cancellation_check: Callable[[], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command, checking cancellation while it is still running.

    The no-cancellation path deliberately preserves the application's existing
    ``subprocess.run`` behavior, including its test-friendly call shape.
    """

    if cancellation_check is None:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)

    cancellation_check()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + timeout
    try:
        while process.poll() is None:
            cancellation_check()
            if time.monotonic() >= deadline:
                process.kill()
                process.communicate()
                raise subprocess.TimeoutExpired(command, timeout)
            time.sleep(0.1)
        stdout, stderr = process.communicate()
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except BaseException:
        if process.poll() is None:
            process.kill()
            process.communicate()
        raise
