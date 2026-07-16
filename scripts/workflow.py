#!/usr/bin/env python3
from __future__ import annotations

import argparse
try:
    from blast_workflow import main
except ImportError:
    from scripts.blast_workflow import main


if __name__ == "__main__":
    raise SystemExit(main())
