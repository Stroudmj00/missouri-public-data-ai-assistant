"""Build the manifest-driven generalized evidence index."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from missouri_public_data_ai.evidence_index import build_evidence_index  # noqa: E402


def main() -> None:
    force = "--force" in sys.argv
    report = build_evidence_index(force=force)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
