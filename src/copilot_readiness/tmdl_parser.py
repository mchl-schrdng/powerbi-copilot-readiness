"""Tolerant reader for TMDL (Tabular Model Definition Language) files.

TMDL is an indentation-based, YAML-like text format. This parser does not
implement the full grammar; it walks the indentation tree and extracts only the
properties the readiness rules need. Unknown keys are ignored and missing
optional files do not raise, so a partial or future model still parses.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .model import Column, Measure, Model, Relationship, Synonym, Table

# Keywords that introduce a nested object block in TMDL.
_BLOCK_KEYWORDS = {
    "model",
    "table",
    "column",
    "measure",
    "partition",
    "relationship",
    "calculationGroup",
    "calculationItem",
    "hierarchy",
    "level",
    "role",
    "culture",
    "expression",
    "namedExpression",
}


@dataclass
class _Node:
    """One line of a TMDL file, placed in the indentation tree."""

    keyword: str          # first token, e.g. "table" or a property name
    raw: str              # full line, stripped of indentation
    indent: int
    name: Optional[str] = None        # the declared object name, unquoted
    inline_value: Optional[str] = None  # text after ':' or '='
    children: List["_Node"] = field(default_factory=list)
    description: Optional[str] = None   # from preceding '///' lines


def _strip_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1]
    return text


def _split_qualified(ref: str) -> Tuple[str, str]:
    """Split a 'Table'.'Column' reference into (table, column), unquoting both."""
    ref = ref.strip()
    # Match optional quoted or bare table, a dot, then quoted or bare column.
    match = re.match(r"^\s*('(?:[^']|'')*'|[^.\s]+)\s*\.\s*('(?:[^']|'')*'|.+)$", ref)
    if not match:
        return ref, ""
    return _strip_quotes(match.group(1)), _strip_quotes(match.group(2))


def _parse_declaration(line: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Return (keyword, name, inline_value) for a stripped TMDL line."""
    # measure / column with inline expression: `measure 'X' = SUM(...)`
    keyword = line.split(None, 1)[0] if line.split() else line
    remainder = line[len(keyword):].strip()

    inline_value: Optional[str] = None
    name: Optional[str] = None

    if keyword in _BLOCK_KEYWORDS:
        if "=" in remainder:
            name_part, inline_value = remainder.split("=", 1)
            name = _strip_quotes(name_part.strip())
            inline_value = inline_value.strip()
        else:
            name = _strip_quotes(remainder) if remainder else None
        return keyword, name, inline_value

    # Otherwise it is a property line `key: value` or a bare flag `isHidden`.
    if ":" in line:
        key, value = line.split(":", 1)
        return key.strip(), None, value.strip()
    return line.strip(), None, None


def _build_tree(text: str) -> List[_Node]:
    """Parse file text into a forest of _Node, tracking '///' descriptions."""
    roots: List[_Node] = []
    stack: List[_Node] = []
    pending_desc: List[str] = []

    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        indent = len(raw_line) - len(raw_line.lstrip())
        stripped = raw_line.strip()

        if stripped.startswith("///"):
            pending_desc.append(stripped[3:].strip())
            continue
        if stripped.startswith("//"):
            continue

        keyword, name, inline_value = _parse_declaration(stripped)
        node = _Node(keyword=keyword, raw=stripped, indent=indent, name=name, inline_value=inline_value)
        if pending_desc:
            node.description = " ".join(pending_desc).strip()
            pending_desc = []

        while stack and stack[-1].indent >= indent:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)

    return roots


def _node_prop(node: _Node, key: str) -> Optional[str]:
    for child in node.children:
        if child.keyword == key and child.inline_value is not None:
            return child.inline_value
    return None


def _node_flag(node: _Node, key: str) -> bool:
    """True when a boolean property is present, whether bare or `key: true`."""
    for child in node.children:
        if child.keyword == key:
            if child.inline_value is None:
                return True
            return child.inline_value.strip().lower() == "true"
    return False


def _parse_table_node(node: _Node) -> Table:
    table = Table(name=node.name or "", description=node.description, is_hidden=_node_flag(node, "isHidden"))
    for child in node.children:
        if child.keyword == "column":
            table.columns.append(
                Column(
                    name=child.name or "",
                    table=table.name,
                    data_type=_node_prop(child, "dataType"),
                    summarize_by=_node_prop(child, "summarizeBy"),
                    is_hidden=_node_flag(child, "isHidden"),
                    data_category=_node_prop(child, "dataCategory"),
                    description=child.description,
                    display_folder=_node_prop(child, "displayFolder"),
                )
            )
        elif child.keyword == "measure":
            table.measures.append(
                Measure(
                    name=child.name or "",
                    table=table.name,
                    expression=child.inline_value,
                    description=child.description,
                    is_hidden=_node_flag(child, "isHidden"),
                )
            )
        elif child.keyword == "calculationGroup":
            table.is_calc_group = True
    return table


def _parse_relationship_node(node: _Node) -> Optional[Relationship]:
    from_ref = _node_prop(node, "fromColumn")
    to_ref = _node_prop(node, "toColumn")
    if not from_ref or not to_ref:
        return None
    from_table, from_column = _split_qualified(from_ref)
    to_table, to_column = _split_qualified(to_ref)

    # TMDL omits the default values: many-to-one, single direction, active.
    is_active = True
    active_prop = _node_prop(node, "isActive")
    if active_prop is not None:
        is_active = active_prop.strip().lower() == "true"

    return Relationship(
        name=node.name or f"{from_table}->{to_table}",
        from_table=from_table,
        from_column=from_column,
        to_table=to_table,
        to_column=to_column,
        from_cardinality=_node_prop(node, "fromCardinality") or "many",
        to_cardinality=_node_prop(node, "toCardinality") or "one",
        cross_filtering_behavior=_node_prop(node, "crossFilteringBehavior") or "singleDirection",
        is_active=is_active,
    )


def _find_definition_root(model_path: str) -> str:
    """Return the folder that holds the TMDL definition files."""
    definition = os.path.join(model_path, "definition")
    if os.path.isdir(definition):
        return definition
    return model_path


def _iter_tmdl_files(root: str) -> List[str]:
    found: List[str] = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".tmdl"):
                found.append(os.path.join(dirpath, name))
    return sorted(found)


def parse_model(model_path: str) -> Model:
    """Parse a `.SemanticModel` folder into a :class:`Model`."""
    model_name = os.path.basename(os.path.normpath(model_path))
    if model_name.endswith(".SemanticModel"):
        model_name = model_name[: -len(".SemanticModel")]

    model = Model(name=model_name, source_path=model_path)
    definition_root = _find_definition_root(model_path)

    for file_path in _iter_tmdl_files(definition_root):
        rel = os.path.relpath(file_path, definition_root).replace(os.sep, "/")
        with open(file_path, "r", encoding="utf-8") as handle:
            text = handle.read()
        roots = _build_tree(text)

        is_culture = "cultures/" in rel or rel.startswith("cultures")
        if is_culture:
            model.has_culture_file = True
            _extract_linguistic_synonyms(text, model)

        for node in roots:
            if node.keyword == "table":
                model.tables.append(_parse_table_node(node))
            elif node.keyword == "relationship":
                rel_obj = _parse_relationship_node(node)
                if rel_obj:
                    model.relationships.append(rel_obj)
            elif node.keyword == "model":
                # Relationships are sometimes nested inside the model block.
                for child in node.children:
                    if child.keyword == "relationship":
                        rel_obj = _parse_relationship_node(child)
                        if rel_obj:
                            model.relationships.append(rel_obj)
    return model


def _extract_linguistic_synonyms(text: str, model: Model) -> None:
    """Parse the embedded linguistic-metadata JSON from a culture file.

    Power BI stores synonyms as a JSON object after ``linguisticMetadata =``:
    ``{ "Entities": { "<obj>": { "Terms": [ {"<term>": {...}}, ... ] } } }``.
    We pull each entity's terms into :class:`Synonym`. Auto-generated terms
    (the field name itself) are kept; the rule reasons about collisions.
    """
    marker = "linguisticMetadata"
    idx = text.find(marker)
    if idx == -1:
        return
    brace = text.find("{", idx)
    if brace == -1:
        return

    # Capture the balanced JSON object that follows the marker.
    depth = 0
    end = None
    in_string = False
    escape = False
    for i in range(brace, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        return

    try:
        data = json.loads(text[brace:end])
    except (ValueError, json.JSONDecodeError):
        return

    entities = data.get("Entities", {})
    if not isinstance(entities, dict):
        return
    for entity_name, entity in entities.items():
        if not isinstance(entity, dict):
            continue
        for term_entry in entity.get("Terms", []) or []:
            if isinstance(term_entry, dict):
                for term, detail in term_entry.items():
                    model.synonyms.append(
                        Synonym(
                            target_object=entity_name,
                            term=term,
                            generated=not _is_authored_term(detail),
                        )
                    )


def _is_authored_term(detail) -> bool:
    """True only for human-curated synonyms.

    Power BI marks terms it created itself: ``State: "Generated"`` (from the
    object name) or ``State: "Suggested"`` with a ``Source.Agent`` (from the
    thesaurus). A human-added synonym has ``State: "Authored"`` and no agent
    source. Everything else is treated as not curated.
    """
    if not isinstance(detail, dict):
        return False
    if "Source" in detail and isinstance(detail["Source"], dict) and detail["Source"].get("Agent"):
        return False
    return str(detail.get("State", "")).lower() == "authored"
