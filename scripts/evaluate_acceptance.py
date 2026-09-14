from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from courtvision.evaluation import evaluate_manifest  # noqa: E402


def _emit(payload: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the eight BadmintonAnalysis platform acceptance gates."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optionally write the same JSON report to this path.",
    )
    args = parser.parse_args(argv)

    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        report = evaluate_manifest(manifest)
        _emit(report, args.output)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        _emit(
            {
                "schema_version": 1,
                "status": "error",
                "passed": False,
                "error": str(error),
            },
            args.output,
        )
        return 3

    if report["status"] == "pass":
        return 0
    if report["status"] == "fail":
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
