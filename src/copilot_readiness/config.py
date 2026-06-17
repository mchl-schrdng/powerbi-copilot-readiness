"""Configuration loading for the readiness linter.

Defaults match the scorecard in the article so the linter is useful with an
empty or absent ``readiness.yaml``. The config lets a repo declare its fact
tables (required for the topology gate to be trustworthy), tune thresholds, and
promote or demote individual rule severities.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml

DEFAULT_KEY_PATTERNS = [
    r".*key$",
    r".*sk$",
    r".*_id$",
    r".*guid$",
    r"^id$",
    r".*createddate$",
    r".*modifieddate$",
    r".*audit.*",
    r".*loadtimestamp$",
]

DEFAULT_BAD_NAME_PREFIXES = [
    r"^f_",
    r"^d_",
    r"^dim",
    r"^fact",
    r"^stg_",
    r"^tmp_",
]

# Numeric column names that should almost never be summed.
DEFAULT_NON_SUMMABLE_PATTERNS = [
    r".*id$",
    r".*key$",
    r"^year$",
    r".*year$",
    r".*price$",
    r".*rate$",
    r".*ratio$",
    r".*percent.*",
    r".*age$",
]

# Disconnected tables matching these names are disconnected by design (utility
# tables), so the join-depth gate skips them instead of flagging a missing path.
DEFAULT_UTILITY_TABLE_PATTERNS = [
    r"parameter",      # what-if parameter tables
    r"^_",             # leading-underscore technical tables
    r"\brls\b",        # row-level-security helper tables
    r"securit", r"sécurit",
    r"^tech", r"^tec_",
    r"^measures?$",    # measure-holder tables, by name
]

DEFAULT_GEO_PATTERNS = [
    r".*country.*",
    r".*city.*",
    r".*state.*",
    r".*province.*",
    r".*region.*",
    r".*postal.*",
    r".*zip.*",
    r".*latitude.*",
    r".*longitude.*",
]


@dataclass
class Config:
    model_glob: str = "**/*.SemanticModel"
    fact_tables: List[str] = field(default_factory=list)
    fact_tables_by_model: Dict[str, List[str]] = field(default_factory=dict)
    # Opt-in naming convention: tables whose name matches any of these regexes are
    # treated as fact tables. This is author-declared, not the tool guessing.
    fact_table_patterns: List[str] = field(default_factory=list)

    exclude_auto_datetime: bool = True
    max_hops_to_fact: int = 1
    min_tables: int = 5
    max_tables: int = 30
    description_char_budget: int = 200

    utility_table_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_UTILITY_TABLE_PATTERNS))
    key_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_KEY_PATTERNS))
    bad_name_prefixes: List[str] = field(default_factory=lambda: list(DEFAULT_BAD_NAME_PREFIXES))
    non_summable_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_NON_SUMMABLE_PATTERNS))
    geo_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_GEO_PATTERNS))

    # Map rule_id -> "GATE" | "WARN" | "OFF" to override the built-in severity.
    severity_overrides: Dict[str, str] = field(default_factory=dict)

    def fact_tables_for(self, model_name: str) -> List[str]:
        specific = self.fact_tables_by_model.get(model_name, [])
        return list(dict.fromkeys(list(specific) + list(self.fact_tables)))


_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}


def _as_bool(value, default: bool) -> bool:
    """Parse a YAML bool robustly. A quoted "false" is False, not truthy."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
    if value is None:
        return default
    return bool(value)


def _as_str_list(value) -> List[str]:
    """Coerce a scalar or list into a list of strings.

    Guards against `key: SomeName` (a bare string) being treated as an iterable
    of characters, which would explode into ['S', 'o', 'm', 'e', ...]."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def load_config(path: Optional[str]) -> Config:
    if not path or not os.path.isfile(path):
        return Config()

    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    config = Config()
    thresholds = data.get("thresholds", {}) or {}
    config.model_glob = str(data.get("model_glob", config.model_glob))
    config.fact_tables = _as_str_list(data.get("fact_tables"))
    config.fact_tables_by_model = {
        str(k): _as_str_list(v) for k, v in (data.get("fact_tables_by_model", {}) or {}).items()
    }
    config.fact_table_patterns = _as_str_list(data.get("fact_table_patterns"))

    config.exclude_auto_datetime = _as_bool(
        data.get("exclude_auto_datetime"), config.exclude_auto_datetime
    )
    config.max_hops_to_fact = int(thresholds.get("max_hops_to_fact", config.max_hops_to_fact))
    config.min_tables = int(thresholds.get("min_tables", config.min_tables))
    config.max_tables = int(thresholds.get("max_tables", config.max_tables))
    config.description_char_budget = int(
        thresholds.get("description_char_budget", config.description_char_budget)
    )

    patterns = data.get("patterns", {}) or {}
    config.utility_table_patterns = _as_str_list(patterns.get("utility_tables")) or config.utility_table_patterns
    config.key_patterns = _as_str_list(patterns.get("key")) or config.key_patterns
    config.bad_name_prefixes = _as_str_list(patterns.get("bad_name_prefixes")) or config.bad_name_prefixes
    config.non_summable_patterns = _as_str_list(patterns.get("non_summable")) or config.non_summable_patterns
    config.geo_patterns = _as_str_list(patterns.get("geo")) or config.geo_patterns

    config.severity_overrides = {
        str(k): str(v).upper() for k, v in (data.get("severity_overrides", {}) or {}).items()
    }
    return config
