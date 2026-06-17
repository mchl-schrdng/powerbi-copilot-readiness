"""Metadata rules: naming, documentation, aggregation, categories, synonyms."""

from __future__ import annotations

import re
from collections import Counter
from typing import List

from ..config import Config
from ..model import Model
from .base import Finding, Section, Severity, Status


def _matches_any(name: str, patterns: List[str]) -> bool:
    return any(re.search(p, name, re.IGNORECASE) for p in patterns)


def _tables(model: Model, config: Config):
    if config.exclude_auto_datetime:
        return model.authored_tables()
    return model.tables


def check_naming(model: Model, config: Config) -> List[Finding]:
    findings: List[Finding] = []
    for table in _tables(model, config):
        names = [(table.name, "table")] + [(c.name, "column") for c in table.columns]
        for name, kind in names:
            if _matches_any(name, config.bad_name_prefixes):
                findings.append(
                    Finding(
                        rule_id="metadata.naming",
                        section=Section.METADATA,
                        title="Abbreviations or technical prefixes in names",
                        obj=name if kind == "table" else f"{table.name}.{name}",
                        status=Status.FAIL,
                        severity=Severity.WARN,
                        observed=name,
                        message="Technical prefix or abbreviation. Use a spelled-out business name.",
                    )
                )
    if not findings:
        findings.append(
            Finding(
                rule_id="metadata.naming",
                section=Section.METADATA,
                title="Abbreviations or technical prefixes in names",
                obj=model.name,
                status=Status.PASS,
                severity=Severity.WARN,
                message="No technical prefixes detected in table or column names.",
            )
        )
    return findings


def check_documentation(model: Model, config: Config) -> List[Finding]:
    """Coverage of descriptions and the first-200-character budget."""
    findings: List[Finding] = []
    missing: List[str] = []
    over_budget: List[str] = []

    def inspect(obj_name: str, description) -> None:
        if not description or not description.strip():
            missing.append(obj_name)
        elif len(description) > config.description_char_budget:
            over_budget.append(obj_name)

    for table in model.visible_tables():
        inspect(table.name, table.description)
        for column in table.columns:
            if column.is_hidden:
                continue
            inspect(f"{table.name}.{column.name}", column.description)
        for measure in table.measures:
            if measure.is_hidden:
                continue
            inspect(f"{table.name}.{measure.name}", measure.description)

    if missing:
        findings.append(
            Finding(
                rule_id="metadata.documentation_coverage",
                section=Section.METADATA,
                title="Documentation coverage",
                obj=model.name,
                status=Status.FAIL,
                severity=Severity.WARN,
                observed=f"{len(missing)} objects undocumented",
                message="Undocumented exposed objects: " + ", ".join(missing[:15])
                + (" ..." if len(missing) > 15 else ""),
            )
        )
    else:
        findings.append(
            Finding(
                rule_id="metadata.documentation_coverage",
                section=Section.METADATA,
                title="Documentation coverage",
                obj=model.name,
                status=Status.PASS,
                severity=Severity.WARN,
                message="All exposed objects have descriptions.",
            )
        )

    if over_budget:
        findings.append(
            Finding(
                rule_id="metadata.description_budget",
                section=Section.METADATA,
                title="Description first-200-character budget",
                obj=model.name,
                status=Status.FAIL,
                severity=Severity.WARN,
                observed=f"{len(over_budget)} descriptions over {config.description_char_budget} chars",
                message=(
                    f"Copilot reads only the first {config.description_char_budget} characters. "
                    "Front-load business intent: " + ", ".join(over_budget[:15])
                ),
            )
        )
    return findings


def check_non_summable(model: Model, config: Config) -> List[Finding]:
    findings: List[Finding] = []
    for table in _tables(model, config):
        for column in table.columns:
            if column.is_hidden or not column.is_numeric:
                continue
            if not _matches_any(column.name, config.non_summable_patterns):
                continue
            summarize = (column.summarize_by or "").lower()
            ok = summarize == "none"
            findings.append(
                Finding(
                    rule_id="metadata.non_summable",
                    section=Section.METADATA,
                    title="Non-summable numeric fields set to Don't Summarize",
                    obj=f"{table.name}.{column.name}",
                    status=Status.PASS if ok else Status.FAIL,
                    severity=Severity.WARN,
                    observed=f"summarizeBy={column.summarize_by or 'default'}",
                    message=(
                        "Set to Don't Summarize."
                        if ok
                        else "Numeric identifier or rate is summed by default. Set summarizeBy to none."
                    ),
                )
            )
    return findings


def check_geo_category(model: Model, config: Config) -> List[Finding]:
    findings: List[Finding] = []
    for table in _tables(model, config):
        for column in table.columns:
            if column.is_hidden:
                continue
            if not _matches_any(column.name, config.geo_patterns):
                continue
            ok = bool(column.data_category)
            findings.append(
                Finding(
                    rule_id="metadata.geo_category",
                    section=Section.METADATA,
                    title="Geographic columns with a Data Category",
                    obj=f"{table.name}.{column.name}",
                    status=Status.PASS if ok else Status.FAIL,
                    severity=Severity.WARN,
                    observed=f"dataCategory={column.data_category or 'none'}",
                    message=(
                        f"Tagged as {column.data_category}."
                        if ok
                        else "Geographic column without a Data Category. Tag it so Copilot can map it."
                    ),
                )
            )
    return findings


def check_synonyms(model: Model, config: Config) -> List[Finding]:
    findings: List[Finding] = []
    if not model.has_culture_file:
        findings.append(
            Finding(
                rule_id="metadata.synonyms",
                section=Section.METADATA,
                title="Synonyms per key field",
                obj=model.name,
                status=Status.MANUAL,
                severity=Severity.WARN,
                auto_verified=False,
                message=(
                    "No linguistic (culture) schema found, so synonym coverage cannot be "
                    "auto-verified. Confirm 1 to 2 synonyms per key field, with no collisions."
                ),
            )
        )
        return findings

    # Only curated synonyms matter. Power BI auto-generates a term per object
    # (the field name and its variants); those are not authored vocabulary, so
    # counting collisions among them is meaningless.
    curated = [s for s in model.synonyms if not s.generated]
    if not curated:
        findings.append(
            Finding(
                rule_id="metadata.synonyms",
                section=Section.METADATA,
                title="Synonyms per key field",
                obj=model.name,
                status=Status.MANUAL,
                severity=Severity.WARN,
                auto_verified=False,
                observed=f"{len(model.synonyms)} terms, all auto-generated",
                message=(
                    "The linguistic schema contains only auto-generated terms, no curated "
                    "synonyms. Add 1 to 2 business synonyms per key field so Copilot maps "
                    "everyday wording to your columns."
                ),
            )
        )
        return findings

    # Collision check on curated synonyms only: one term pointing at >1 object.
    term_targets = Counter(s.term.lower() for s in curated)
    collisions = [term for term, count in term_targets.items() if count > 1]
    findings.append(
        Finding(
            rule_id="metadata.synonyms",
            section=Section.METADATA,
            title="Synonyms per key field",
            obj=model.name,
            status=Status.FAIL if collisions else Status.PASS,
            severity=Severity.WARN,
            observed=f"{len(curated)} curated synonyms, {len(collisions)} collisions",
            message=(
                "Curated synonym collisions (one term, several objects): " + ", ".join(collisions[:10])
                if collisions
                else f"{len(curated)} curated synonyms present with no detected collisions."
            ),
        )
    )
    return findings


RULES = [
    check_naming,
    check_documentation,
    check_non_summable,
    check_geo_category,
    check_synonyms,
]
