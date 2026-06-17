from copilot_readiness.config import Config
from copilot_readiness.gate import Effort, Verdict, evaluate
from copilot_readiness.rules import run_all_rules
from copilot_readiness.rules.base import Finding, Section, Severity, Status
from copilot_readiness.tmdl_parser import parse_model


def _gate_fails(n, passes=30):
    """n blocking gate fails plus enough passing checks to keep the Structure
    score well above the 'major rework' floor, so the tier reflects the count."""
    findings = [
        Finding(
            rule_id="structure.many_to_many", section=Section.STRUCTURE,
            title="m2m", obj=f"r{i}", status=Status.FAIL, severity=Severity.GATE, message="x",
        )
        for i in range(n)
    ]
    findings += [
        Finding(
            rule_id="structure.bidirectional", section=Section.STRUCTURE,
            title="bidi", obj=f"p{i}", status=Status.PASS, severity=Severity.GATE, message="ok",
        )
        for i in range(passes)
    ]
    return findings


def test_effort_tiers_by_blocker_count():
    near = evaluate("m", "p", _gate_fails(2))
    work = evaluate("m", "p", _gate_fails(5))
    major = evaluate("m", "p", _gate_fails(9))
    assert near.effort == Effort.NEAR_FIX
    assert work.effort == Effort.NEEDS_WORK
    assert major.effort == Effort.MAJOR_REWORK


def test_effort_major_when_structure_score_low():
    # Few blockers but a terrible structure score still means major rework.
    result = evaluate("m", "p", _gate_fails(2, passes=1))  # score ~33, below floor
    assert result.effort == Effort.MAJOR_REWORK


def test_effort_ready_and_incomplete():
    ready = evaluate("m", "p", [])
    assert ready.effort == Effort.NONE
    incomplete = evaluate("m", "p", [
        Finding(rule_id="config.no_fact_table", section=Section.CONFIG, title="fact",
                obj="m", status=Status.FAIL, severity=Severity.GATE, message="declare a fact"),
    ])
    assert incomplete.verdict == Verdict.INCOMPLETE
    assert incomplete.effort == Effort.BLOCKED_ON_CONFIG


def test_undeclared_fact_is_incomplete_not_not_ready(good_star_path):
    """A clean model with no declared fact is INCOMPLETE, not NOT READY."""
    model = parse_model(good_star_path)
    result = evaluate(model.name, good_star_path, run_all_rules(model, Config()))
    assert result.verdict == Verdict.INCOMPLETE
    assert result.is_ready is False
    assert result.real_blocking == []      # no genuine defect
    assert result.config_gaps              # just the missing input


def test_finition_score_capped_when_not_ready(bad_snowflake_path):
    model = parse_model(bad_snowflake_path)
    config = Config(fact_tables_by_model={"bad_snowflake": ["f_sls_trx"]})
    result = evaluate(model.name, bad_snowflake_path, run_all_rules(model, config))
    assert result.verdict == Verdict.NOT_READY
    assert result.finition is not None and result.finition <= 49


def test_good_star_finition_not_capped(good_star_path):
    model = parse_model(good_star_path)
    config = Config(fact_tables_by_model={"good_star": ["Sales"]})
    result = evaluate(model.name, good_star_path, run_all_rules(model, config))
    assert result.verdict == Verdict.READY
    # A clean star scores well above the NOT READY cap.
    assert result.finition is not None and result.finition > 49


def test_good_star_is_ready(good_star_path):
    model = parse_model(good_star_path)
    config = Config(fact_tables_by_model={"good_star": ["Sales"]})
    result = evaluate(model.name, good_star_path, run_all_rules(model, config))
    assert result.is_ready is True
    assert result.blocking == []


def test_bad_snowflake_is_not_ready(bad_snowflake_path):
    model = parse_model(bad_snowflake_path)
    config = Config(fact_tables_by_model={"bad_snowflake": ["f_sls_trx"]})
    result = evaluate(model.name, bad_snowflake_path, run_all_rules(model, config))
    assert result.is_ready is False
    assert len(result.blocking) >= 1


def test_severity_override_can_demote_a_gate(bad_snowflake_path):
    model = parse_model(bad_snowflake_path)
    config = Config(
        fact_tables_by_model={"bad_snowflake": ["f_sls_trx"]},
        severity_overrides={
            "structure.many_to_many": "WARN",
            "structure.bidirectional": "WARN",
            "structure.inactive_exposed": "WARN",
            "structure.join_depth": "WARN",
        },
    )
    result = evaluate(model.name, bad_snowflake_path, run_all_rules(model, config))
    # With every structural gate demoted, nothing blocks anymore.
    assert result.is_ready is True
