"""Regression tests for behaviors hardened against a real PBIP workspace:
auto date/time exclusion, fact-table naming conventions, and parsing the
embedded linguistic-metadata JSON for curated synonyms.
"""

import os
import textwrap

from copilot_readiness.config import Config
from copilot_readiness.rules import run_all_rules
from copilot_readiness.rules.base import Status
from copilot_readiness.tmdl_parser import parse_model


def _write(model_dir, rel, content):
    path = os.path.join(model_dir, "definition", rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(textwrap.dedent(content))


def _build_model(tmp_path, name="Demo"):
    model_dir = os.path.join(str(tmp_path), f"{name}.SemanticModel")
    _write(model_dir, "tables/fact_sales.tmdl", """\
        table fact_sales
        \tcolumn Amount
        \t\tdataType: decimal
        \t\tsummarizeBy: sum
        \t\tisHidden
        """)
    _write(model_dir, "tables/Customer.tmdl", """\
        table Customer
        \tcolumn CustomerKey
        \t\tdataType: int64
        \t\tisHidden
        """)
    # An auto date/time table and an AutoDetected bidirectional relationship.
    _write(model_dir, "tables/LocalDateTable_abc.tmdl", """\
        table LocalDateTable_abc
        \tcolumn Year
        \t\tdataType: int64
        """)
    _write(model_dir, "relationships.tmdl", """\
        relationship Sales_Customer
        \tfromColumn: fact_sales.CustomerKey
        \ttoColumn: Customer.CustomerKey

        relationship AutoDetected_xyz
        \tcrossFilteringBehavior: bothDirections
        \tfromColumn: fact_sales.OrderDate
        \ttoColumn: LocalDateTable_abc.Date
        """)
    return model_dir


def test_auto_datetime_excluded_and_consolidated(tmp_path):
    model = parse_model(_build_model(tmp_path))
    findings = run_all_rules(model, Config(fact_table_patterns=["^fact_"]))

    # The AutoDetected bidirectional relationship must NOT raise a bidi gate.
    bidi_fails = [f for f in findings if f.rule_id == "structure.bidirectional" and f.status == Status.FAIL]
    assert bidi_fails == []

    # Instead, a single consolidated auto date/time warning is emitted.
    auto = [f for f in findings if f.rule_id == "structure.auto_datetime"]
    assert auto and auto[0].status == Status.FAIL


def test_fact_table_pattern_resolves_without_explicit_declaration(tmp_path):
    model = parse_model(_build_model(tmp_path))
    findings = run_all_rules(model, Config(fact_table_patterns=["^fact_"]))
    # With a fact resolved by convention, there is no "no fact table" config error.
    assert not any(f.rule_id == "config.no_fact_table" for f in findings)
    # And Customer (one hop from the fact) passes the join-depth gate.
    depth = [f for f in findings if f.rule_id == "structure.join_depth" and f.obj == "Customer"]
    assert depth and depth[0].status == Status.PASS


def test_no_fact_without_declaration_or_pattern(tmp_path):
    model = parse_model(_build_model(tmp_path))
    findings = run_all_rules(model, Config())  # no facts at all
    assert any(f.rule_id == "config.no_fact_table" and f.is_blocking for f in findings)


def test_linguistic_synonyms_authored_vs_generated(tmp_path):
    model_dir = _build_model(tmp_path, name="WithCulture")
    _write(model_dir, "cultures/en-US.tmdl", """\
        cultureInfo en-US

        \tlinguisticMetadata =
        \t\t\t{
        \t\t\t  "Version": "4.1.0",
        \t\t\t  "Entities": {
        \t\t\t    "Customer": {
        \t\t\t      "Terms": [
        \t\t\t        { "customer": { "State": "Generated", "Weight": 0.99 } },
        \t\t\t        { "client": { "State": "Suggested", "Source": { "Agent": "Thesaurus" } } },
        \t\t\t        { "account": { "State": "Authored" } }
        \t\t\t      ]
        \t\t\t    }
        \t\t\t  }
        \t\t\t}
        """)
    model = parse_model(model_dir)
    assert model.has_culture_file is True
    authored = [s for s in model.synonyms if not s.generated]
    # Only "account" is human-authored; "customer" and "client" are not.
    assert [s.term for s in authored] == ["account"]
