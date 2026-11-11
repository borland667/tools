#!/usr/bin/env python3
"""Run a bounded read-only local-model OpenCode integration probe."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_model_eval.harness import main

if __name__ == '__main__':
    raise SystemExit(main())
