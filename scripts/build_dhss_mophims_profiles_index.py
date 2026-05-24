"""Build the local DHSS MOPHIMS statewide profile aggregate index."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from missouri_tiny_llm.dhss_mophims_profiles_index import main  # noqa: E402


if __name__ == "__main__":
    main()
