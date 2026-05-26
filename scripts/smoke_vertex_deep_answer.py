"""Manual smoke test for live Vertex AI Deep Answer Mode."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from missouri_public_data_ai.ask_model import AskEngine  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--question",
        default="What year has the highest transportation spending and by how much?",
    )
    parser.add_argument("--allow-missing", action="store_true")
    args = parser.parse_args()

    engine = AskEngine()
    if not engine.deep_answer_provider.is_available():
        message = (
            "Vertex AI is not available. Set GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, "
            "GOOGLE_GENAI_USE_VERTEXAI=True, and authenticate Google Cloud before running this smoke test."
        )
        print(message)
        raise SystemExit(0 if args.allow_missing else 2)

    result = engine.ask(args.question)
    print(
        json.dumps(
            {
                "question": args.question,
                "deep_answer_status": result.get("deep_answer_status"),
                "deep_answer_provider": result.get("deep_answer_provider"),
                "deep_answer_model": result.get("deep_answer_model"),
                "evidence_tool_calls": result.get("evidence_tool_calls"),
                "answer": result.get("answer"),
            },
            indent=2,
        )
    )
    if result.get("deep_answer_status") != "synthesized":
        raise SystemExit("Expected live Vertex synthesis.")


if __name__ == "__main__":
    main()
