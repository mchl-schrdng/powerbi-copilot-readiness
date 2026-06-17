"""Join-depth gate: snowflakes block, disconnected utility tables are skipped,
real orphan tables warn (not block)."""

import os
import textwrap

from copilot_readiness.config import Config
from copilot_readiness.rules import run_all_rules
from copilot_readiness.rules.base import Severity, Status
from copilot_readiness.tmdl_parser import parse_model


def _write(model_dir, rel, content):
    path = os.path.join(model_dir, "definition", rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(textwrap.dedent(content))


def _build(tmp_path):
    d = os.path.join(str(tmp_path), "Demo.SemanticModel")
    _write(d, "tables/fact_sales.tmdl", "table fact_sales\n\tcolumn XKey\n\t\tdataType: int64\n\t\tisHidden\n")
    _write(d, "tables/DimX.tmdl", "table DimX\n\tcolumn K\n\t\tdataType: int64\n\tcolumn Name\n\t\tdataType: string\n")
    _write(d, "tables/DimSub.tmdl", "table DimSub\n\tcolumn XKey\n\t\tdataType: int64\n\tcolumn Label\n\t\tdataType: string\n")
    # Measure holder: a measure plus a single hidden column, disconnected.
    _write(d, "tables/KPIs.tmdl", "table KPIs\n\tcolumn Dummy\n\t\tdataType: int64\n\t\tisHidden\n\tmeasure 'Total' = SUM(fact_sales[XKey])\n")
    # Utility table by name, disconnected.
    _write(d, "tables/_Helper.tmdl", "table _Helper\n\tcolumn V\n\t\tdataType: int64\n")
    # A genuine orphan dimension, disconnected.
    _write(d, "tables/OrphanDim.tmdl", "table OrphanDim\n\tcolumn Code\n\t\tdataType: string\n\tcolumn Label\n\t\tdataType: string\n")
    _write(d, "relationships.tmdl", """\
        relationship fact_DimX
        \tfromColumn: fact_sales.XKey
        \ttoColumn: DimX.K

        relationship sub_DimX
        \tfromColumn: DimSub.XKey
        \ttoColumn: DimX.K
        """)
    return d


def _by_rule(findings, rule_id):
    return [f for f in findings if f.rule_id == rule_id]


def test_join_depth_buckets(tmp_path):
    model = parse_model(_build(tmp_path))
    findings = run_all_rules(model, Config(fact_table_patterns=["^fact_"]))

    depth = {f.obj: f for f in _by_rule(findings, "structure.join_depth")}
    disconnected = {f.obj for f in _by_rule(findings, "structure.disconnected_table")}

    # DimX is one hop: passing join-depth gate.
    assert depth["DimX"].status == Status.PASS
    # DimSub is two hops via DimX: a snowflake, blocking.
    assert depth["DimSub"].status == Status.FAIL
    assert depth["DimSub"].severity == Severity.GATE

    # Measure holder and the _-prefixed utility table are skipped entirely.
    assert "KPIs" not in depth and "KPIs" not in disconnected
    assert "_Helper" not in depth and "_Helper" not in disconnected

    # The genuine orphan dimension is a non-blocking warning, not a gate.
    assert "OrphanDim" in disconnected
    orphan = _by_rule(findings, "structure.disconnected_table")[0]
    assert orphan.severity == Severity.WARN
    assert not orphan.is_blocking


def test_snowflake_still_blocks_in_fixture(bad_snowflake_path, fixtures_config):
    from copilot_readiness.config import load_config
    model = parse_model(bad_snowflake_path)
    findings = run_all_rules(model, load_config(fixtures_config))
    depth = _by_rule(findings, "structure.join_depth")
    failed = {f.obj for f in depth if f.status == Status.FAIL}
    assert "DimSubCategory" in failed  # 2 hops
    assert "DimCategory" in failed     # 3 hops
