# MPMB Repo Analyzer

Standalone analysis tool for the three local source trees:

- `data/mpmb_source`
- `data/mpmb_source_2024`
- `data/imports_source`

The analyzer builds a static HTML report plus a JSON sidecar. It is intentionally separate from the backend so parser/indexing ideas can be explored without coupling the experiment to application code. The report is also meant to be useful for maintainers and contributors who need a readable map of where source truth lives.

## Run

From the repository root:

```powershell
uv --cache-dir .uv-cache --project scripts/analyze run python scripts/analyze/analyze-repos.py
```

Default output:

- `scripts/analyze/reports/mpmb-analysis.html`
- `scripts/analyze/reports/mpmb-analysis.json`

Custom output:

```powershell
uv --cache-dir .uv-cache --project scripts/analyze run python scripts/analyze/analyze-repos.py --output docs/mpmb-analysis.html
```

## What It Scans

- Git provenance for each source checkout.
- File inventory and skip/indexable status.
- MPMB registry assignments such as `SpellsList["key"] = { ... }`.
- Dot assignments such as `SourceList.P = { ... }`.
- Function-valued registry assignments such as `MagicItemsList["absorbing tattoo"] = function () { ... }`.
- `Add*` declaration calls such as `AddSubClass(...)`.
- Engine function declarations and assignment-style functions.
- Source-key references.
- Required sheet version calls.
- Syntax template marker and attribute counts.
- Identifier and string references for discovered functions and key symbols.
- Per-file source intelligence: object counts, source keys, required versions, functions, Add calls, reference samples, and line context.
- Coverage metrics for current parser baselines versus robust scanner targets.
- Graph views for spell registry relationships, AddSubClass calls, 2024-specific feature surfaces, source-key provenance, and high-volume file dependencies.

## Report Features

- Interactive file explorer with repo -> folder -> file navigation.
- File detail panel with copyable `rg` commands for exact local reproduction.
- Function reference explorer with definitions separated from references.
- Fan-in file counts and approximate fan-out symbol counts.
- Reference confidence badges: function call, object registry access, exact identifier, likely dynamic reference, and string mention.
- Coverage dashboard for parser gaps and disagreements such as indented object assignments, apostrophe keys, legacy-only object hits, function-valued registry entries, assignment-style functions, and syntax marker gaps.
- Accuracy-mode roadmap showing how a future AST backend can act as a third checker against the baseline regex and brace-aware scanner.

## Accuracy Notes

This version uses a brace-aware scanner and a lightweight JavaScript lexer that skips comments for identifier references while also recording exact symbol mentions inside strings. That is much more reliable than plain grep, but it is not a formal JavaScript AST. The package is structured so a future parser backend, such as tree-sitter or Acorn output, can become a second/third opinion while keeping the report contract.

Git provenance is decoded as UTF-8 explicitly so repository subjects with bullets or other Unicode characters render correctly on Windows.
