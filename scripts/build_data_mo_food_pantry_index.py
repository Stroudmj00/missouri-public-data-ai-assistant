"""CLI wrapper for the selected data.mo.gov Food Pantry List index."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from missouri_tiny_llm.data_mo_food_pantry_index import main  # noqa: E402


if __name__ == "__main__":
    main()
