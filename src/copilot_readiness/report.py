"""Renderers for the gate results.

Two axes, never merged:
- Verdict (binary-ish): READY / NOT READY / INCOMPLETE, driven by the hard
  structural gates. This is the go/no-go decision.
- Finition score (0-100, per section): driven by the quality slopes (warnings).
  It communicates distance-to-ready and lets you prioritise. It can never make a
  blocked model look green (it is capped when NOT READY).

Output is "focus on fails" by default: passes are never printed unless the
verbosity is turned all the way up. Formats: console (verbosity ladder), json,
markdown (PR-comment dashboard), and github (workflow annotations).
"""

from __future__ import annotations

import json
from typing import List, Optional

from .gate import Effort, ModelResult, Verdict
from .rules.base import Section, Status

# Marker so the GitHub Action can find and update its sticky PR comment.
COMMENT_MARKER = "<!-- copilot-readiness-linter -->"

# Verbosity ladder (console only).
QUIET = -1     # per-model summary + totals
NORMAL = 0     # + blocking gates (the fails)
VERBOSE = 1    # + warnings
DEBUG = 2      # + manual checks and passes

_SCORED_SECTIONS = [Section.STRUCTURE, Section.METADATA, Section.CALCULATIONS]
_VERDICT_ICON = {Verdict.READY: "✅", Verdict.NOT_READY: "❌", Verdict.INCOMPLETE: "⚠️"}
_VERDICT_ORDER = {Verdict.NOT_READY: 0, Verdict.INCOMPLETE: 1, Verdict.READY: 2}

_ANSI = {"red": "31", "green": "32", "yellow": "33", "cyan": "36", "dim": "2", "bold": "1"}

# Effort never uses green: green reads as "good/ready" and would visually soften a
# NOT READY verdict. Near fix is cyan (neutral "quick win"), then yellow, then red.
_EFFORT_COLOR = {
    Effort.NONE: "dim",
    Effort.NEAR_FIX: "cyan",
    Effort.NEEDS_WORK: "yellow",
    Effort.MAJOR_REWORK: "red",
    Effort.BLOCKED_ON_CONFIG: "dim",
}


class _Paint:
    """Wraps text in ANSI colour, or returns it untouched when disabled.

    Colour is applied AFTER padding so it never affects column alignment (ANSI
    codes occupy zero terminal columns)."""

    def __init__(self, enabled: bool):
        self.on = enabled

    def __call__(self, text: str, color: Optional[str]) -> str:
        if not self.on or not color:
            return text
        return f"\033[{_ANSI[color]}m{text}\033[0m"


def _verdict_color(v: Verdict) -> str:
    return {Verdict.READY: "green", Verdict.NOT_READY: "red", Verdict.INCOMPLETE: "yellow"}[v]


def _score_color(value: Optional[int]) -> Optional[str]:
    if value is None:
        return "dim"
    if value < 50:
        return "red"
    if value < 75:
        return "yellow"
    return "green"


def _overall_ready(results: List[ModelResult]) -> bool:
    return all(r.is_ready for r in results)


def _score_str(value: Optional[int]) -> str:
    return f"{value}" if value is not None else "n/a"


def _totals(results: List[ModelResult]):
    return {
        "ready": sum(1 for r in results if r.verdict == Verdict.READY),
        "incomplete": sum(1 for r in results if r.verdict == Verdict.INCOMPLETE),
        "not_ready": sum(1 for r in results if r.verdict == Verdict.NOT_READY),
        "models": len(results),
        "blocking": sum(len(r.real_blocking) for r in results),
        "warnings": sum(len(r.warnings) for r in results),
        "passed": sum(len(r.passed) for r in results),
        "manual": sum(len(r.manual) for r in results),
    }


def _worst_first(results: List[ModelResult]):
    return sorted(
        results,
        key=lambda r: (_VERDICT_ORDER[r.verdict], -len(r.real_blocking), -len(r.warnings)),
    )


# --------------------------------------------------------------------------- #
# Console
# --------------------------------------------------------------------------- #

def render_console(results: List[ModelResult], verbosity: int = NORMAL, color: bool = False) -> str:
    paint = _Paint(color)
    lines: List[str] = []
    t = _totals(results)
    plural = "s" if t["models"] != 1 else ""
    lines.append(
        f"Copilot Readiness · {t['models']} model{plural} "
        f"({t['ready']} ready · {t['incomplete']} incomplete · {t['not_ready']} not ready)"
    )
    lines.append("")

    # Aligned table. Columns: (header, width, align).
    name_w = min(max((len(r.model_name) for r in results), default=5), 38)
    cols = [
        ("VERDICT", 10, "l"),
        ("EFFORT", 17, "l"),
        ("MODEL", name_w, "l"),
        ("SCORE", 5, "r"),
        ("STRUCT", 6, "r"),
        ("META", 4, "r"),
        ("CALC", 4, "r"),
        ("BLOCK", 5, "r"),
        ("WARN", 5, "r"),
        ("PASS", 5, "r"),
    ]

    def cell(text: str, width: int, align: str, c: Optional[str] = None) -> str:
        padded = text.rjust(width) if align == "r" else text.ljust(width)
        return paint(padded, c)

    header = "  " + "  ".join(cell(h, w, a) for h, w, a in cols)
    rule = "  " + paint("-" * (len(header) - 2), "dim")
    lines.append(paint(header, "dim"))
    lines.append(rule)

    for r in _worst_first(results):
        ss = r.section_scores
        row = "  " + "  ".join([
            cell(r.verdict.value, 10, "l", _verdict_color(r.verdict)),
            cell(r.effort.value, 17, "l", _EFFORT_COLOR[r.effort]),
            cell(r.model_name[:name_w], name_w, "l"),
            cell(_score_str(r.finition), 5, "r", _score_color(r.finition)),
            cell(_score_str(ss[Section.STRUCTURE]), 6, "r", _score_color(ss[Section.STRUCTURE])),
            cell(_score_str(ss[Section.METADATA]), 4, "r", _score_color(ss[Section.METADATA])),
            cell(_score_str(ss[Section.CALCULATIONS]), 4, "r", _score_color(ss[Section.CALCULATIONS])),
            cell(str(len(r.real_blocking)), 5, "r"),
            cell(str(len(r.warnings)), 5, "r"),
            cell(str(len(r.passed)), 5, "r"),
        ])
        lines.append(row)

    lines.append(rule)
    totals_row = "  " + "  ".join([
        cell("TOTAL", 10, "l", "dim"),
        cell("", 17, "l"),
        cell("", name_w, "l"),
        cell("", 5, "r"),
        cell("", 6, "r"),
        cell("", 4, "r"),
        cell("", 4, "r"),
        cell(str(t["blocking"]), 5, "r"),
        cell(str(t["warnings"]), 5, "r"),
        cell(str(t["passed"]), 5, "r"),
    ])
    lines.append(totals_row)
    lines.append("")

    if verbosity >= NORMAL and any(r.real_blocking for r in results):
        lines.append("Blocking gates (must fix)")
        lines.append("-" * 25)
        for r in _worst_first(results):
            if not r.real_blocking:
                continue
            lines.append(f"  {r.model_name}")
            for f in r.real_blocking:
                obs = f"  ({f.observed})" if f.observed else ""
                lines.append(f"    x {f.title} :: {f.obj}{obs}")
        lines.append("")

    if verbosity >= NORMAL and any(r.config_gaps for r in results):
        lines.append("Incomplete (cannot assess until resolved)")
        lines.append("-" * 25)
        for r in _worst_first(results):
            for f in r.config_gaps:
                lines.append(f"  {r.model_name}: {f.message}")
        lines.append("")

    if verbosity >= VERBOSE:
        _append_detail(lines, results, "Warnings", lambda r: r.warnings)

    if verbosity >= DEBUG:
        _append_detail(lines, results, "Manual checks", lambda r: r.manual)
        _append_detail(lines, results, "Passed", lambda r: r.passed)

    ready_all = _overall_ready(results)
    overall = "READY" if ready_all else "NOT READY"
    lines.append(
        f"Summary: {t['ready']} ready, {t['incomplete']} incomplete, {t['not_ready']} not ready  "
        f"| blocking {t['blocking']} | warnings {t['warnings']} "
        f"| passed {t['passed']} | manual {t['manual']}"
    )
    lines.append("Overall: " + paint(overall, "green" if ready_all else "red"))
    return "\n".join(lines)


def _append_detail(lines, results, heading, selector) -> None:
    if not any(selector(r) for r in results):
        return
    lines.append(heading)
    lines.append("-" * len(heading))
    for r in _worst_first(results):
        items = selector(r)
        if not items:
            continue
        lines.append(f"  {r.model_name}")
        for f in items:
            obs = f"  ({f.observed})" if f.observed else ""
            lines.append(f"    - {f.title} :: {f.obj}{obs}")
    lines.append("")


# --------------------------------------------------------------------------- #
# JSON
# --------------------------------------------------------------------------- #

def render_json(results: List[ModelResult]) -> str:
    payload = {
        "overall_ready": _overall_ready(results),
        "summary": _totals(results),
        "models": [
            {
                "model": r.model_name,
                "source_path": r.source_path,
                "verdict": r.verdict.value,
                "effort": r.effort.value,
                "ready": r.is_ready,
                "finition_score": r.finition,
                "section_scores": {s.value: r.section_scores[s] for s in _SCORED_SECTIONS},
                "blocking_count": len(r.real_blocking),
                "warning_count": len(r.warnings),
                "passed_count": len(r.passed),
                "manual_count": len(r.manual),
                "findings": [
                    {
                        "rule_id": f.rule_id,
                        "section": f.section.value,
                        "title": f.title,
                        "object": f.obj,
                        "status": f.status.value,
                        "severity": f.severity.value,
                        "observed": f.observed,
                        "message": f.message,
                        "auto_verified": f.auto_verified,
                    }
                    for f in r.findings
                ],
            }
            for r in results
        ],
    }
    return json.dumps(payload, indent=2)


# --------------------------------------------------------------------------- #
# Markdown (PR comment / job summary dashboard)
# --------------------------------------------------------------------------- #

def render_markdown(results: List[ModelResult]) -> str:
    t = _totals(results)
    overall_ready = _overall_ready(results)
    lines: List[str] = [COMMENT_MARKER, "# Copilot Readiness Scorecard", ""]
    banner = "✅ All models READY" if overall_ready else "❌ NOT READY"
    lines.append(
        f"**{banner}** · {t['ready']} ready, {t['incomplete']} incomplete, "
        f"{t['not_ready']} not ready (of {t['models']})"
    )
    lines.append("")
    lines.append(
        f"`{t['blocking']} blocking` · `{t['warnings']} warnings` · "
        f"`{t['passed']} passed` · `{t['manual']} manual`"
    )
    lines.append("")

    # Summary table: the dashboard.
    lines.append("| Model | Verdict | Effort | Finition | Blocking | Warnings | Passed |")
    lines.append("|---|---|---|--:|--:|--:|--:|")
    for r in _worst_first(results):
        verdict = f"{_VERDICT_ICON[r.verdict]} {r.verdict.value}"
        lines.append(
            f"| {r.model_name} | {verdict} | {r.effort.value} | {_score_str(r.finition)}/100 "
            f"| {len(r.real_blocking)} | {len(r.warnings)} | {len(r.passed)} |"
        )
    lines.append("")

    # Per-model detail, focused on fails, collapsed.
    for r in _worst_first(results):
        if r.verdict == Verdict.READY and not r.warnings:
            continue
        summary = (
            f"{_VERDICT_ICON[r.verdict]} {r.model_name} · {r.verdict.value}, "
            f"finition {_score_str(r.finition)}/100"
        )
        lines.append(f"<details><summary>{summary}</summary>")
        lines.append("")
        ss = r.section_scores
        lines.append(
            "Section scores: "
            + " · ".join(f"{s.value} {_score_str(ss[s])}/100" for s in _SCORED_SECTIONS)
        )
        lines.append("")
        if r.config_gaps:
            for f in r.config_gaps:
                lines.append(f"> ⚠️ Incomplete: {f.message}")
            lines.append("")
        if r.real_blocking:
            lines.append("#### Blocking gates")
            for f in r.real_blocking:
                lines.append(f"- ❌ **{f.title}** ({f.obj}): {f.message}")
            lines.append("")
        if r.warnings:
            lines.append(f"<details><summary>Warnings ({len(r.warnings)})</summary>")
            lines.append("")
            for f in r.warnings:
                obs = f" _(observed: {f.observed})_" if f.observed else ""
                lines.append(f"- ⚠️ **{f.title}** ({f.obj}): {f.message}{obs}")
            lines.append("")
            lines.append("</details>")
            lines.append("")
        if r.manual:
            lines.append(f"<details><summary>Manual checklist ({len(r.manual)})</summary>")
            lines.append("")
            for f in r.manual:
                lines.append(f"- [ ] **{f.title}**: {f.message}")
            lines.append("")
            lines.append("</details>")
            lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append(
        "_Layer 1 static gate. Verdict is driven by the hard structural gates; the "
        "finition score reflects the quality slopes and is capped when NOT READY. "
        "Manual checklist items must be confirmed by hand._"
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# GitHub workflow annotations
# --------------------------------------------------------------------------- #

def _gh_data(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _gh_prop(text: str) -> str:
    return _gh_data(text).replace(",", "%2C").replace(":", "%3A")


def render_github(results: List[ModelResult]) -> str:
    """Error annotation per blocking gate, warning per incomplete model, notice
    summary. Warnings (the slopes) are not annotated; they live in the summary."""
    lines: List[str] = []
    for r in _worst_first(results):
        for f in r.real_blocking:
            title = _gh_prop(f"Copilot Readiness: {f.title}")
            msg = _gh_data(f"[{r.model_name}] {f.obj}: {f.message}")
            lines.append(f"::error title={title}::{msg}")
        for f in r.config_gaps:
            msg = _gh_data(f"[{r.model_name}] {f.message}")
            lines.append(f"::warning title={_gh_prop('Copilot Readiness: Incomplete')}::{msg}")
    t = _totals(results)
    summary = _gh_data(
        f"{t['ready']} ready, {t['incomplete']} incomplete, {t['not_ready']} not ready. "
        f"{t['blocking']} blocking, {t['warnings']} warnings."
    )
    lines.append(f"::notice title=Copilot Readiness::{summary}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #

def render(results: List[ModelResult], fmt: str, verbosity: int = NORMAL, color: bool = False) -> str:
    if fmt == "json":
        return render_json(results)
    if fmt == "markdown":
        return render_markdown(results)
    if fmt == "github":
        return render_github(results)
    return render_console(results, verbosity, color)
