"""Regression tests for the issues raised in code review."""

import os
import textwrap

from copilot_readiness.cli import main
from copilot_readiness.config import Config
from copilot_readiness.rules import run_all_rules
from copilot_readiness.rules.base import Status
from copilot_readiness.tmdl_parser import parse_model


def _write(model_dir, rel, content):
    path = os.path.join(model_dir, "definition", rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(textwrap.dedent(content))


def _findings(model, config, rule_id):
    return [f for f in run_all_rules(model, config) if f.rule_id == rule_id]


def test_autodetected_between_real_tables_is_evaluated(tmp_path):
    """An AutoDetected_* relationship between two real tables is NOT auto-date
    noise and must be gated (regression: it used to be silently excluded)."""
    model_dir = os.path.join(str(tmp_path), "Demo.SemanticModel")
    _write(model_dir, "tables/fact_sales.tmdl", "table fact_sales\n\tcolumn K\n\t\tdataType: int64\n")
    _write(model_dir, "tables/ref_a.tmdl", "table ref_a\n\tcolumn K\n\t\tdataType: int64\n")
    _write(model_dir, "tables/ref_b.tmdl", "table ref_b\n\tcolumn K\n\t\tdataType: int64\n")
    _write(model_dir, "relationships.tmdl", """\
        relationship AutoDetected_real
        \tcrossFilteringBehavior: bothDirections
        \tfromColumn: ref_a.K
        \ttoColumn: ref_b.K
        """)
    model = parse_model(model_dir)
    bidi = _findings(model, Config(fact_table_patterns=["^fact_"]), "structure.bidirectional")
    assert any(f.status == Status.FAIL for f in bidi)


def test_autodetected_to_local_date_table_still_excluded(tmp_path):
    model_dir = os.path.join(str(tmp_path), "Demo.SemanticModel")
    _write(model_dir, "tables/fact_sales.tmdl", "table fact_sales\n\tcolumn OrderDate\n\t\tdataType: dateTime\n")
    _write(model_dir, "tables/LocalDateTable_x.tmdl", "table LocalDateTable_x\n\tcolumn Date\n\t\tdataType: dateTime\n")
    _write(model_dir, "relationships.tmdl", """\
        relationship AutoDetected_date
        \tcrossFilteringBehavior: bothDirections
        \tfromColumn: fact_sales.OrderDate
        \ttoColumn: LocalDateTable_x.Date
        """)
    model = parse_model(model_dir)
    bidi = _findings(model, Config(fact_table_patterns=["^fact_"]), "structure.bidirectional")
    assert not any(f.status == Status.FAIL for f in bidi)  # excluded as auto date/time


def test_patterns_are_case_insensitive(tmp_path):
    model_dir = os.path.join(str(tmp_path), "Demo.SemanticModel")
    _write(model_dir, "tables/fact_sales.tmdl", "table fact_sales\n\tcolumn K\n\t\tdataType: int64\n")
    model = parse_model(model_dir)
    # An uppercase pattern must still match a lowercase object name.
    config = Config(fact_table_patterns=["^fact_"], bad_name_prefixes=["^Fact"])
    naming = _findings(model, config, "metadata.naming")
    assert any(f.status == Status.FAIL and f.obj == "fact_sales" for f in naming)


def test_inactive_exposed_checks_either_endpoint(tmp_path):
    """fromColumn hidden but toColumn visible must still flag exposure."""
    model_dir = os.path.join(str(tmp_path), "Demo.SemanticModel")
    _write(model_dir, "tables/fact_sales.tmdl", """\
        table fact_sales
        \tcolumn ShipDateKey
        \t\tdataType: int64
        \t\tisHidden
        """)
    _write(model_dir, "tables/DimDate.tmdl", "table DimDate\n\tcolumn DateKey\n\t\tdataType: int64\n")
    _write(model_dir, "relationships.tmdl", """\
        relationship ship
        \tisActive: false
        \tfromColumn: fact_sales.ShipDateKey
        \ttoColumn: DimDate.DateKey
        """)
    model = parse_model(model_dir)
    inactive = _findings(model, Config(fact_table_patterns=["^fact_"]), "structure.inactive_exposed")
    assert any(f.status == Status.FAIL for f in inactive)


def test_inactive_exposed_ignores_hidden_tables(tmp_path):
    """A hidden endpoint table is not exposed, even if its column is not hidden."""
    model_dir = os.path.join(str(tmp_path), "Demo.SemanticModel")
    _write(model_dir, "tables/fact_sales.tmdl", """\
        table fact_sales
        \tcolumn ShipDateKey
        \t\tdataType: int64
        \t\tisHidden
        """)
    _write(model_dir, "tables/DimHidden.tmdl", """\
        table DimHidden
        \tisHidden
        \tcolumn DateKey
        \t\tdataType: int64
        """)
    _write(model_dir, "relationships.tmdl", """\
        relationship ship
        \tisActive: false
        \tfromColumn: fact_sales.ShipDateKey
        \ttoColumn: DimHidden.DateKey
        """)
    model = parse_model(model_dir)
    inactive = _findings(model, Config(fact_table_patterns=["^fact_"]), "structure.inactive_exposed")
    # Both endpoints are effectively hidden (fact column hidden, dim table hidden).
    assert inactive and all(f.status == Status.PASS for f in inactive)


def test_allow_incomplete_flag_changes_exit_code(good_star_path):
    # No fact declared -> INCOMPLETE. Default exits 1, --allow-incomplete exits 0.
    assert main(["lint", good_star_path]) == 1
    assert main(["lint", good_star_path, "--allow-incomplete"]) == 0


def test_hidden_table_is_not_evaluated_by_quality_rules(tmp_path):
    """A column in a hidden table is not surfaced, so visible-object rules skip it."""
    model_dir = os.path.join(str(tmp_path), "Demo.SemanticModel")
    _write(model_dir, "tables/fact_sales.tmdl", "table fact_sales\n\tcolumn Amount\n\t\tdataType: decimal\n\t\tsummarizeBy: sum\n\t\tisHidden\n")
    # Hidden staging table whose columns are NOT individually hidden.
    _write(model_dir, "tables/f_staging.tmdl", """\
        table f_staging
        \tisHidden
        \tcolumn CustomerKey
        \t\tdataType: int64
        \t\tsummarizeBy: sum
        """)
    model = parse_model(model_dir)
    config = Config(fact_table_patterns=["^fact_"])
    keys = _findings(model, config, "structure.visible_keys")
    non_summable = _findings(model, config, "metadata.non_summable")
    naming = _findings(model, config, "metadata.naming")
    # CustomerKey lives in a hidden table -> not flagged by any visible-object rule.
    assert not any(f.status == Status.FAIL and "CustomerKey" in f.obj for f in keys)
    assert not any("f_staging" in f.obj for f in non_summable)
    assert not any(f.status == Status.FAIL and f.obj == "f_staging" for f in naming)


def test_config_bool_and_list_coercion(tmp_path):
    from copilot_readiness.config import load_config
    cfg_path = os.path.join(str(tmp_path), "readiness.yaml")
    with open(cfg_path, "w", encoding="utf-8") as handle:
        handle.write(
            'exclude_auto_datetime: "false"\n'
            "fact_tables_by_model:\n"
            "  Sales: FactSales\n"      # bare string, not a list
            "fact_tables: FactGlobal\n"
        )
    config = load_config(cfg_path)
    # Quoted "false" must parse as False, not truthy.
    assert config.exclude_auto_datetime is False
    # A bare string value must become a one-element list, not a list of chars.
    assert config.fact_tables_by_model["Sales"] == ["FactSales"]
    assert config.fact_tables == ["FactGlobal"]
