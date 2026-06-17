# Copilot Readiness Linter

Static linter that gates Power BI semantic models (PBIP/TMDL files in Git) for
Copilot "Talk to your data" readiness. Pure Python, no .NET. Layer 1 only
(static metadata inspection); it does not run questions against a live model.

## Run

```bash
pip install -e ".[dev]"          # install + pytest
pytest -q                        # 41 tests
copilot-readiness lint <repo-or-model> --config readiness.yaml
```

- Verbosity: `-q` summary only · default adds blocking gates · `-v` adds warnings · `-vv` adds manual + passes.
- Formats: `--format console|json|markdown|github`.
- Exit: `0` only if every model is READY; `1` if any is NOT READY or INCOMPLETE; `--allow-incomplete` passes INCOMPLETE-only runs.

## Architecture

- `tmdl_parser.py` parses a `.SemanticModel` folder into `model.py` dataclasses.
- `rules/` holds the checks (`structure`, `metadata`, `calculations`); each returns `Finding`s with a section, status, and severity.
- `gate.py` computes the verdict and scores; `report.py` renders; `cli.py` is the entry point and owns the exit code.

## Two axes (never merge them)

- **Verdict**: `READY` / `NOT READY` / `INCOMPLETE`, driven only by the hard structural GATES (the cliffs): direct many-to-many, bidirectional, exposed inactive relationship, snowflake / join depth over one hop. `INCOMPLETE` means no defect found but a required input (the fact-table declaration) is missing.
- **Finition score** (0-100, per section + overall), driven by the WARN checks (the slopes). It is capped at 49 when the verdict is NOT READY so a blocked model can never look green.

## Invariants (each is a past bug; do not regress)

- Fact tables are **author-declared** (`fact_tables`, `fact_tables_by_model`, or `fact_table_patterns`). Never guess them; emit `config.no_fact_table` instead.
- Auto date/time = relationships whose endpoint is a `LocalDateTable_*` or `DateTableTemplate_*` table. The `AutoDetected_*` relationship **name** is a different feature (auto-detection between real tables) and must be gated, not excluded.
- Synonyms: only `State: "Authored"` terms count. `Generated` (from object names) and thesaurus `Suggested` terms are not curated.
- Hidden-object scoping: rules check visible objects (matches the article's "exposed objects" language). The fact that the AI schema still includes hidden objects is surfaced as a manual checklist item, not a code gate.
- TMDL relationship cardinality defaults to many-to-one; a many-to-many is serialized as `toCardinality: many` with `fromCardinality` defaulted to many.
- Config regex patterns are case-insensitive (`re.IGNORECASE`).

## Conventions

- No em dashes anywhere (output, code, docs).
- Tests assert observable behavior (findings, exit codes), not internals. Add a regression test for every bug fix.
