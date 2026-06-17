"""In-memory model of a Power BI semantic model.

These dataclasses capture only the metadata the readiness rules need, not the
full Tabular Object Model. The TMDL parser populates them; the rules read them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import networkx as nx


@dataclass
class Column:
    name: str
    table: str
    data_type: Optional[str] = None
    summarize_by: Optional[str] = None
    is_hidden: bool = False
    data_category: Optional[str] = None
    description: Optional[str] = None
    display_folder: Optional[str] = None

    @property
    def is_numeric(self) -> bool:
        if not self.data_type:
            return False
        return self.data_type.lower() in {"int64", "double", "decimal"}


@dataclass
class Measure:
    name: str
    table: str
    expression: Optional[str] = None
    description: Optional[str] = None
    is_hidden: bool = False


# Prefixes Power BI uses for auto-generated artifacts (the auto date/time feature).
_AUTO_TABLE_PREFIXES = ("LocalDateTable_", "DateTableTemplate_")


def _is_auto_table_name(name: str) -> bool:
    return name.startswith(_AUTO_TABLE_PREFIXES)


@dataclass
class Relationship:
    name: str
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    from_cardinality: str = "many"
    to_cardinality: str = "one"
    cross_filtering_behavior: str = "singleDirection"
    is_active: bool = True

    @property
    def is_many_to_many(self) -> bool:
        return self.from_cardinality.lower() == "many" and self.to_cardinality.lower() == "many"

    @property
    def is_bidirectional(self) -> bool:
        return self.cross_filtering_behavior.lower() == "bothdirections"

    @property
    def is_auto_generated(self) -> bool:
        """True only for auto date/time relationships (an endpoint is a hidden
        LocalDateTable_*/DateTableTemplate_*).

        Note: the ``AutoDetected_*`` name prefix is a DIFFERENT feature
        (relationship auto-detection between real tables) and must NOT be
        excluded; those are real relationships the gates should evaluate.
        """
        return _is_auto_table_name(self.from_table) or _is_auto_table_name(self.to_table)


@dataclass
class Table:
    name: str
    columns: List[Column] = field(default_factory=list)
    measures: List[Measure] = field(default_factory=list)
    is_hidden: bool = False
    description: Optional[str] = None
    is_calc_group: bool = False

    @property
    def is_auto_generated(self) -> bool:
        """True for Power BI auto date/time tables (LocalDateTable_*, etc.)."""
        return _is_auto_table_name(self.name)

    def column_by_name(self, name: str) -> Optional[Column]:
        for column in self.columns:
            if column.name.lower() == name.lower():
                return column
        return None


@dataclass
class Synonym:
    """A linguistic synonym mapping a model object to a business term."""

    target_object: str
    term: str
    generated: bool = False   # True for Power BI auto-generated terms, not curated


@dataclass
class Model:
    name: str
    source_path: str
    tables: List[Table] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    synonyms: List[Synonym] = field(default_factory=list)
    has_culture_file: bool = False

    def table_by_name(self, name: str) -> Optional[Table]:
        for table in self.tables:
            if table.name.lower() == name.lower():
                return table
        return None

    def visible_tables(self) -> List[Table]:
        return [t for t in self.tables if not t.is_hidden and not t.is_calc_group]

    def authored_tables(self) -> List[Table]:
        """Tables excluding Power BI auto date/time artifacts."""
        return [t for t in self.tables if not t.is_auto_generated]

    def authored_relationships(self) -> List[Relationship]:
        return [r for r in self.relationships if not r.is_auto_generated]

    def auto_artifact_counts(self) -> "tuple[int, int]":
        """(auto tables, auto relationships) from the auto date/time feature."""
        tables = sum(1 for t in self.tables if t.is_auto_generated)
        rels = sum(1 for r in self.relationships if r.is_auto_generated)
        return tables, rels

    def active_relationship_graph(self, include_auto: bool = False) -> "nx.Graph":
        """Undirected graph of active relationships, for hop-counting.

        Auto date/time artifacts are excluded unless ``include_auto`` is set."""
        tables = self.tables if include_auto else self.authored_tables()
        rels = self.relationships if include_auto else self.authored_relationships()
        graph = nx.Graph()
        for table in tables:
            graph.add_node(table.name)
        for rel in rels:
            if rel.is_active:
                graph.add_edge(rel.from_table, rel.to_table, name=rel.name)
        return graph
