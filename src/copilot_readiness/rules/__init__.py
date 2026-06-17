"""Rule registry. Collects every rule callable across the rule modules."""

from __future__ import annotations

from typing import Callable, List

from ..config import Config
from ..model import Model
from . import calculations, metadata, structure
from .base import Finding, Section, Severity, Status

Rule = Callable[[Model, Config], List[Finding]]

ALL_RULES: List[Rule] = [*structure.RULES, *metadata.RULES, *calculations.RULES]


def run_all_rules(model: Model, config: Config) -> List[Finding]:
    """Run every rule, then apply severity overrides from config."""
    findings: List[Finding] = []
    for rule in ALL_RULES:
        findings.extend(rule(model, config))

    for finding in findings:
        override = config.severity_overrides.get(finding.rule_id)
        if override in {s.value for s in Severity}:
            finding.severity = Severity(override)
    return [f for f in findings if f.severity != Severity.OFF]


__all__ = [
    "ALL_RULES",
    "run_all_rules",
    "Finding",
    "Section",
    "Severity",
    "Status",
]
