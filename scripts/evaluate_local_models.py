#!/usr/bin/env python3
"""Run the versioned local-model evaluation pilot from any working directory."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_model_eval.runner import main

if __name__ == '__main__':
    raise SystemExit(main())
