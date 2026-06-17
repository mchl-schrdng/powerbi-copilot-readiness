"""Command-line entrypoint for the Copilot readiness linter."""

from __future__ import annotations

import argparse
import glob
import os
import sys
from typing import List, Optional

from .config import load_config
from .gate import ModelResult, Verdict, evaluate
from .report import render
from .rules import run_all_rules
from .tmdl_parser import parse_model


def discover_models(target: str, model_glob: str = "**/*.SemanticModel") -> List[str]:
    """Find .SemanticModel folders at or under the target path, using model_glob."""
    target = os.path.normpath(target)
    if target.endswith(".SemanticModel") and os.path.isdir(target):
        return [target]

    matches = sorted(
        path
        for path in glob.glob(os.path.join(target, model_glob), recursive=True)
        if os.path.isdir(path)
    )
    # Include the target itself if it is directly a model folder by another name
    # but contains a definition directory.
    if not matches and os.path.isdir(os.path.join(target, "definition")):
        matches = [target]
    return matches


def _lint(args: argparse.Namespace) -> int:
    config_path = args.config
    if config_path is None:
        default_config = os.path.join(os.getcwd(), "readiness.yaml")
        config_path = default_config if os.path.isfile(default_config) else None
    config = load_config(config_path)

    model_paths = discover_models(args.target, config.model_glob)
    if not model_paths:
        sys.stderr.write(f"No .SemanticModel folders found under: {args.target}\n")
        return 2

    results: List[ModelResult] = []
    for path in model_paths:
        model = parse_model(path)
        findings = run_all_rules(model, config)
        results.append(evaluate(model.name, path, findings))

    verbosity = -1 if args.quiet else args.verbose
    color = (
        args.format == "console"
        and not args.output
        and not args.no_color
        and os.environ.get("NO_COLOR") is None
        and sys.stdout.isatty()
    )
    output = render(results, args.format, verbosity, color)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output + "\n")
    else:
        print(output)

    # Exit non-zero unless every model is READY. INCOMPLETE counts as a failure
    # (a model cannot be certified without its fact-table declaration) unless the
    # user opts out with --allow-incomplete, which fails only on real defects.
    if any(r.verdict == Verdict.NOT_READY for r in results):
        return 1
    if any(r.verdict == Verdict.INCOMPLETE for r in results) and not args.allow_incomplete:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="copilot-readiness",
        description="Gate Power BI semantic models for Copilot 'Talk to your data' readiness.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    lint = subparsers.add_parser("lint", help="Lint one or more .SemanticModel folders.")
    lint.add_argument("target", help="Path to a .SemanticModel folder or a repo root to scan.")
    lint.add_argument("--config", default=None, help="Path to readiness.yaml (default: ./readiness.yaml if present).")
    lint.add_argument(
        "--format",
        choices=["console", "json", "markdown", "github"],
        default="console",
        help="Output format. 'github' emits workflow annotations.",
    )
    lint.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase console detail: -v adds warnings, -vv adds manual checks and passes.",
    )
    lint.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Console: show only the per-model summary and totals, no finding detail.",
    )
    lint.add_argument("--no-color", action="store_true", help="Disable coloured console output.")
    lint.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Exit 0 for INCOMPLETE models (only a missing fact declaration); fail only on real defects.",
    )
    lint.add_argument("--output", default=None, help="Write the report to a file instead of stdout.")
    lint.set_defaults(func=_lint)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
