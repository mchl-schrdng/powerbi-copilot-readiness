"""Calculation and AI-artifact rules.

Some scorecard lines (Verified Answers, AI Instructions, the Simplify Data
Schema selection) are not reliably present in TMDL. Rather than pass or fail
them silently, these surface as MANUAL checklist items flagged not-auto-verified.
"""

from __future__ import annotations

from typing import List

from ..config import Config
from ..model import Model
from .base import Finding, Section, Severity, Status


def check_calc_groups(model: Model, config: Config) -> List[Finding]:
    findings: List[Finding] = []
    calc_groups = [t for t in model.tables if t.is_calc_group]
    if not calc_groups:
        return findings
    for table in calc_groups:
        findings.append(
            Finding(
                rule_id="calculations.calc_group_exposed",
                section=Section.CALCULATIONS,
                title="Calculation groups exposed without an equivalent dedicated measure",
                obj=table.name,
                status=Status.MANUAL,
                severity=Severity.WARN,
                auto_verified=False,
                message=(
                    "Calculation group present. It intercepts context via SELECTEDMEASURE(), "
                    "so Copilot cannot tie a metric to its real execution. Confirm a dedicated "
                    "explicit measure exists for each priority combination."
                ),
            )
        )
    return findings


def check_time_intelligence(model: Model, config: Config) -> List[Finding]:
    return [
        Finding(
            rule_id="calculations.time_intelligence",
            section=Section.CALCULATIONS,
            title="Time calcs left to generate on the fly",
            obj=model.name,
            status=Status.MANUAL,
            severity=Severity.WARN,
            auto_verified=False,
            message=(
                "Whether YoY/MoM/rolling are pre-computed as measures cannot be proven "
                "statically. Confirm they exist as explicit measures rather than being left "
                "for Copilot to generate."
            ),
        )
    ]


def check_ai_artifacts(model: Model, config: Config) -> List[Finding]:
    """Verified Answers, AI Instructions, Simplify Data Schema, Prepped flag."""
    items = [
        (
            "calculations.verified_answers",
            "Executive KPI without a Verified Answer",
            "Confirm each executive KPI has a Verified Answer with 5 to 7 trigger phrases.",
        ),
        (
            "config.ai_instructions",
            "AI Instructions",
            "Confirm AI Instructions are authored (up to 10,000 characters) and written like prompts.",
        ),
        (
            "config.ai_data_schema",
            "Simplify Data Schema (the AI data schema)",
            "Confirm the AI data schema selection restricts what Copilot sees, plus OLS for sensitive metadata.",
        ),
        (
            "config.prepped_for_ai",
            "Mark as Prepped for AI",
            "Confirm the model is marked Prepped for AI once every gate is green.",
        ),
    ]
    findings: List[Finding] = []
    for rule_id, title, message in items:
        findings.append(
            Finding(
                rule_id=rule_id,
                section=Section.CONFIG,
                title=title,
                obj=model.name,
                status=Status.MANUAL,
                severity=Severity.WARN,
                auto_verified=False,
                message=message,
            )
        )
    return findings


RULES = [
    check_calc_groups,
    check_time_intelligence,
    check_ai_artifacts,
]
