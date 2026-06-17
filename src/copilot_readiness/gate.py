"""Gate decision: turn a list of findings into READY or NOT READY.

The rule is the one from the article: a single blocking (GATE) failure means the
model is NOT READY, regardless of how clean everything else is.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from .rules.base import Finding, Section, Status

# Blocking findings that signal a missing input (not a model defect). A model
# whose only blocker is one of these is INCOMPLETE, not NOT READY.
CONFIG_BLOCKER_RULES = {"config.no_fact_table"}

# Findings excluded from the finition score: the missing-fact signal (a verdict
# driver, not a quality slope). MANUAL findings are excluded separately.
_SCORE_EXCLUDED_RULE_PREFIXES = ("config.",)


class Verdict(str, Enum):
    READY = "READY"
    NOT_READY = "NOT READY"
    INCOMPLETE = "INCOMPLETE"   # cannot assess: a required input was not declared


class Effort(str, Enum):
    """How far a model is from ready. A communication axis on top of the verdict;
    it never says 'ready' while a blocker exists, so it cannot soften the gate."""

    NONE = "-"
    NEAR_FIX = "Near fix"
    NEEDS_WORK = "Needs work"
    MAJOR_REWORK = "Major rework"
    BLOCKED_ON_CONFIG = "Blocked on config"


# Effort thresholds (blocking-gate counts). Tunable here if needed.
_NEAR_FIX_MAX = 2          # 1 to 2 blockers
_NEEDS_WORK_MAX = 8        # 3 to 8 blockers
_MAJOR_STRUCTURE_FLOOR = 40  # below this Structure score, it is major rework


def _score(findings: List[Finding]) -> Optional[int]:
    """Percent of scoreable checks that pass. None when nothing is scoreable.

    Scoreable = PASS/FAIL findings that are quality slopes (not the config
    verdict signal and not MANUAL checks we cannot verify statically).
    """
    considered = [
        f
        for f in findings
        if f.status in (Status.PASS, Status.FAIL)
        and not f.rule_id.startswith(_SCORE_EXCLUDED_RULE_PREFIXES)
    ]
    if not considered:
        return None
    passes = sum(1 for f in considered if f.status == Status.PASS)
    return round(100 * passes / len(considered))


@dataclass
class ModelResult:
    model_name: str
    source_path: str
    findings: List[Finding]

    @property
    def blocking(self) -> List[Finding]:
        return [f for f in self.findings if f.is_blocking]

    @property
    def real_blocking(self) -> List[Finding]:
        """Blocking gates that are genuine model defects (drive NOT READY)."""
        return [f for f in self.blocking if f.rule_id not in CONFIG_BLOCKER_RULES]

    @property
    def config_gaps(self) -> List[Finding]:
        """Blocking findings that are missing inputs (drive INCOMPLETE)."""
        return [f for f in self.blocking if f.rule_id in CONFIG_BLOCKER_RULES]

    @property
    def warnings(self) -> List[Finding]:
        return [
            f
            for f in self.findings
            if f.status == Status.FAIL and not f.is_blocking
        ]

    @property
    def manual(self) -> List[Finding]:
        return [f for f in self.findings if f.status == Status.MANUAL]

    @property
    def passed(self) -> List[Finding]:
        return [f for f in self.findings if f.status == Status.PASS]

    @property
    def verdict(self) -> Verdict:
        if self.real_blocking:
            return Verdict.NOT_READY
        if self.config_gaps:
            return Verdict.INCOMPLETE
        return Verdict.READY

    @property
    def is_ready(self) -> bool:
        return self.verdict == Verdict.READY

    @property
    def effort(self) -> Effort:
        """Remediation distance, derived from blocker count and structure score."""
        if self.verdict == Verdict.READY:
            return Effort.NONE
        if self.verdict == Verdict.INCOMPLETE:
            return Effort.BLOCKED_ON_CONFIG
        n = len(self.real_blocking)
        structure = self.section_scores.get(Section.STRUCTURE)
        if n > _NEEDS_WORK_MAX or (structure is not None and structure < _MAJOR_STRUCTURE_FLOOR):
            return Effort.MAJOR_REWORK
        if n > _NEAR_FIX_MAX:
            return Effort.NEEDS_WORK
        return Effort.NEAR_FIX

    @property
    def section_scores(self) -> Dict[Section, Optional[int]]:
        return {
            section: _score([f for f in self.findings if f.section == section])
            for section in Section
        }

    @property
    def finition(self) -> Optional[int]:
        """Overall finition score 0-100. Capped below green when NOT READY so a
        blocked model can never look passing, no matter how clean the slopes are."""
        score = _score(self.findings)
        if score is None:
            return None
        if self.verdict == Verdict.NOT_READY:
            return min(score, 49)
        return score


def evaluate(model_name: str, source_path: str, findings: List[Finding]) -> ModelResult:
    return ModelResult(model_name=model_name, source_path=source_path, findings=findings)
