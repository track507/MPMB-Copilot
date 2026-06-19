# MPMB Repo Analyzer (`@mpmb/analyze`)

AST-based static analysis of the three MPMB source trees:

- `data/mpmb_source` (2014)
- `data/mpmb_source_2024` (2024)
- `data/imports_source` (community imports)

It parses each file with a real JavaScript AST (acorn + eslint-scope) and emits a JSON
catalog the backend `source_catalog` consumes, plus additive discovery sections. It
replaces the previous regex/brace-scanner Python tool: the registry / function / `Add*`
surface is **discovered**, not hardcoded.

## Run

From the repo root:

```bash
pnpm run analyze        # alias for: pnpm --filter @mpmb/analyze run analyze
```

Output: `scripts/analyze/reports/mpmb-analysis.json` (gitignored).

Optional host-symbol input (Subsystem B, later):
`pnpm --filter @mpmb/analyze run analyze --host-symbols path/to/host.json` reclassifies
undeclared references into host-API vs leak-candidate.

## Two passes

1. **Engine pass** - parses the engine repos (`mpmb_source*`) into the authoritative API
   surface: declared global registries, every function, and the derived `Add*` set.
2. **Corpus pass** - parses all three trees and, per file, extracts registry writes
   (`bracket_object` / `dot_object` / `function_object`, incl. nested `classes.primary`),
   all functions, all call/reference sites, and implicit-global leaks (via eslint-scope),
   classifying each against the engine surface (+ optional host symbols).

## Output

Preserves the backend `CatalogModel` v1 contract (`objects`, `add_calls`, `functions`,
`coverage_metrics`, `repos`, `source_keys`, `required_versions`) plus additive sections:
`discovered_registries`, `all_functions`, `references`, `implicit_globals`,
`undeclared_seed` (the host-symbol seed for the future PDF/Acrobat host-surface
discovery), and `parse_errors`.

`coverage_metrics` are AST health signals: `parse_errors`, `leak_candidates`,
`undeclared_references`, `undiscovered_registries`.

## Dev

```bash
pnpm --filter @mpmb/analyze run test         # vitest
pnpm --filter @mpmb/analyze run typecheck    # tsc --noEmit
```

TypeScript, run via `tsx` (no build step). The analyzer is exempt from the repo's
Acrobat-ES5 eslint config (it is Node tooling); quality is `tsc` + prettier.
`src/migrate-diff.ts` is a one-time migration aid that diffs a new report against a saved
`reports/old-baseline.json` snapshot.

## Notes

- acorn requires valid JS; files with syntax errors (e.g. the `additional content syntax/`
  templates) are recorded in `parse_errors` and skipped, not crashed on.
- Discovery is broad: it surfaces every global object container the engine declares;
  `undiscovered_registries` flags corpus writes to globals the engine did not declare.
- Subsystems B (PDF/Acrobat host-surface discovery) and C (ESLint static validator) are
  separate; see `docs/superpowers/specs/2026-06-18-ast-analyzer-design.md`.
