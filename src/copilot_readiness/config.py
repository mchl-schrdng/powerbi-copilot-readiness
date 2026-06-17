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

    key_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_KEY_PATTERNS))
    bad_name_prefixes: List[str] = field(default_factory=lambda: list(DEFAULT_BAD_NAME_PREFIXES))
    non_summable_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_NON_SUMMABLE_PATTERNS))
    geo_patterns: List[str] = field(default_factory=lambda: list(DEFAULT_GEO_PATTERNS))

    # Map rule_id -> "GATE" | "WARN" | "OFF" to override the built-in severity.
    severity_overrides: Dict[str, str] = field(default_factory=dict)

    def fact_tables_for(self, model_name: str) -> List[str]:
        specific = self.fact_tables_by_model.get(model_name, [])
        return list(dict.fromkeys(list(specific) + list(self.fact_tables)))


def load_config(path: Optional[str]) -> Config:
    if not path or not os.path.isfile(path):
        return Config()

    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    config = Config()
    thresholds = data.get("thresholds", {}) or {}
    config.model_glob = data.get("model_glob", config.model_glob)
    config.fact_tables = list(data.get("fact_tables", []) or [])
    config.fact_tables_by_model = {
        str(k): list(v or []) for k, v in (data.get("fact_tables_by_model", {}) or {}).items()
    }
    config.fact_table_patterns = list(data.get("fact_table_patterns", []) or [])

    config.exclude_auto_datetime = bool(
        data.get("exclude_auto_datetime", config.exclude_auto_datetime)
    )
    config.max_hops_to_fact = thresholds.get("max_hops_to_fact", config.max_hops_to_fact)
    config.min_tables = thresholds.get("min_tables", config.min_tables)
    config.max_tables = thresholds.get("max_tables", config.max_tables)
    config.description_char_budget = thresholds.get(
        "description_char_budget", config.description_char_budget
    )

    patterns = data.get("patterns", {}) or {}
    config.key_patterns = list(patterns.get("key", config.key_patterns))
    config.bad_name_prefixes = list(patterns.get("bad_name_prefixes", config.bad_name_prefixes))
    config.non_summable_patterns = list(patterns.get("non_summable", config.non_summable_patterns))
    config.geo_patterns = list(patterns.get("geo", config.geo_patterns))

    config.severity_overrides = {
        str(k): str(v).upper() for k, v in (data.get("severity_overrides", {}) or {}).items()
    }
    return config
