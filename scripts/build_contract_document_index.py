"""Command wrapper for extracting public Missouri contract PDF text locally."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from missouri_tiny_llm.contract_documents import main  # noqa: E402


if __name__ == "__main__":
    main()
