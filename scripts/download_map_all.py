"""Command wrapper for MAP all-files inventory/download."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from missouri_tiny_llm.map_all_download import main  # noqa: E402


if __name__ == "__main__":
    main()
