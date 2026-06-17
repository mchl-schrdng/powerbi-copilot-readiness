# Examples

## Point the linter at a real PBIP repo

A Power BI Project saves a semantic model as a `<name>.SemanticModel` folder with
a `definition/` subfolder of TMDL files. Commit that folder to Git and run:

```bash
copilot-readiness lint path/to/your-repo --config readiness.yaml
```

The linter discovers every `*.SemanticModel` folder under the path you give it.

## Try it on the bundled samples

Two sample models ship with the tests:

```bash
# A clean star schema: passes.
copilot-readiness lint tests/fixtures/good_star.SemanticModel \
  --config tests/fixtures/readiness.yaml

# A snowflake with many-to-many, bidirectional, and an exposed inactive
# relationship: fails with five blocking gates.
copilot-readiness lint tests/fixtures/bad_snowflake.SemanticModel \
  --config tests/fixtures/readiness.yaml --format markdown
```

## Declaring fact tables

The topology gate needs to know your fact tables. In `readiness.yaml`:

```yaml
fact_tables_by_model:
  good_star:
    - Sales
  bad_snowflake:
    - f_sls_trx
```

The key is the model name, which is the `.SemanticModel` folder name without the
suffix.
