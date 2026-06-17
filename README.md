# Copilot Readiness Linter

A static linter that tells you, on day one, whether a Power BI semantic model is
ready for Copilot's "Talk to your data", instead of finding out six weeks into a
tuning effort that the model was never going to clear an acceptable answer rate.

Point it at a repository where your models live as PBIP/TMDL files and it scores
each model, lists exactly what blocks it, and (in CI) fails the pull request when
a model is not ready.

---

## Why this exists

Readiness for Copilot is a property of the **model**, not of the configuration.
A DAX engine compiles a query deterministically; a large language model reasons
over your metadata and maps human intent onto it. The more tangled the schema,
the more it hallucinates join paths, invents totals, and times out. No amount of
prompt tuning fixes a model whose structure is illegible.

The linter separates two kinds of problems, and never mixes them:

- **Cliffs** are structural defects where accuracy collapses regardless of effort
  (a many-to-many relationship, a bidirectional filter, a snowflake). These are a
  binary go/no-go: one of them and the model is **not ready**.
- **Slopes** are quality issues that degrade answers gradually (missing
  documentation, technical names, no synonyms). These are scored, not gated.

That split is the whole design: gate the cliffs, score the slopes.

---

## What it checks (and what it does not)

This is the **Layer 1** gate: static inspection of model metadata. It is fast,
deterministic, needs no deployed model, and runs on every pull request.

It does **not** measure the actual Copilot answer rate. That would be Layer 2 (a
golden-question harness firing real questions at a deployed model) and is out of
scope here. The structural thresholds correlate with accuracy; they do not
replace measuring it.

---

## Install

```bash
pip install -e ".[dev]"     # editable install plus pytest
```

Requires Python 3.9+. Dependencies: `pyyaml`, `networkx`.

---

## Quickstart

```bash
# Lint one model
copilot-readiness lint path/to/Sales.SemanticModel

# Scan a whole repo and gate on it
copilot-readiness lint . --config readiness.yaml
```

Console output is an aligned dashboard (one row per model), focused on failures.
The default level shows the dashboard plus the blocking gates:

```
Copilot Readiness · 2 models (1 ready · 0 incomplete · 1 not ready)

  VERDICT     MODEL          SCORE  STRUCT  META  CALC  BLOCK   WARN   PASS
  -------------------------------------------------------------------------
  NOT READY   bad_snowflake     49      52    47   n/a      5     21     26
  READY       good_star        100     100   100   n/a      0      0     20
  -------------------------------------------------------------------------
  TOTAL                                                     5     21     46

Blocking gates (must fix)
-------------------------
  bad_snowflake
    x Direct many-to-many relationships :: f_sls_trx -> DimPromotion  (many-to-many)
    x Bidirectional relationships :: f_sls_trx -> DimProduct  (bothDirections)
    x Inactive relationships exposed to Copilot :: f_sls_trx.ShipDateKey -> DimDate.DateKey  (isActive=false)
    x Join depth from a field to the fact table :: DimCategory  (3 hop(s) to fact)
    x Join depth from a field to the fact table :: DimSubCategory  (2 hop(s) to fact)

Summary: 1 ready, 0 incomplete, 1 not ready  | blocking 5 | warnings 21 | passed 46 | manual 12
Overall: NOT READY
```

(In a real terminal the verdict and scores are colour-coded; colour is off
automatically for files, pipes, and CI.)

---

## How a model is judged: verdict + score

Two independent axes are reported and never merged into a single number.

### Verdict (the go/no-go decision)

| Verdict | Meaning |
|---|---|
| `READY` | No blocking structural gate failed. |
| `NOT READY` | At least one genuine structural defect (a cliff). Binary on purpose. |
| `INCOMPLETE` | No defect found, but a required input is missing: the model's fact table was not declared, so join depth cannot be assessed. This is a missing input, not a failure. |

### Finition score (for prioritisation)

A score from 0 to 100, per section (Structure, Metadata, Calculations) and
overall, computed from the quality warnings. It tells you how much polish a model
still needs and lets you rank models against each other.

The score is **capped at 49 when the verdict is NOT READY**, so a blocked model
can never look green no matter how clean its metadata is. Think of a Lighthouse
report: category scores, plus a hard list of failing audits.

---

## Output at every level of detail

The console output has a verbosity ladder, so you can dial in exactly how much
you want to see. All examples below are the same two-model scan.

### `-q` (quiet): the dashboard and totals only

Best for a quick health check or a status line. No per-finding detail.

```
$ copilot-readiness lint . --config readiness.yaml -q

Copilot Readiness · 2 models (1 ready · 0 incomplete · 1 not ready)

  VERDICT     MODEL          SCORE  STRUCT  META  CALC  BLOCK   WARN   PASS
  -------------------------------------------------------------------------
  NOT READY   bad_snowflake     49      52    47   n/a      5     21     26
  READY       good_star        100     100   100   n/a      0      0     20
  -------------------------------------------------------------------------
  TOTAL                                                     5     21     46

Summary: 1 ready, 0 incomplete, 1 not ready  | blocking 5 | warnings 21 | passed 46 | manual 12
Overall: NOT READY
```

### default: dashboard plus the blocking gates

What you want in a pull request: the verdict and the exact list of things that
block each model (see the Quickstart output above).

### `-v`: also list the warnings (the scored slopes)

Adds every WARN finding, grouped by model. Use it when you are actively
improving a model's finition score.

```
$ copilot-readiness lint . --config readiness.yaml -v

... dashboard and blocking gates as above ...

Warnings
--------
  bad_snowflake
    - Visible surrogate keys or audit fields :: f_sls_trx.CustomerKey  (visible)
    - Fact table contents :: f_sls_trx  (OrderNote)
    - Abbreviations or technical prefixes in names :: DimCustomer  (DimCustomer)
    - Non-summable numeric fields set to Don't Summarize :: DimDate.Year  (summarizeBy=sum)
    - Geographic columns with a Data Category :: ...
    ... (21 warnings total) ...
```

### `-vv`: everything, including manual checks and passing checks

The full firehose: warnings, the manual checklist (Verified Answers, AI
Instructions, ...), and every check that passed. Use it for a deep audit of a
single model, rarely for a whole repo.

---

## Output formats

Beyond the console, three machine- or review-friendly formats:

### `--format markdown`

The dashboard as a table plus collapsible per-model detail. This is what the
GitHub Action posts as a pull-request comment and writes to the run summary.

### `--format json`

Structured output for tooling: a `summary` block plus, per model, the verdict,
`finition_score`, `section_scores`, counts, and the full list of findings.

```json
{
  "overall_ready": false,
  "summary": { "ready": 1, "incomplete": 0, "not_ready": 1, "blocking": 5, "...": "..." },
  "models": [
    { "model": "bad_snowflake", "verdict": "NOT READY", "finition_score": 49,
      "section_scores": { "Structure": 52, "Metadata": 47, "Calculations": null },
      "findings": [ "..." ] }
  ]
}
```

### `--format github`

GitHub Actions workflow commands: one `::error` annotation per blocking gate
(shown inline on the pull request) and a `::notice` summary. This is what fails
the CI check.

```
::error title=Copilot Readiness: Direct many-to-many relationships::[bad_snowflake] f_sls_trx -> DimPromotion: Direct many-to-many relationship. Resolve it with a physical bridge table to enforce a strict one-to-many flow.
::error title=Copilot Readiness: Bidirectional relationships::[bad_snowflake] f_sls_trx -> DimProduct: Bidirectional cross-filter. This produces false totals; switch to a single direction.
::notice title=Copilot Readiness::1 ready, 0 incomplete, 1 not ready. 5 blocking, 21 warnings.
```

---

## The checks, in full

Every check carries a severity:

- **GATE**: a failure blocks the model (NOT READY).
- **WARN**: reported and scored, never blocking on its own.
- **MANUAL**: cannot be verified from TMDL, surfaced as a checklist item rather
  than silently passed or failed.

### Structural gates (blocking)

| Check | Triggers when | Why it matters |
|---|---|---|
| Direct many-to-many | A relationship has `many` cardinality on both ends | Power BI treats these as limited relationships: blank rows dropped, inner joins, mathematically wrong totals. Resolve with a physical bridge table. |
| Bidirectional relationship | `crossFilteringBehavior` is `bothDirections` | Bidirectional cross-filtering produces false totals and ambiguous filter context. Use a single direction. |
| Inactive relationship exposed | A relationship is inactive and at least one endpoint (table and column) is visible | Copilot only maps active relationships. A visible role-playing relationship is dead weight it cannot use; split the dimension into separate active tables. |
| Join depth to the fact | A visible dimension reaches the fact table in more than one hop (a snowflake) | Copilot cannot reliably traverse multi-hop paths; flatten nested dimensions into one. Requires declared fact tables (see below). A table with no path at all is handled separately as a warning, not a gate. |

### Quality warnings (scored)

| Check | Triggers when | Why it matters |
|---|---|---|
| Auto date/time tables | The model contains hidden `LocalDateTable_*` / `DateTableTemplate_*` tables and their relationships | The auto date/time feature generates one hidden date table per date column, bloating the schema. Disable it and use a single shared date dimension. (One consolidated finding, not one per table.) |
| Disconnected table | A visible table has no active path to any fact, and is not a known utility table (measure holder, what-if parameter, RLS, technical helper) | Copilot cannot relate it to anything, so it answers nothing useful from it. Connect it, or hide it if it is a helper. Utility tables are skipped via the `utility_tables` patterns. |
| Table count | The number of visible tables is outside 5 to 30 | A working range. Far above it usually means the scope is too broad for one Copilot experience. |
| Visible surrogate or audit keys | A visible column matches a key/audit name pattern (`*Key`, `*SK`, `*_id`, audit timestamps) | Keys and audit fields are meaningless to a business question and invite wrong answers. Hide them (use Object-Level Security if sensitive). |
| Fact table contents | A fact table holds a visible descriptive (text) column that is not a key | Fact tables should carry foreign keys and measures only. Descriptive attributes belong in a dimension. |
| Technical names | A table or column name matches a technical prefix/abbreviation (`f_`, `dim`, `fact`, `stg_`, ...) | Copilot maps everyday wording onto names. `f_sls_trx` and `CustID` are guesses waiting to fail; spell names out. |
| Documentation coverage | A visible table, column, or measure has no description | Without descriptions the model guesses from names. Document every exposed object. |
| Description budget | A description is longer than 200 characters | Copilot reads only the first 200 characters of a description. Front-load the business intent, not the formula. |
| Non-summable numerics | A visible numeric column whose name looks like an ID, year, price, or rate is not set to "Don't Summarize" | Otherwise Copilot will happily sum customer IDs or years. Set `summarizeBy` to none. |
| Geographic data category | A visible column with a geographic name has no Data Category | Without it, Copilot draws bars instead of a map. Tag City, Country, Postal Code, and so on. |
| Synonyms | The model has no human-authored synonyms, or two curated terms point at different objects | Synonyms translate business vocabulary into your field names. Only author-curated synonyms count; Power BI's auto-generated and thesaurus-suggested terms do not. Collisions make answers ambiguous. |

### Manual checklist (not verifiable from TMDL)

These artifacts are not reliably present in the model definition, so they are
reported as a checklist to confirm by hand rather than passed or failed.

| Item | What to confirm |
|---|---|
| Calculation groups | A calc group intercepts context via `SELECTEDMEASURE()`, so Copilot cannot tie a metric to its real execution. Confirm a dedicated explicit measure exists for each priority combination. |
| Time intelligence | Confirm YoY / MoM / rolling metrics exist as explicit measures rather than being left for Copilot to generate on the fly. |
| Verified Answers | Confirm each executive KPI has a Verified Answer with five to seven trigger phrases. |
| AI Instructions | Confirm AI Instructions are authored (up to 10,000 characters) and written like prompts. |
| AI data schema | Confirm the Simplify Data Schema selection restricts what Copilot sees, plus Object-Level Security for sensitive metadata. |
| Prepped for AI | Confirm the model is marked "Prepped for AI" once every gate is green. |

---

## Fact tables must be declared

The join-depth gate needs to know which tables are facts. The linter **refuses to
guess** them, because guessing inside a blocking gate destroys trust. Declare them
in `readiness.yaml`. If none is declared for a model, that model is reported as
`INCOMPLETE` (not failed) with a clear message.

```yaml
fact_tables_by_model:
  Sales:
    - FactSales

# Or, for a workspace with a consistent convention:
fact_table_patterns:
  - "^fact_"
```

`fact_table_patterns` is still author-declared: you opt into a naming convention,
the tool does not infer one.

---

## Configuration reference (`readiness.yaml`)

Every field is optional; defaults match the readiness scorecard, so the linter
works with no config at all.

```yaml
# Where to look for models when you point the linter at a repo root.
model_glob: "**/*.SemanticModel"

# Fact tables, declared explicitly per model and/or by naming convention.
fact_tables: []                 # applies to every model (rarely what you want)
fact_tables_by_model: {}        # keyed by model name (folder name without suffix)
fact_table_patterns: []         # e.g. ["^fact_"]

# Exclude Power BI auto date/time artifacts (relationships into a hidden
# LocalDateTable_* / DateTableTemplate_* table). On by default. Note: the
# AutoDetected_* relationship name is a DIFFERENT feature (auto-detection between
# real tables) and is always evaluated, never excluded.
exclude_auto_datetime: true

thresholds:
  max_hops_to_fact: 1           # a pure star is one hop from any dimension
  min_tables: 5
  max_tables: 30
  description_char_budget: 200  # Copilot reads only the first 200 characters

# Case-insensitive regexes matched against object names.
patterns:
  utility_tables: ["parameter", "^_", "\\brls\\b", "^tech"]  # disconnected-by-design tables to skip
  key: [".*key$", ".*sk$", ".*_id$"]
  bad_name_prefixes: ["^f_", "^dim", "^fact"]
  non_summable: [".*id$", "^year$", ".*price$"]
  geo: [".*country.*", ".*city.*", ".*postal.*"]

# Promote a WARN to a blocking GATE, demote a GATE, or turn a rule OFF.
# Keys are rule ids shown in the report (e.g. structure.join_depth).
severity_overrides:
  # metadata.naming: GATE
  # structure.table_count: OFF
```

---

## CLI reference

```bash
copilot-readiness lint <target> [options]
```

`<target>` is a `.SemanticModel` folder or a repo root to scan.

| Option | Effect |
|---|---|
| `--config PATH` | Path to `readiness.yaml` (default: `./readiness.yaml` if present). |
| `--format console\|json\|markdown\|github` | Output format. `github` emits workflow annotations. |
| `-q`, `--quiet` | Console: per-model table and totals only, no finding detail. |
| `-v`, `-vv` | More console detail: `-v` adds warnings, `-vv` adds manual checks and passes. |
| `--select RULE` | Only report these rule ids or sections (comma-separated, repeatable). Example: `--select metadata,structure.join_depth`. |
| `--ignore RULE` | Drop these rule ids or sections so they neither report nor block. Example: `--ignore structure.disconnected_table`. |
| `--no-color` | Disable coloured console output (also off automatically for files, pipes, and CI). |
| `--allow-incomplete` | Exit `0` when the only non-ready models are `INCOMPLETE`; fail solely on real defects. |
| `--output FILE` | Write the report to a file instead of stdout. |

**Exit codes:** `0` only when every model is `READY`; `1` if any model is
`NOT READY` or `INCOMPLETE` (unless `--allow-incomplete`); `2` if no models are
found.

---

## GitHub Action (for your models repo)

A ready-to-use workflow template lives at
[`examples/github-action.yml`](examples/github-action.yml). Copy it into your
**Power BI models** repository as `.github/workflows/copilot-readiness.yml`. On
pull requests that touch any `.SemanticModel` folder it:

1. writes the scorecard to the run's Job Summary,
2. posts (and updates) a sticky pull-request comment with the dashboard,
3. emits an `::error` annotation per blocking gate and fails the required check
   when a model is not ready.

It needs only the built-in `GITHUB_TOKEN`, and installs the linter straight from
this repository. It is shipped as a template rather than an active workflow here
because this package contains only test fixtures (one deliberately broken), so
running the gate against itself would always fail.

This repository's own CI (`.github/workflows/ci.yml`) instead installs the
package and runs the test suite plus a CLI smoke test on every push and pull
request.

---

## How it reads your model (TMDL notes)

The parser is tolerant: it walks the TMDL indentation tree and extracts only what
the rules need, ignoring unknown keys and missing optional files. A few behaviours
worth knowing:

- **Relationship cardinality** defaults to many-to-one when omitted. A
  many-to-many is serialised as `toCardinality: many` (with `fromCardinality`
  defaulting to many).
- **`AutoDetected_*` relationships** are auto-detected relationships between real
  tables and are evaluated like any other. Only relationships into a
  `LocalDateTable_*` / `DateTableTemplate_*` date table are treated as auto
  date/time noise.
- **Synonyms** are parsed from the embedded linguistic-metadata JSON in culture
  files. Only terms with `State: "Authored"` count as curated; `Generated` and
  thesaurus-`Suggested` terms do not.

---

## Limitations

- Layer 1 only: it measures structural legibility, not the live answer rate.
- TMDL input only: live Fabric/Premium models read over XMLA are not covered (the
  parser is structured so an XMLA reader could be added later).
- Hidden objects: rules evaluate visible objects, matching Power BI's "exposed
  object" model. Note that the schema Copilot is grounded on still includes hidden
  objects unless you use the Simplify Data Schema selection or Object-Level
  Security; that caveat is surfaced as a manual checklist item.

---

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

```
src/copilot_readiness/
  cli.py            entry point and exit codes
  config.py         readiness.yaml loading and defaults
  model.py          dataclasses for the parsed model
  tmdl_parser.py    tolerant TMDL reader
  gate.py           verdict and finition scoring
  report.py         console, json, markdown, and github renderers
  rules/
    structure.py    topology and relationship gates
    metadata.py     naming, documentation, aggregation, categories, synonyms
    calculations.py calc groups and the AI-artifact checklist
tests/              unit and end-to-end tests over two sample models
```

---

## License

MIT. See [LICENSE](LICENSE).
