"""Command-line entry point.

Usage::

    python -m app.pipeline [path-to.eml]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .runner import run_pipeline

DEFAULT_INPUT = Path("data/sample_emails/progress_report.eml")


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(
        prog="app.pipeline",
        description="Run the offline SchoolMail Bridge pipeline on one .eml file.",
    )
    cli.add_argument(
        "input",
        nargs="?",
        default=str(DEFAULT_INPUT),
        help=f"Path to the .eml file to process (default: {DEFAULT_INPUT}).",
    )
    args = cli.parse_args(argv)

    eml_path = Path(args.input)
    if not eml_path.is_file():
        print(f"ERROR: input not found: {eml_path}", file=sys.stderr)
        return 1

    result = run_pipeline(eml_path)
    print("Pipeline result:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
