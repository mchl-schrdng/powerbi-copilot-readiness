"""Structural and topology rules: the hard gates from the scorecard."""

from __future__ import annotations

import re
from typing import List

import networkx as nx

from ..config import Config
from ..model import Model
from .base import Finding, Section, Severity, Status


def _matches_any(name: str, patterns: List[str]) -> bool:
    return any(re.search(p, name, re.IGNORECASE) for p in patterns)


def _rels(model: Model, config: Config):
    """Relationships to evaluate, skipping auto date/time noise when configured."""
    if config.exclude_auto_datetime:
        return model.authored_relationships()
    return model.relationships


def _tables(model: Model, config: Config):
    if config.exclude_auto_datetime:
        return model.authored_tables()
    return model.tables


def resolve_fact_tables(model: Model, config: Config) -> List[str]:
    """Fact tables for this model: explicit declarations plus pattern matches.

    Both are author-declared. Returns the names as they appear in the model.
    """
    names: List[str] = []
    for declared in config.fact_tables_for(model.name):
        table = model.table_by_name(declared)
        if table:
            names.append(table.name)
    for table in _tables(model, config):
        if any(re.search(p, table.name, re.IGNORECASE) for p in config.fact_table_patterns):
            names.append(table.name)
    return list(dict.fromkeys(names))


def check_auto_datetime(model: Model, config: Config) -> List[Finding]:
    """One consolidated finding for Power BI's auto date/time feature."""
    auto_tables, auto_rels = model.auto_artifact_counts()
    if auto_tables == 0 and auto_rels == 0:
        return []
    excluded_note = (
        " These artifacts are excluded from the gates below."
        if config.exclude_auto_datetime
        else " These artifacts are INCLUDED in the gates below (exclude_auto_datetime is off)."
    )
    return [
        Finding(
            rule_id="structure.auto_datetime",
            section=Section.STRUCTURE,
            title="Auto date/time tables",
            obj=model.name,
            status=Status.FAIL,
            severity=Severity.WARN,
            observed=f"{auto_tables} hidden date tables, {auto_rels} auto relationships",
            message=(
                "Auto date/time is enabled. It generates one hidden date table per date "
                "column plus auto relationships (often bidirectional or inactive), which "
                "bloats the schema and confuses Copilot. Disable it and use a single shared "
                "date dimension." + excluded_note
            ),
        )
    ]


def check_many_to_many(model: Model, config: Config) -> List[Finding]:
    findings: List[Finding] = []
    for rel in _rels(model, config):
        bad = rel.is_many_to_many
        findings.append(
            Finding(
                rule_id="structure.many_to_many",
                section=Section.STRUCTURE,
                title="Direct many-to-many relationships",
                obj=f"{rel.from_table} -> {rel.to_table}",
                status=Status.FAIL if bad else Status.PASS,
                severity=Severity.GATE,
                observed=f"{rel.from_cardinality}-to-{rel.to_cardinality}",
                message=(
                    "Direct many-to-many relationship. Resolve it with a physical bridge "
                    "table to enforce a strict one-to-many flow."
                    if bad
                    else "No direct many-to-many cardinality."
                ),
            )
        )
    return findings


def check_bidirectional(model: Model, config: Config) -> List[Finding]:
    findings: List[Finding] = []
    for rel in _rels(model, config):
        bad = rel.is_bidirectional
        findings.append(
            Finding(
                rule_id="structure.bidirectional",
                section=Section.STRUCTURE,
                title="Bidirectional relationships",
                obj=f"{rel.from_table} -> {rel.to_table}",
                status=Status.FAIL if bad else Status.PASS,
                severity=Severity.GATE,
                observed=rel.cross_filtering_behavior,
                message=(
                    "Bidirectional cross-filter. This produces false totals; switch to a "
                    "single direction."
                    if bad
                    else "Single-direction cross-filter."
                ),
            )
        )
    return findings


def check_inactive_exposed(model: Model, config: Config) -> List[Finding]:
    """Inactive relationships are invisible to Copilot; flag exposed ones."""
    findings: List[Finding] = []
    for rel in _rels(model, config):
        if rel.is_active:
            continue
        # Exposed if EITHER endpoint column is visible (the relationship is then
        # discoverable in the field lists even though Copilot will not map it).
        from_table = model.table_by_name(rel.from_table)
        to_table = model.table_by_name(rel.to_table)
        from_col = from_table.column_by_name(rel.from_column) if from_table else None
        to_col = to_table.column_by_name(rel.to_column) if to_table else None
        # An endpoint is exposed only when both its table and its column are
        # visible, consistent with the linter's "visible object" model.
        from_visible = (
            from_table is not None and not from_table.is_hidden
            and from_col is not None and not from_col.is_hidden
        )
        to_visible = (
            to_table is not None and not to_table.is_hidden
            and to_col is not None and not to_col.is_hidden
        )
        exposed = from_visible or to_visible
        findings.append(
            Finding(
                rule_id="structure.inactive_exposed",
                section=Section.STRUCTURE,
                title="Inactive relationships exposed to Copilot",
                obj=f"{rel.from_table}.{rel.from_column} -> {rel.to_table}.{rel.to_column}",
                status=Status.FAIL if exposed else Status.PASS,
                severity=Severity.GATE,
                observed="isActive=false",
                message=(
                    "Inactive (role-playing) relationship on a visible column. Copilot only "
                    "maps active relationships; split the dimension into separate active tables."
                    if exposed
                    else "Inactive relationship is on hidden columns."
                ),
            )
        )
    return findings


def check_join_depth(model: Model, config: Config) -> List[Finding]:
    """Snowflake / join-depth gate. Requires declared fact tables."""
    findings: List[Finding] = []
    known_facts = resolve_fact_tables(model, config)

    if not known_facts:
        declared = config.fact_tables_for(model.name)
        message = (
            "No fact table declared for this model. The topology gate refuses to "
            "guess. Declare fact tables in readiness.yaml (fact_tables, "
            "fact_tables_by_model, or fact_table_patterns) so join depth can be measured."
        )
        if declared:
            message = "Declared fact tables were not found in the model. Check the names: " + ", ".join(declared)
        findings.append(
            Finding(
                rule_id="config.no_fact_table",
                section=Section.CONFIG,
                title="Fact table declaration",
                obj=model.name,
                status=Status.FAIL,
                severity=Severity.GATE,
                observed=", ".join(declared) if declared else None,
                message=message,
            )
        )
        return findings

    graph = model.active_relationship_graph(include_auto=not config.exclude_auto_datetime)
    fact_set = set(known_facts)

    for table in model.visible_tables():
        if table.name in fact_set:
            continue
        hops = None
        for fact in fact_set:
            if table.name in graph and fact in graph and nx.has_path(graph, table.name, fact):
                length = nx.shortest_path_length(graph, table.name, fact)
                hops = length if hops is None else min(hops, length)
        ok = hops is not None and hops <= config.max_hops_to_fact
        findings.append(
            Finding(
                rule_id="structure.join_depth",
                section=Section.STRUCTURE,
                title="Join depth from a field to the fact table",
                obj=table.name,
                status=Status.PASS if ok else Status.FAIL,
                severity=Severity.GATE,
                observed=f"{hops} hop(s) to fact" if hops is not None else "no active path to fact",
                message=(
                    f"Reaches a fact table in {hops} hop(s)."
                    if ok
                    else (
                        "Snowflake or disconnected. A dimension must reach the fact in "
                        f"{config.max_hops_to_fact} hop(s); flatten nested dimensions into one."
                    )
                ),
            )
        )
    return findings


def check_table_count(model: Model, config: Config) -> List[Finding]:
    count = len(model.visible_tables())
    ok = config.min_tables <= count <= config.max_tables
    return [
        Finding(
            rule_id="structure.table_count",
            section=Section.STRUCTURE,
            title="Total number of tables",
            obj=model.name,
            status=Status.PASS if ok else Status.FAIL,
            severity=Severity.WARN,
            observed=str(count),
            message=(
                f"{count} visible tables, within the {config.min_tables} to {config.max_tables} range."
                if ok
                else f"{count} visible tables, outside the {config.min_tables} to {config.max_tables} range. Re-question scope."
            ),
        )
    ]


def check_visible_keys(model: Model, config: Config) -> List[Finding]:
    findings: List[Finding] = []
    for table in _tables(model, config):
        if table.is_hidden:
            continue  # a key in a hidden table is not visible to the user
        for column in table.columns:
            if column.is_hidden:
                continue
            if _matches_any(column.name, config.key_patterns):
                findings.append(
                    Finding(
                        rule_id="structure.visible_keys",
                        section=Section.STRUCTURE,
                        title="Visible surrogate keys or audit fields",
                        obj=f"{table.name}.{column.name}",
                        status=Status.FAIL,
                        severity=Severity.WARN,
                        observed="visible",
                        message="Surrogate key or audit field is visible. Hide it (use OLS if sensitive).",
                    )
                )
    if not findings:
        findings.append(
            Finding(
                rule_id="structure.visible_keys",
                section=Section.STRUCTURE,
                title="Visible surrogate keys or audit fields",
                obj=model.name,
                status=Status.PASS,
                severity=Severity.WARN,
                message="No visible surrogate keys or audit fields detected.",
            )
        )
    return findings


def check_fact_descriptive_columns(model: Model, config: Config) -> List[Finding]:
    """Fact tables should hold foreign keys and measures only."""
    findings: List[Finding] = []
    for fact_name in resolve_fact_tables(model, config):
        table = model.table_by_name(fact_name)
        if not table:
            continue
        descriptive = [
            c.name
            for c in table.columns
            if not c.is_hidden
            and not _matches_any(c.name, config.key_patterns)
            and (c.data_type or "").lower() in {"string", "text"}
        ]
        ok = not descriptive
        findings.append(
            Finding(
                rule_id="structure.fact_descriptive",
                section=Section.STRUCTURE,
                title="Fact table contents",
                obj=table.name,
                status=Status.PASS if ok else Status.FAIL,
                severity=Severity.WARN,
                observed=", ".join(descriptive) if descriptive else "keys and measures only",
                message=(
                    "Fact table holds foreign keys and measures only."
                    if ok
                    else "Descriptive columns on the fact table belong in a dimension: "
                    + ", ".join(descriptive)
                ),
            )
        )
    return findings


RULES = [
    check_auto_datetime,
    check_many_to_many,
    check_bidirectional,
    check_inactive_exposed,
    check_join_depth,
    check_table_count,
    check_visible_keys,
    check_fact_descriptive_columns,
]
