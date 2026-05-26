"""CLI wrapper for the selected data.mo.gov DNR oil and gas permit index."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from missouri_public_data_ai.data_mo_dnr_oil_gas_index import main  # noqa: E402


if __name__ == "__main__":
    main()
