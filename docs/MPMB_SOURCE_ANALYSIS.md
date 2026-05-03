# MPMB Source Material Analysis

Analysis date: 2026-05-03

This document is a source-level analysis of the local MPMB trees used by MPMB-Copilot:

- `data/mpmb_source`
- `data/mpmb_source_2024`
- `data/imports_source`

It is intentionally more detailed than a simple file inventory. The goal is to capture the real syntax surface, content patterns, parser/indexer gaps, and retrieval implications for `backend/app/core/chunker.py`, `backend/app/core/intent.py`, `backend/app/core/query_analysis.py`, and the agentic source tools.

## Executive Findings

1. `data/mpmb_source` is the current 2014-rule MPMB sheet source. It is on branch `master`, commit `f059e44`, tag `v14.0.7`, dated 2026-04-28.
2. `data/mpmb_source_2024` now tracks the separate active 2024 repository, `morepurplemorebetter/2024_MPMBs-Character-Record-Sheet`, on branch `main`, commit `4537ae1`, tag `v24.0.7`, dated 2026-04-28. The old 2024 branch on `morepurplemorebetter/MPMBs-Character-Record-Sheet` is no longer published, which is why pulling from that branch failed.
3. `data/imports_source` is the safety-orange imports repo on branch `master`, commit `5c978b0`, dated 2026-04-28. It contains the best concrete examples of WotC content, including newer 2024 import files.
4. The 2014 and 2024 MPMB source repos still share most paths, but they are no longer identical file-set twins: 148 paths are shared, 30 same-path files differ, and 4 files exist only in the 2024 repo. The 2024-only files are `FunctionsHelpers.js`, `ListsEvals.js`, `DefaultEvalsList` syntax, and `WeaponMasteriesList` syntax.
5. The imports repo is much larger than the two MPMB source trees because it includes generated aggregate bundles. Those generated bundles must remain excluded from indexing, or object counts will be roughly doubled.
6. The active 2024 source adds first-class 2024 surfaces that retrieval must understand: `WeaponMasteriesList`, `DefaultEvalsList`, weapon mastery metadata on `WeaponsList`, `reqLoS` spell metadata, and 2024 origin feat/species patterns.
7. `PsionicsList` appears heavily in imports, especially UA mystic/psionics content, while `ToolsList` is documented in MPMB syntax. Both need first-class routing alongside the new 2024 registries.
8. Current object and `Add*` regexes are anchored at column 1. Real import/community files often indent top-level registrations. A whitespace-tolerant regex would recover about 422 additional object assignments and about 136 additional mapped `Add*` calls in the current indexing set.
9. Five WotC magic items are registry assignments to `function () { ... }` rather than object literals. The current object extractor only captures `= { ... }`, so those entries are invisible.
10. The read/grep/function tools currently expose only `mpmb_source`, `mpmb_source_2024`, and upload roots. They do not expose `imports_source`, even though imports are the strongest example corpus.

## Repository Inventory

Static scan of local files, excluding `.git` and `node_modules`:

| Source root | Branch | Commit | Date | JS files | Indexable JS | Lines | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| `data/mpmb_source` | `master` | `f059e44` | 2026-04-28 | 143 | 143 | 116,474 | Current 2014-rule MPMB source, tag `v14.0.7` |
| `data/mpmb_source_2024` | `main` | `4537ae1` | 2026-04-28 | 147 | 147 | 121,407 | Current 2024-rule MPMB source, tag `v24.0.7` |
| `data/imports_source` | `master` | `5c978b0` | 2026-04-28 | 141 | 134 | 257,668 | Includes generated bundles and minified files |

`Indexable JS` excludes `all_WotC_*.js`, `*.min.js`, `gulpfile.js`, `package.json`, and `package-lock.json`.

## Source Tiers

The source trees are not all equally authoritative. Retrieval should preserve this distinction.

| Tier | Local paths | Role in answers |
|---|---|---|
| `authoritative.syntax` | `mpmb_source*/additional content syntax/*.js` | Defines valid add-on object attributes and examples |
| `authoritative.engine` | `mpmb_source*/_functions/*.js` | Defines runtime behavior, validation, import flow, field mutation |
| `official.builtin_variables` | `mpmb_source*/_variables/*.js` | Built-in SRD/default lists used by the sheet |
| `official.imports_2014_published` | `imports_source/WotC material/pub_*.js` | Best 2014 WotC examples |
| `official.imports_2014_ua` | `imports_source/WotC material/ua_*.js` | 2014 playtest examples, useful but lower trust |
| `official.imports_2014_plane_shift` | `imports_source/WotC material/ps_*.js` | Plane Shift examples |
| `official.imports_2024` | `imports_source/WotC 2024/pub_*.js` | Best current 2024 examples |
| `official.imports_2024_not_reprinted` | `imports_source/WotC 2024/not-reprinted_*.js` | Legacy content explicitly not reprinted |
| `community.mpmb_examples` | `mpmb_source/additional content/**/*.js` | Third-party/community implementation examples |
| `community.imports_homebrew` | `imports_source/Homebrew/*.js` | Homebrew examples |
| `duplicate.bundle` | `imports_source/WotC material/all_WotC_*.js` | Generated aggregate output; skip |
| `duplicate.minified` | `imports_source/WotC material/*.min.js` | Generated minified output; skip |
| `wip.2014` | `imports_source/WotC material/wip_*.js` | Incomplete/excluded material; index as low priority or skip |

## Directory-Level Counts

| Root | Bucket | Files | Lines |
|---|---|---:|---:|
| `mpmb_source` | `_functions` | 13 | 41,318 |
| `mpmb_source` | `_variables` | 13 | 25,231 |
| `mpmb_source` | `additional content syntax` | 22 | 10,380 |
| `mpmb_source` | `additional content` | 95 | 39,545 |
| `mpmb_source_2024` | `_functions` | 14 | 42,357 |
| `mpmb_source_2024` | `_variables` | 14 | 28,593 |
| `mpmb_source_2024` | `additional content syntax` | 24 | 10,912 |
| `mpmb_source_2024` | `additional content` | 95 | 39,545 |
| `imports_source` | `WotC material`, published | 55 | 62,891 |
| `imports_source` | `WotC material`, UA | 67 | 28,976 |
| `imports_source` | `WotC material`, Plane Shift | 6 | 2,220 |
| `imports_source` | `WotC material`, WIP | 1 | 1,037 |
| `imports_source` | generated bundles/minified | 6 | 157,231 |
| `imports_source` | `WotC 2024` | 4 | 4,994 |
| `imports_source` | `Homebrew` | 1 | 160 |
| `imports_source` | `gulpfile.js` | 1 | 159 |

## Source Comparison: `mpmb_source` vs `mpmb_source_2024`

The 2014 and 2024 source checkouts are sibling repositories. Path equality is still useful for shared engine/syntax files, but 2024 also has its own files that should be indexed as 2024-only authoritative material.

| Comparison | Count |
|---|---:|
| Same relative paths | 148 |
| Changed same-path files | 30 |
| Only in `mpmb_source` | 0 |
| Only in `mpmb_source_2024` | 4 |

Changed files by folder:

| Folder | Changed files |
|---|---:|
| `_variables` | 11 |
| `additional content syntax` | 9 |
| `_functions` | 8 |
| root/metadata | 2 |

2024-only files:

- `_functions/FunctionsHelpers.js`
- `_variables/ListsEvals.js`
- `additional content syntax/calculation changes - default calcChanges (DefaultEvalsList).js`
- `additional content syntax/weapon mastery (WeaponMasteriesList).js`

Changed shared files include:

- `_functions/Functions0.js`
- `_functions/Functions1.js`
- `_functions/Functions2.js`
- `_functions/Functions3.js`
- `_functions/FunctionsImport.js`
- `_functions/FunctionsResources.js`
- `_functions/FunctionsSpells.js`
- `_functions/AbilityScores.js`
- `_variables/Lists.js`
- `_variables/ListsBackgrounds.js`
- `_variables/ListsClasses.js`
- `_variables/ListsCompanions.js`
- `_variables/ListsCreatures.js`
- `_variables/ListsFeats.js`
- `_variables/ListsGear.js`
- `_variables/ListsMagicItems.js`
- `_variables/ListsRaces.js`
- `_variables/ListsSources.js`
- `_variables/ListsSpells.js`
- `additional content syntax/_common attributes.js`
- `additional content syntax/adventuring gear - equipment (GearList).js`
- `additional content syntax/adventuring gear - pack (PacksList).js`
- `additional content syntax/companion template option (CompanionList).js`
- `additional content syntax/creature, wild shape option (CreatureList).js`
- `additional content syntax/feat (FeatsList).js`
- `additional content syntax/magic item (MagicItemsList).js`
- `additional content syntax/spell (SpellsList).js`
- `additional content syntax/weapon (WeaponsList).js`

## Imports Repo Inventory

`imports_source/WotC material` contains both individual source files and generated bundles.

| Group | Files | Lines | Main object families | Main `Add*` calls |
|---|---:|---:|---|---|
| Published 2014, `pub_*.js` | 55 | 62,891 | magic items, spells, races, background features, feats, creatures | subclasses, feature choices, background variants, racial variants |
| UA 2014, `ua_*.js` | 67 | 28,976 | psionics, feats, races, spells, magic items | subclasses, feature choices, invocations |
| Plane Shift, `ps_*.js` | 6 | 2,220 | races, creatures, sources | subclasses |
| WIP excluded items | 1 | 1,037 | magic items | none |
| Generated bundles/minified | 6 | 157,234 | duplicate aggregate content | duplicate aggregate content |

`imports_source/WotC 2024` currently contains:

| File | Lines | Robust object count | Contents |
|---|---:|---:|---|
| `pub_20240917_PHB.js` | 4,262 | 142 | `P24`, 58 feats, 53 spells, 12 backgrounds, 12 background features, 5 weapons, 1 race, 3 subclasses |
| `pub_20250218_MM.js` | 125 | 4 | `M24`, 3 creatures |
| `not-reprinted_20140819_PHB.js` | 543 | 22 | 2014 content not in 2024 PHB; features, feats, races, companion, invocations |
| `not-reprinted_20201117_TCoE.js` | 64 | 0 object literals | 1 subclass not reprinted |

2024 import-specific details:

- `pub_20240917_PHB.js` uses `RequiredSheetVersion("24.0.6-beta")`.
- `pub_20250218_MM.js` uses `RequiredSheetVersion("24.0.1-beta")`.
- `pub_20240917_PHB.js` contains 23 `reqLoS: true` spell entries. That attribute is present in real 2024 imports but is not documented in the current syntax template scan.
- Four 2024 PHB spell keys contain apostrophes and are missed by the current key regex: `crusader's mantle`, `jallarzi's storm of radiance`, `tasha's bubbling cauldron`, and `yolande's regal presence`.

The imports `gulpfile.js` distinguishes stable and beta sheet versions:

- Stable: `14.0.6-beta`, max `15.0.0`
- Beta: `24.0.6-beta`

## Object Registries Observed

Across all source trees, including generated bundles, these registry object names appear:

| Registry | Raw count | Meaning |
|---|---:|---|
| `MagicItemsList` | 1,889 | Magic items |
| `SpellsList` | 1,554 | Spells |
| `RaceList` | 764 | Races/species |
| `FeatsList` | 754 | Feats |
| `PsionicsList` | 693 | Psionic talents/disciplines |
| `SourceList` | 452 | Source books/documents |
| `BackgroundFeatureList` | 409 | Background features |
| `CreatureList` | 334 | Creatures/wild shape options |
| `BackgroundList` | 275 | Backgrounds |
| `WeaponsList` | 263 | Weapons/attack options |
| `ClassList` | 62 | Classes |
| `AmmoList` | 51 | Ammunition |
| `GearList` | 46 | Adventuring gear |
| `CompanionList` | 14 | Companion templates/options |
| `ClassSubList` | 26 | Legacy/direct subclass registry entries |
| `PacksList` | 10 | Equipment packs |
| `ArmourList` | 7 | Armor/shields |
| `ToolsList` | 2 | Tool equipment options |
| `DefaultEvalsList` | 1 | Always-on 2024 calculation changes |
| `WeaponMasteriesList` | 1 | 2024 weapon mastery options |

The raw count includes generated bundles and both MPMB source repos. Use the current-indexing count below for practical chunk estimates.

## Current Indexing Reality

Mirroring the current `MPMBChunker.run_all()` source selection and current extractor maps, before fixing regex gaps:

| Chunk family | Current count |
|---|---:|
| Object literal chunks | 3,400 |
| Mapped `Add*` function-call chunks | 743 |
| Syntax template attribute chunks | 560 |
| Engine function declaration occurrences | 1,197 |
| Selected source files | 424 |

Object literal chunks currently captured:

| Object type | Current count |
|---|---:|
| `SpellsList` | 942 |
| `MagicItemsList` | 559 |
| `RaceList` | 324 |
| `FeatsList` | 311 |
| `SourceList` | 286 |
| `PsionicsList` | 229 |
| `WeaponsList` | 163 |
| `BackgroundFeatureList` | 161 |
| `CreatureList` | 129 |
| `BackgroundList` | 107 |
| `ClassList` | 53 |
| `AmmoList` | 37 |
| `GearList` | 34 |
| `ClassSubList` | 26 |
| `CompanionList` | 21 |
| `PacksList` | 11 |
| `ArmourList` | 5 |
| `DefaultEvalsList` | 1 |
| `WeaponMasteriesList` | 1 |

Mapped `Add*` calls currently captured:

| Function | Current count | Meaning |
|---|---:|---|
| `AddSubClass` | 399 | Subclass definitions |
| `AddWarlockInvocation` | 100 | Warlock/eldritch invocation options |
| `AddRacialVariant` | 83 | Race/species variants |
| `AddFeatureChoice` | 79 | Feature choices/extrachoices |
| `AddBackgroundVariant` | 67 | Background variants |
| `AddFightingStyle` | 13 | Fighting styles |
| `AddWarlockPactBoon` | 2 | Warlock pact boons |

A robust object pass that allows leading whitespace, dot assignments, and matching quote backreferences would capture 3,828 object literal chunks from the same selected source set, or 428 more than the current extractor. Robust mapped `Add*` extraction would capture 879 calls, or 136 more than the current extractor.

## Parser and Coverage Gaps

These are the highest-impact fixes for getting closer to full source coverage.

### 1. Complete `PsionicsList` coverage

Observed:

- 229 currently indexable `PsionicsList` assignments after adding the registry to the chunker map.
- 693 raw assignments if generated bundles are included.
- `FunctionsSpells.js` explicitly merges `PsionicsList` into `SpellsList` at runtime.

Implemented app-map changes:

- Add `"PsionicsList": "psionic"` to `OBJECT_TYPE_MAP`.
- Add `PsionicsList` to `_MPMB_SYMBOLS` in `intent.py`.
- Add `PsionicsList` to `_CODE_IDENTIFIERS` in `query_analysis.py`.
- Add natural-language mappings for `psionic`, `psionics`, `psionic discipline`, and `psionic disciplines`.

Remaining work: add metadata filters/retrieval tests for psionic-specific user language, especially bare `mystic`, `discipline`, and `talent`.

### 2. Complete `ToolsList` coverage

`chunker.py`, `intent.py`, and `query_analysis.py` now map `ToolsList`.

Implemented app-map changes:

- Add `ToolsList` to `_MPMB_SYMBOLS`.
- Add `ToolsList` to `_CODE_IDENTIFIERS`.
- Add keyword mappings for `tool`, `tools`, `artisan tools`, `tool proficiency`, and `proficiencies`.

Remaining work: add plural/specific proficiency keywords where needed, such as `artisan tool`, `artisan tools`, `tool proficiency`, and `tool proficiencies`.

### 3. Make object/call regexes indentation tolerant

Current patterns require column-1 registrations:

```python
r"^(\w+)\s*\[..."
r"^(Add\w+)\s*\("
```

Real content commonly indents top-level registrations inside grouping braces or wrapper blocks. In the current indexing set, accepting leading whitespace would recover approximately:

| Missed shape | Additional chunks |
|---|---:|
| Object assignments | 422 |
| Mapped `Add*` calls | 136 |

Use `^\s*` for object and function-call extraction.

### 4. Parse keys using the matching quote

Current object-key regex rejects keys that contain the other quote character:

```python
["']([^"']+)["']
```

That fails for valid keys like:

- `ToolsList["purplemancer's tools"]`
- `SpellsList["crusader's mantle"]`
- `BackgroundFeatureList["ship's passage"]`
- `MagicItemsList["warsmith's armor"]`

Use a quote backreference:

```python
r'^\s*(\w+)\s*\[\s*(["\'])(.*?)\2\s*\]\s*=\s*\{'
```

If escaped quotes inside keys become relevant, upgrade the key capture to handle escapes.

### 5. Capture registry assignments to functions

The imports repo contains five non-bundle magic item entries of this shape:

```javascript
MagicItemsList["absorbing tattoo"] = function () { ... }
```

Current object extraction only captures `= { ... }`. These function-valued registry entries are real content and should be chunked as `object_factory` or `function_valued_object`.

Observed function-valued registry entries:

- `lantern of tracking`
- `absorbing tattoo`
- `dragon wing bow`
- `potion of dragon's majesty`
- `scaled ornament`

### 6. Expand engine function extraction

A broad engine scan found:

| Source | Unique function-like names | Function-like occurrences |
|---|---:|---:|
| `mpmb_source` | 702 | 747 |
| `mpmb_source_2024` | 725 | 769 |

The current `FunctionDefinitionExtractor` only captures `function name(...) { ... }`. It misses `var name = function (...) { ... }` and `name = function (...) { ... }` definitions. The `mpmb_function` tool already searches those shapes, so the indexer should match the tool's broader function patterns.

### 7. Expose imports to tools

`backend/app/core/tools/source_paths.py` currently defines:

- `ROOT_MPMB_2014`
- `ROOT_MPMB_2024`
- `ROOT_UPLOADS_SESSION`
- `ROOT_UPLOADS_GLOBAL`

It does not define `ROOT_IMPORTS`. This means the model can retrieve import chunks from Qdrant but cannot verify the exact import file via `mpmb_read` or `mpmb_grep`.

Recommended addition:

```python
ROOT_IMPORTS = "./data/imports_source/"
```

Add it to `ALLOWED_ROOTS`, `_build_default_roots`, and any tool prompt/schema text.

## Syntax Template Coverage

The syntax templates are the closest thing to formal documentation. A broad required/optional marker scan found:

| Source | Required/optional markers |
|---|---:|
| `mpmb_source` | 415 |
| `mpmb_source_2024` | 433 |

The current `SyntaxTemplateExtractor` captures only attribute lines followed by required/optional comments. That produces 560 chunks across both source repos:

| Syntax file | 2014 chunks | 2024 chunks |
|---|---:|---:|
| `_common attributes.js` | 72 | 72 |
| `_common spell list object.js` | 8 | 8 |
| `adventuring gear - equipment (GearList).js` | 6 | 6 |
| `adventuring gear - pack (PacksList).js` | 2 | 2 |
| `adventuring gear - tool (ToolsList).js` | 6 | 6 |
| `ammunition (AmmoList).js` | 8 | 8 |
| `armor (ArmourList).js` | 16 | 16 |
| `class (ClassList)_unfinished.js` | 9 | 9 |
| `companion template option (CompanionList).js` | 8 | 8 |
| `creature, wild shape option (CreatureList).js` | 32 | 34 |
| `feat (FeatsList).js` | 11 | 13 |
| `magic item (MagicItemsList).js` | 31 | 31 |
| `source (SourceList).js` | 8 | 8 |
| `spell (SpellsList).js` | 32 | 33 |
| `weapon (WeaponsList).js` | 27 | 27 |
| `weapon mastery (WeaponMasteriesList).js` | 0 | 3 |
| `calculation changes - default calcChanges (DefaultEvalsList).js` | 0 | 0 |

The current syntax extractor intentionally does not capture all header/object-name blocks, including:

- `iFileName`
- `RequiredSheetVersion`
- `SpellsList object name`
- `FeatsList object name`
- similar "object name" blocks for other registries
- the 2024-only `DefaultEvalsList` template, which primarily documents object identity and points to common `calcChanges` attributes

Those blocks are useful for how-to and generation answers. Consider a second syntax extractor pass for `template_header` and `template_object_key` chunks.

## Syntax Differences Between Sources

Important source-level syntax differences:

| File | 2014-only documented fields | 2024-only documented fields | Notes |
|---|---|---|---|
| `_common attributes.js` | none | none | Both sources now expose the same broad common attribute field set |
| `creature, wild shape option (CreatureList).js` | none | `formatSpellDescription`, `immunities`, `resistances`, `useSpellDescription`, `vulnerabilities` | 2024 creature syntax expands spell text and damage modifier display support |
| `feat (FeatsList).js` | none | `choicesNotInMenu`, `descriptionClassFeature`, `sortname` | 2024 feat menu and class-feature rendering behavior differs |
| `spell (SpellsList).js` | none | `reqLoS` | 2024 spell syntax documents line-of-sight requirements |
| `weapon mastery (WeaponMasteriesList).js` | file absent | `name`, `source`, `description`, `descriptionFull` | 2024-only registry referenced by `WeaponsList.mastery` |
| `calculation changes - default calcChanges (DefaultEvalsList).js` | file absent | object-name/header docs only | 2024-only always-on `calcChanges` registry; needs header/object-key extraction |

One important anomaly: both 2014 and 2024 syntax templates commonly use `RequiredSheetVersion("14.0.5", "24.0.0")` as a compatibility gate. Do not use that call alone as an edition signal; source path, source keys such as `P24`/`M24`, and 2024-only registry names are stronger signals.

## Edition Signals

Use multiple signals. No single signal is enough.

| Signal | Meaning | Reliability |
|---|---|---|
| Path starts `imports_source/WotC 2024/` | 2024 import content | High |
| Path starts `imports_source/WotC material/` | 2014 import content | High |
| `RequiredSheetVersion("24...")` | 2024 sheet content | High |
| `RequiredSheetVersion("14...", "15.0.0")` or max below 24 | 2014 sheet content | High |
| Source key ends/contains `24`, for example `P24`, `M24` | 2024 source | Medium |
| `WeaponMasteriesList` or `DefaultEvalsList` | 2024-only MPMB registry | High |
| `mpmb_source` root | 2014 source repo | High |
| `mpmb_source_2024` root | 2024 source repo | High |
| `descriptionFull` as array | common in newer syntax and 2024 imports | Low by itself |
| `type: "origin"` on feats | 2024 feat style | Medium |
| `reqLoS` | 2024 spell import behavior | Medium |

## Object-Type Deep Dive

### `SourceList`

Role: source declaration and source filtering.

Common fields:

- `name`
- `abbreviation`
- `abbreviationSpellsheet`
- `group`
- `url`
- `date`
- `campaignSetting`
- `defaultExcluded`

Retrieval metadata to extract:

- `source_key`
- `display_name`
- `abbreviation`
- `group`
- `date`
- `url`
- `campaign_setting`
- `default_excluded`

Source keys are central to grounding examples. Top source refs in the local scan include `UA:TMC`, `X`, `P`, `T`, `E:RLW`, `KCCC`, `W`, `L:SM`, `XPtL3:IA`, `BoMT`, `ELCC`, `D`, `WGtE`, `MM:BH`, and `MW:SC`.

### `SpellsList`

Role: spell/cantrip/psionic spell-like definitions.

Core fields:

- `name`, `nameAlt`, `nameShort`
- `regExpSearch`
- `source`
- `defaultExcluded`
- `classes`
- `level`
- `school`
- `time`, `timeFull`
- `range`, metric range variant
- `components`, `compMaterial`
- `duration`
- `save`
- `description`
- `descriptionCantripDie`
- `descriptionMetric`
- `descriptionFull`
- `ritual`
- `psionic`
- `firstCol`
- `dependencies`
- `allowUpCasting`
- `descriptionShorter`, `descriptionShorterMetric`
- `dynamicDamageBonus`

2024-specific observed fields/behaviors:

- `reqLoS: true` appears in 23 PHB 2024 spell entries.
- `descriptionFull` may be an array and may use formatting tags.
- Time abbreviations shift toward PHB 2024 naming, for example `Act` style in imports.

Metadata to extract:

- `spell_level`
- `spell_school`
- `classes`
- `time`
- `range`
- `components`
- `duration`
- `save`
- `ritual`
- `psionic`
- `requires_line_of_sight`
- `dependencies`
- `damage_types` if derivable
- `source_book`, `source_page`

### `PsionicsList`

Role: psionic talents and disciplines, historically used by Mystic/UA psionics.

Common fields observed:

- `name`
- `source`
- `psionic`
- `level`
- `school`
- `time`
- `range`
- `duration`
- `description`
- `descriptionFull`
- `firstCol`
- `classes`
- `save`
- `components`
- `dependencies`

Retrieval implication: treat `PsionicsList` as spell-adjacent but not identical. It should be searchable by `psionic`, `psionics`, `mystic`, `discipline`, and `talent`, and it should share some metadata with `SpellsList`.

### `ClassList`

Role: full class definitions.

High-value fields:

- `name`, `regExpSearch`, `source`
- `primaryAbility`
- `prereqs`, `prereqeval`
- `die`
- `improvements`
- `saves`
- `skills`
- `armorProfs`, `weaponProfs`, `toolProfs`
- `equipment`
- `subclasses`
- `attacks`
- `spellcastingFactor`
- `spellcastingKnown`, `spellcastingList`, `spellcastingAbility`
- `features`

Nested fields inside `features` are as important as the class root:

- feature key, usually `classfeatureN` or similar
- `name`
- `minlevel`
- `description`
- `additional`
- `usages`, `usagescalc`, `recovery`
- `action`
- `eval`, `removeeval`, `changeeval`
- `spellcastingBonus`, `spellcastingExtra`
- `weaponOptions`, `armorOptions`, `magicitemsAdd`
- `calcChanges`
- `choices`, `extrachoices`

Chunking recommendation: create both a class-root chunk and nested feature chunks. A user asking about "why is my level 6 feature not showing" needs the specific feature object, not the whole class file.

### `AddSubClass` and `ClassSubList`

Role: subclass definitions.

`AddSubClass(parent_class, subclass_key, {...})` is the dominant modern pattern. `ClassSubList[...] = {...}` appears mostly in older/pre-v13 content.

Top subclass parents in local source:

| Parent class | Count |
|---|---:|
| `fighter` | 77 |
| `cleric` | 74 |
| `wizard` | 69 |
| `warlock` | 62 |
| `sorcerer` | 59 |
| `monk` | 53 |
| `bard` | 53 |
| `barbarian` | 51 |
| `paladin` | 51 |
| `rogue` | 49 |
| `druid` | 46 |
| `mystic` | 18 |
| `rangerua` | 15 |
| `ranger` | 14 |

Metadata to extract:

- `function_name = AddSubClass`
- `parent_class`
- `subclass_key`
- `subname`
- `fullname`
- `source_book`, `source_page`
- `features`
- nested feature keys/min levels
- `spellcastingFactor` or subclass spellcasting fields

### `RaceList` and `AddRacialVariant`

Role: races/species and race variants.

High-value fields:

- `name`, `plural`, `sortname`
- `regExpSearch`
- `source`
- `size`
- `speed`
- `languageProfs`
- `vision`
- `savetxt`
- `dmgres`
- `skillstxt`, `skills`
- `toolProfs`, `weaponProfs`, `armorProfs`
- `scores`, `scorestxt`
- `trait`
- `features`
- `spellcastingBonus`, `spellcastingAbility`
- `featsAdd`
- `height`, `weight`, metric variants

2024 note: the app should map user wording `species` to `RaceList`, which it already does. Add `origin feat` and `featsAdd` awareness for 2024 species.

### `FeatsList`

Role: feats, including 2024 origin feats.

High-value fields:

- `name`
- optional menu `name` in 2024 syntax
- `source`
- `type`
- `defaultExcluded`
- `prerequisite`
- `prereqeval`
- `allowDuplicates`
- `description`
- `descriptionFull`
- `calculate`
- `choices`
- `choicesNotInMenu`
- `selfChoosing`
- `scores`, `scorestxt`
- `spellcastingBonus`, `spellcastingAbility`
- `weaponOptions`
- `action`
- `usages`, `usagescalc`, `recovery`

2024-specific observed fields:

- `type: "origin"` appears in 2024 built-in variables/imports.
- `choicesNotInMenu`, `descriptionClassFeature`, and `sortname` are documented in the 2024 feat syntax.

### `MagicItemsList`

Role: magic items, including items with choices, generated variants, and function-valued factories.

High-value fields:

- `name`
- `source`
- `type`
- `rarity`
- `attunement`
- `prerequisite`, `prereqeval`
- `description`
- `descriptionFull`
- `weight`
- `magicItemTable`
- `choices`
- `selfChoosing`
- `allowDuplicates`
- `weaponOptions`, `armorOptions`, `ammoOptions`
- `spellcastingBonus`
- `calcChanges`
- `usages`, `usagescalc`, `recovery`
- `action`
- `eval`, `removeeval`
- `selectNow`
- `defaultExcluded`

Parser note: capture both object literals and `MagicItemsList["key"] = function () { ... }` factories.

### `WeaponsList`, `AmmoList`, `ArmourList`, `GearList`, `PacksList`, `ToolsList`

Role: equipment and inventory/menu automation.

Common weapon fields:

- `name`
- `regExpSearch`
- `source`
- `list`
- `type`
- `ability`
- `abilitytodamage`
- `damage`
- `range`
- `description`
- `weight`
- `dc`
- `ammo`
- `monkweapon`
- `isAlwaysProf`
- `isNotWeapon`
- `useSpellcastingAbility`
- `modifiers`
- `tooltip`

Common armor fields:

- `name`
- `regExpSearch`
- `source`
- `type`
- `list`
- `ac`
- `dex`
- `stealthdis`
- `weight`
- `strReq`
- `addMod`
- `isMagicArmor`
- `affectsWildShape`

Common gear/tool/pack fields:

- `infoname`
- `name`
- `amount`
- `weight`
- `type`
- `source`
- `items` for packs

Intent/query gap: add `tool`, `tools`, and plural `packs` keyword mappings. Current query analysis maps `pack` but not `packs`, and does not map tool wording.

### `BackgroundList`, `BackgroundFeatureList`, `AddBackgroundVariant`

Role: backgrounds, their feature text, and variants.

Background fields:

- `name`
- `regExpSearch`
- `source`
- `skills`
- `skillstxt`
- `gold`
- `equipleft`, `equipright`, `equip1stPage`
- `feature`
- `trait`, `ideal`, `bond`, `flaw`
- `toolProfs`
- `languageProfs`
- `lifestyle`
- `extra`
- `variant`
- `scorestxt`
- `spellList`
- `calcChanges`

Background feature fields:

- `description`
- `source`
- `featsAdd`
- `spellList`
- `calcChanges`
- `options`

### `CreatureList` and `CompanionList`

Role: wild shape, companions, familiars, sidekicks, and creature stat blocks.

Creature fields:

- `name`, `nameAlt`
- `source`
- `size`
- `type`
- `alignment`
- `ac`
- `hp`
- `hd`
- `speed`
- `scores`
- `saves`
- `skills`
- `senses`
- `passivePerception`
- `languages`
- `challengeRating`
- `proficiencyBonus`
- `attacksAction`
- `attacks`
- `traits`, `actions`
- `wildshapeString`
- `features`

Source difference: 2024 creature syntax adds explicit `resistances`, `immunities`, `vulnerabilities`, `formatSpellDescription`, and `useSpellDescription` fields compared with the 2014 syntax.

Companion fields:

- `name`
- `nameOrigin`
- `nameMenu`
- `nameTooltip`
- `source`
- `includeCheck`
- `attributesAdd`
- `attributesChange`
- `notes`
- `features`
- `calcChanges`
- `eval`, `changeeval`
- `hp`
- `header`
- `action`

## Function and Engine Surface

The engine is concentrated in:

| File | Role |
|---|---|
| `_functions/Functions0.js` | foundational helpers, tooltip/string utilities, version helpers |
| `_functions/Functions1.js` | main sheet field mutations, equipment, features, race/background/class integration |
| `_functions/Functions2.js` | companions, wild shape, actions, attacks, skills, proficiencies |
| `_functions/Functions3.js` | magic items, weapon/magic item processing, later feature systems |
| `_functions/FunctionsImport.js` | import/export and migration logic |
| `_functions/FunctionsSpells.js` | spell list construction, psionics merge, spell sheets |
| `_functions/FunctionsResources.js` | resources and limited-use handling |
| `_functions/ClassSelection.js` | class/subclass selection UI and logic |
| `_functions/AbilityScores.js` | ability score UI/logic |

Function extraction recommendations:

- Keep declaration chunks for `function name(...)`.
- Add chunks for `var name = function (...)`.
- Add chunks for `name = function (...)`.
- Preserve JSDoc/comments immediately preceding the definition.
- Window large functions with signature headers, as current chunker design intends.
- Add metadata for `function_name`, `parameters`, `file`, `branch`, `edition`, `size_lines`, and `window_index`.

## Intent and Query Analysis Coverage

Current `QueryIntent` categories are:

- `how_to`
- `generate`
- `debug`
- `lookup`

That taxonomy is good. The symbol and object maps now cover the newly confirmed 2024 source registries, but a few natural-language aliases are still worth adding.

### `intent.py` coverage

Literal symbols now covered:

- `PsionicsList`
- `ToolsList`
- `WeaponMasteriesList`
- `DefaultEvalsList`

Consider adding user-facing support functions if lookup/debug queries often mention them:

- `AddMagicItem`
- `AddWeapon`
- `AddAction`
- `AddFeature`
- `AddToInv`
- `AddString`
- `AddTooltip`

Those are engine functions, not add-on declaration functions, so they should classify as `lookup` or `debug`, not necessarily as generation targets.

### `query_analysis.py` coverage

Code identifiers now covered:

- `PsionicsList`
- `ToolsList`
- `WeaponMasteriesList`
- `DefaultEvalsList`

Keyword mapping status:

| Keywords | Object/function target | Status |
|---|---|---|
| `psionic`, `psionics`, `psionic discipline`, `psionic disciplines` | `PsionicsList` | Covered |
| `mystic`, bare `discipline`, bare `talent` | `PsionicsList` | Still recommended |
| `tool`, `tools`, `artisan tools`, `tool proficiency` | `ToolsList` | Covered through `tool`/`tools` |
| `weapon mastery`, `weapon masteries`, `mastery property` | `WeaponMasteriesList` | Covered |
| `default eval`, `default evals`, `default calculation`, `default calculations` | `DefaultEvalsList` | Covered |
| `packs` | `PacksList` | Still recommended |
| `ammunition` and `ammo` plural variants | `AmmoList` | Mostly covered |
| `armor`, `armour`, `shield`, `shields` | `ArmourList` | Partly covered |
| `origin feat`, `origin feats` | `FeatsList` plus edition hint `2024` if context permits | Still recommended |
| `species` | `RaceList` | Covered |

Do not map bare `source` to `SourceList`; the current collision concern is valid. `source book` and literal `SourceList` are safer.

## Retrieval and Chunking Strategy

Recommended chunk order and priority:

| Source | Chunking granularity | Tier | Priority |
|---|---|---|---|
| Syntax templates | Attribute block, header block, object-key block | authoritative | Highest |
| Engine functions | Function definition windows | authoritative | High |
| Imports published WotC | Object/call per registry entry | official example | High |
| Imports 2024 WotC | Object/call per registry entry | official example | High |
| Imports UA/Plane Shift | Object/call per registry entry | official example, lower trust | Medium |
| Built-in variables | Object per built-in entry | official example | Medium |
| Community additional content | Object/call per entry, nested feature chunks | community example | Medium |
| WIP excluded items | Object per entry, low priority or skip | low-trust official | Low |
| Generated bundles/minified | Do not index | duplicate | Skip |

### Nested chunks to add

Object-level chunks are not enough for classes, subclasses, races, feats, and magic items. Add nested chunks for:

- `features` entries
- `choices`
- `extrachoices`
- `weaponOptions`
- `armorOptions`
- `ammoOptions`
- `spellcastingBonus`
- `spellcastingExtra`
- `calcChanges`
- `toNotesPage`
- `eval`, `removeeval`, `changeeval`
- creature `traits`, `actions`, and `attacks`

Each nested chunk should carry parent metadata:

```json
{
  "chunk_type": "nested_feature",
  "object_type": "ClassList",
  "object_key": "fighter",
  "nested_path": "features.classfeature3",
  "display_name": "Martial Archetype",
  "minlevel": 3,
  "source_book": "P",
  "source_page": 72
}
```

## Agent Query Playbook

This section is written for future agents that need to rediscover the source truth without trusting this document blindly. Prefer `rg` for fast source discovery, then use a structured parser or brace-aware extraction for the final chunking pass. Regex search is excellent for finding candidate lines; it is not sufficient by itself for extracting complete JavaScript objects.

### Source roots to query

| Root | Purpose | Default edition metadata | Trust tier |
|---|---|---|---|
| `data/mpmb_source` | 2014 MPMB engine, built-ins, syntax templates, community examples | `2014` | authoritative for engine/syntax, mixed for examples |
| `data/mpmb_source_2024` | 2024 MPMB engine, built-ins, syntax templates, community examples | `2024` | authoritative for engine/syntax, mixed for examples |
| `data/imports_source/WotC material` | 2014 WotC published, UA, Plane Shift, generated bundles | `2014` for individual files | official examples, except generated duplicates |
| `data/imports_source/WotC 2024` | 2024 PHB/MM and not-reprinted legacy content | `2024` for `pub_*.js`, mixed for `not-reprinted_*.js` | official examples |
| `data/imports_source/Homebrew` | small homebrew example corpus | `unknown` | community example |

### Fast provenance checks

Run these before trusting any count:

```powershell
git -C data\mpmb_source log -1 --format="%H%n%cs%n%s%n%D"
git -C data\mpmb_source_2024 log -1 --format="%H%n%cs%n%s%n%D"
git -C data\imports_source log -1 --format="%H%n%cs%n%s%n%D"
git -C data\mpmb_source_2024 remote -v
git -C data\mpmb_source_2024 branch -a -vv
```

Expected 2024 source state for this analysis:

- `data/mpmb_source_2024` branch: `main`
- remote: `https://github.com/morepurplemorebetter/2024_MPMBs-Character-Record-Sheet.git`
- commit: `4537ae1`
- tag: `v24.0.7`

### Fast file inventory queries

```powershell
rg --files data\mpmb_source -g "*.js"
rg --files data\mpmb_source_2024 -g "*.js"
rg --files data\imports_source -g "*.js"
rg --files data\imports_source -g "*.js" -g "!all_WotC_*.js" -g "!*.min.js" -g "!gulpfile.js"
```

Use these path buckets when deriving `source_tier`:

```powershell
rg --files data\mpmb_source\_functions
rg --files data\mpmb_source\_variables
rg --files "data\mpmb_source\additional content syntax"
rg --files "data\mpmb_source\additional content"
rg --files data\mpmb_source_2024\_functions
rg --files data\mpmb_source_2024\_variables
rg --files "data\mpmb_source_2024\additional content syntax"
rg --files "data\imports_source\WotC 2024"
```

### Registry discovery queries

Start broad to discover all registry families:

```powershell
rg -n "^\s*[A-Za-z_$][\w$]*\s*\[" data\mpmb_source data\mpmb_source_2024 data\imports_source -g "*.js" -g "!all_WotC_*.js" -g "!*.min.js"
rg -n "^\s*[A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*\s*=\s*\{" data\mpmb_source data\mpmb_source_2024 data\imports_source -g "*.js" -g "!all_WotC_*.js" -g "!*.min.js"
```

Then narrow by object type:

```powershell
rg -n "^\s*SpellsList\s*\[" data\mpmb_source data\mpmb_source_2024 data\imports_source -g "*.js" -g "!all_WotC_*.js" -g "!*.min.js"
rg -n "^\s*FeatsList\s*\[" data\mpmb_source data\mpmb_source_2024 data\imports_source -g "*.js" -g "!all_WotC_*.js" -g "!*.min.js"
rg -n "^\s*PsionicsList\s*\[" data\imports_source -g "*.js" -g "!all_WotC_*.js" -g "!*.min.js"
rg -n "^\s*WeaponMasteriesList\s*\[" data\mpmb_source_2024 data\imports_source -g "*.js"
rg -n "^\s*DefaultEvalsList\s*\[" data\mpmb_source_2024 data\imports_source -g "*.js"
```

For exact object keys, use the registry and likely key text:

```powershell
rg -n "SpellsList\s*\[\s*[`\"']crusader" data\imports_source data\mpmb_source_2024 -g "*.js"
rg -n "MagicItemsList\s*\[\s*[`\"']absorbing tattoo" data\imports_source -g "*.js"
rg -n "WeaponMasteriesList\s*\[" data\mpmb_source_2024 -g "*.js"
```

Important parser warning: many valid keys contain apostrophes. The current non-backreference pattern misses keys such as `crusader's mantle`, `potion of dragon's majesty`, and `warsmith's armor`. Use a matching quote backreference in parser code:

```python
r'''^\s*(\w+)\s*\[\s*(["'])(.*?)\2\s*\]\s*=\s*\{'''
```

### `Add*` call discovery queries

Mapped declaration-style calls:

```powershell
rg -n "^\s*Add(SubClass|FeatureChoice|BackgroundVariant|RacialVariant|WarlockInvocation|FightingStyle|WarlockPactBoon)\s*\(" data\mpmb_source data\mpmb_source_2024 data\imports_source -g "*.js" -g "!all_WotC_*.js" -g "!*.min.js"
```

All `Add*` calls, including engine helpers that may matter for lookup/debug answers:

```powershell
rg -n "^\s*Add[A-Za-z_$][\w$]*\s*\(" data\mpmb_source data\mpmb_source_2024 data\imports_source -g "*.js" -g "!all_WotC_*.js" -g "!*.min.js"
```

High-count non-declaration helpers observed in the scan include `AddTooltip`, `AddString`, `AddToInv`, `AddMagicItem`, `AddToModFld`, `AddToNotes`, `AddAction`, `AddFeature`, `AddFeat`, and `AddWeapon`. These should be indexed as engine/API surface when they occur in `_functions`, but they should not be treated as content declaration families like `AddSubClass`.

### Syntax-template queries

Syntax templates are the strongest source for answering "how do I write this?" questions:

```powershell
rg -n "//\s*(REQUIRED|OPTIONAL)\s*//" "data\mpmb_source\additional content syntax" "data\mpmb_source_2024\additional content syntax"
rg -n "RequiredSheetVersion|iFileName|object name" "data\mpmb_source\additional content syntax" "data\mpmb_source_2024\additional content syntax"
rg -n "reqLoS|choicesNotInMenu|descriptionClassFeature|WeaponMasteriesList|DefaultEvalsList|mastery" "data\mpmb_source_2024\additional content syntax"
```

The current syntax extractor only captures attribute lines followed by required/optional comments. It does not capture header sections, `RequiredSheetVersion`, `iFileName`, or object-name documentation unless those are represented as attributes. A near-complete syntax index should create separate chunks for:

- `template_header`
- `template_required_version`
- `template_i_file_name`
- `template_object_key`
- `template_attribute`
- `template_examples`

### Engine-function queries

Use these to locate implementation truth behind imports and automation:

```powershell
rg -n "^function\s+[A-Za-z_$][\w$]*\s*\(" data\mpmb_source\_functions data\mpmb_source_2024\_functions
rg -n "^\s*(var|let|const)\s+[A-Za-z_$][\w$]*\s*=\s*function\s*\(" data\mpmb_source\_functions data\mpmb_source_2024\_functions
rg -n "^\s*[A-Za-z_$][\w$]*\s*=\s*function\s*\(" data\mpmb_source\_functions data\mpmb_source_2024\_functions
```

The broad function-like scan found:

| Source | Declaration occurrences | Declaration unique | Function-like occurrences | Function-like unique |
|---|---:|---:|---:|---:|
| `mpmb_source` | 590 | 586 | 747 | 702 |
| `mpmb_source_2024` | 597 | 594 | 769 | 725 |

Current function-definition extraction only captures `function name(...)`. To align index coverage with `mpmb_function`, add extraction for assignment-style functions too.

### Source-key and edition queries

Source keys are essential for grounding answers to books and pages:

```powershell
rg -n "^\s*SourceList\s*\[" data\mpmb_source data\mpmb_source_2024 data\imports_source -g "*.js" -g "!all_WotC_*.js" -g "!*.min.js"
rg -n "source\s*:\s*\[" data\mpmb_source data\mpmb_source_2024 data\imports_source -g "*.js" -g "!all_WotC_*.js" -g "!*.min.js"
rg -n "RequiredSheetVersion\(" data\mpmb_source data\mpmb_source_2024 data\imports_source -g "*.js" -g "!all_WotC_*.js" -g "!*.min.js"
rg -n "\b(P24|M24|SRD24|reqLoS|mastery|origin)\b" data\mpmb_source_2024 data\imports_source -g "*.js"
```

Top source-key references in this scan:

| Key | References | Main meaning |
|---|---:|---|
| `SRD` | 1,449 | 2014 SRD/default source |
| `SRD24` | 949 | 2024 SRD/default source |
| `KCCC` | 1,082 | Kibbles Compendium community source |
| `T` | 511 | Tasha's Cauldron of Everything |
| `P` | 473 | 2014 Player's Handbook |
| `P24` | 189 | 2024 Player's Handbook |
| `M24` | 103 | 2024 Monster Manual; defined in `WotC 2024/pub_20250218_MM.js` |
| `UA:TMC` | 286 | UA Mystic Class, primary `PsionicsList` corpus |

Do not infer edition from `RequiredSheetVersion("14.0.5", "24.0.0")` alone. Both MPMB source repos use it as a compatibility gate. Stronger edition signals are root path, source key (`P24`, `M24`, `SRD24`), 2024-only fields (`reqLoS`, `mastery`), and 2024-only registries (`WeaponMasteriesList`, `DefaultEvalsList`).

## Extraction Pipeline For Near-Complete Qdrant Truth

Use multiple passes. Each pass should produce chunks with enough metadata to be filtered and cross-linked later.

| Pass | Extract | Chunk type | Notes |
|---|---|---|---|
| 0 | Git/root/file provenance | `source_manifest` | Store branch, commit, tag, root, path, line count, skip reason |
| 1 | Syntax template headers | `template_header` | Capture subject/effect/remarks/sheet blocks |
| 2 | Syntax object-key docs | `template_object_key` | Capture `SpellsList object name`, `WeaponMasteriesList object name`, etc. |
| 3 | Syntax attributes | `template_attribute` | Current extractor does this partially |
| 4 | Registry object literals | `object_literal` | Use whitespace-tolerant matching quote regex plus brace matcher |
| 5 | Dot object literals | `object_literal` | Capture `SomeRegistry.someKey = { ... }` forms |
| 6 | Function-valued registries | `function_valued_object` | Needed for 5 WotC magic items now |
| 7 | Mapped `Add*` declaration calls | `function_call` | `AddSubClass`, `AddFeatureChoice`, etc. |
| 8 | Engine functions | `function_definition` | Include declaration and assignment-style functions |
| 9 | Nested object surfaces | `nested_feature`, `nested_choice`, `nested_hook` | Essential for class/race/feat/magic item precision |
| 10 | Source keys | `source_definition`, `source_reference` | Normalize `source_book`, `source_page`, `source_group` |
| 11 | Cross-reference edges | `relationship_edge` | Link subclass to class, spellcastingBonus to spell, mastery to weapon mastery |

Recommended object-assignment parser seeds:

```python
BRACKET_OBJECT = r'''^\s*(\w+)\s*\[\s*(["'])(.*?)\2\s*\]\s*=\s*\{'''
DOT_OBJECT = r'''^\s*(\w+)\.([A-Za-z_$][\w$]*)\s*=\s*\{'''
FUNCTION_OBJECT = r'''^\s*(\w+)\s*\[\s*(["'])(.*?)\2\s*\]\s*=\s*function\s*\('''
ADD_CALL = r'''^\s*(Add[A-Za-z_$][\w$]*)\s*\('''
```

After matching a start line, use a brace/paren matcher that skips strings, comments, and regex literals. Do not stop at the next `};` with plain string search; nested `calcChanges`, `eval`, and `choices` blocks can contain braces and functions.

### Nested extraction targets

The following fields are common enough to deserve dedicated nested chunks or at least typed metadata:

| Field/hook | Total occurrences | 2014 source | 2024 source | Imports |
|---|---:|---:|---:|---:|
| `descriptionFull` | 3,543 | 887 | 958 | 1,698 |
| `action` | 2,362 | 584 | 588 | 1,190 |
| `usages` | 2,082 | 497 | 514 | 1,071 |
| `recovery` | 2,082 | 498 | 515 | 1,069 |
| `spellcastingBonus` | 1,583 | 402 | 422 | 759 |
| `scores` | 1,119 | 249 | 249 | 621 |
| `prereqeval` | 1,094 | 308 | 302 | 484 |
| `features` | 972 | 218 | 233 | 521 |
| `calcChanges` | 933 | 234 | 247 | 452 |
| `languageProfs` | 566 | 116 | 93 | 357 |
| `dmgres` | 534 | 149 | 162 | 223 |
| `eval` | 486 | 173 | 173 | 140 |
| `choices` | 473 | 110 | 121 | 242 |
| `removeeval` | 400 | 141 | 138 | 121 |
| `weaponOptions` | 396 | 81 | 81 | 234 |
| `vision` | 382 | 84 | 85 | 213 |
| `toolProfs` | 330 | 57 | 59 | 214 |
| `usagescalc` | 328 | 57 | 71 | 200 |
| `spellcastingExtra` | 203 | 50 | 48 | 105 |
| `toNotesPage` | 204 | 28 | 31 | 145 |
| `choicesNotInMenu` | 161 | 36 | 47 | 78 |
| `reqLoS` | 109 | 0 | 86 | 23 |
| `mastery` | 38 | 0 | 38 | 0 |

2024-specific nested signals:

- `reqLoS` appears in 2024 spells.
- `mastery` appears in 2024 weapon definitions.
- `descriptionClassFeature`, `choicesNotInMenu`, and `type: "origin"` matter for 2024 feats.
- `featsAdd` matters for 2024 species/background-origin workflows.
- `DefaultEvalsList` entries should be linked to `calcChanges` semantics.

## Qdrant Retrieval Design Guide

The index should support both semantic questions and exact source lookup. A single vector query is not enough for MPMB because users often mention exact code identifiers, book keys, object keys, or feature names.

### Core metadata fields

Every chunk should carry:

- `source_root`: `mpmb_source`, `mpmb_source_2024`, or `imports_source`
- `source_repo`: `mpmb`, `imports`, or `user`
- `source_file`
- `source_tier`
- `edition`: `2014`, `2024`, `both`, `auto`, `unknown`
- `branch`
- `commit`
- `chunk_type`
- `object_type`
- `object_key`
- `display_name`
- `category`
- `start_line`, `end_line`
- `required_sheet_version`
- `i_file_name`
- `source_book`, `source_page`
- `source_group`
- `parent_object_type`, `parent_object_key`
- `nested_path`
- `hook_type`
- `confidence_flags`: `generated_bundle`, `minified`, `wip`, `legacy_syntax`, `not_reprinted`

### Retrieval profiles by intent

| Intent | First-pass filters | Ranking preference |
|---|---|---|
| `how_to` | syntax templates, engine docs, exact object type if detected | syntax attribute/object-key chunks first, then official examples |
| `generate` | syntax templates plus official examples for same object type/edition | syntax constraints first, examples second, community examples third |
| `debug` | exact identifiers, engine functions, import examples, user uploads | exact symbol/BM25 matches first, then engine behavior |
| `lookup` | exact symbol/object key/source key | exact object/function/source chunks first |

### Multi-query recipes

For "How do I add a 2024 spell with line of sight?":

1. Filter `edition=2024`, `object_type=SpellsList`.
2. Search syntax chunks for `reqLoS`, `range`, `description`, `descriptionFull`.
3. Search official examples in `imports_source/WotC 2024/pub_20240917_PHB.js`.
4. Search engine `_functions/FunctionsSpells.js` for `reqLoS`.

For "How do I add artisan tools?":

1. Filter `object_type=ToolsList` and syntax root.
2. Search `adventuring gear - tool (ToolsList).js`.
3. Search `GearList` too if the wording is "equipment" or "inventory".
4. Include `toolProfs` examples from classes/races/backgrounds if the user means proficiency, not a physical tool item.

For "How do I add weapon mastery?":

1. Filter `edition=2024`.
2. Search `WeaponMasteriesList` syntax and object chunks.
3. Search `WeaponsList` for `mastery`.
4. Search 2024 engine/built-ins for `Mastery Property` and `WeaponMasteriesList`.

For "How do I add psionic disciplines?":

1. Search `PsionicsList` in imports first, especially `ua_20170313_The-Mystic-Class.js`.
2. Search `_functions/FunctionsSpells.js` for how psionics merge into spell handling.
3. Retrieve `SpellsList` syntax as adjacent structure, but keep `object_type=PsionicsList` in metadata.

For "Why is a named item/spell missing?":

1. Exact BM25 search the object key with matching apostrophes and normalized lowercase.
2. Search function-valued registries if the object type is `MagicItemsList`.
3. Search generated bundles only for debugging source-generation problems, not normal retrieval.

### Coverage validation targets

After parser changes, rerun a scan and compare against these current baselines:

| Measure | Baseline |
|---|---:|
| Selected source files | 424 |
| Current mapped object literals | 3,400 |
| Robust mapped object literals target | 3,828 |
| Current mapped `Add*` calls | 743 |
| Robust mapped `Add*` calls target | 879 |
| Function-valued registry entries | 5 |
| Syntax attribute chunks | 560 |
| 2024-only source files vs 2014 source | 4 |

If robust counts drop unexpectedly, check:

- whether generated bundles were accidentally included or excluded differently
- whether `data/mpmb_source_2024` is still on `main`
- whether the parser still allows leading whitespace
- whether the parser uses quote backreferences
- whether dot assignments are included
- whether function-valued registries are counted separately

### Recommended metadata schema

```json
{
  "source_repo": "imports",
  "source_root": "./data/imports_source/",
  "source_file": "WotC 2024/pub_20240917_PHB.js",
  "source_tier": "official_example",
  "edition": "2024",
  "branch": "master",
  "commit": "5c978b0",
  "chunk_type": "object_literal",
  "object_type": "SpellsList",
  "object_key": "crusader's mantle",
  "display_name": "Crusader's Mantle",
  "category": "spell",
  "source_book": "P24",
  "source_page": 250,
  "required_sheet_version": "24.0.6-beta",
  "i_file_name": "pub_20240917_PHB.js",
  "metadata": {
    "spell_level": 3,
    "spell_school": "Evoc",
    "classes": ["paladin"],
    "time": "Act",
    "range": "Self",
    "components": "V",
    "duration": "Conc, 1 min",
    "requires_line_of_sight": false
  }
}
```

## Skip and De-Dupe Rules

Always skip:

- `.git/**`
- `node_modules/**`
- `imports_source/WotC material/all_WotC_*.js`
- `imports_source/WotC material/*.min.js`
- `imports_source/package*.json`
- `imports_source/gulpfile.js`

Usually skip or low-priority index:

- `imports_source/WotC material/wip_*.js`, because the file explicitly says the items were excluded from first-round transcriptions.
- `additional content syntax/v12.999 syntax, if v13 not available/*.js`, unless answering legacy sheet questions.

Do not index both aggregate bundles and individual files. The bundles are generated from the individual files and will duplicate most examples.

## Recommended Implementation Actions

Highest priority:

1. Add metadata filters and retrieval tests for `PsionicsList`.
2. Add retrieval tests for `ToolsList`, `WeaponMasteriesList`, and `DefaultEvalsList`.
3. Add `ROOT_IMPORTS = "./data/imports_source/"` to source tool roots.
4. Change object and Add-call regexes to allow leading whitespace.
5. Change object-key parsing to use matching quote backreferences.
6. Add extraction for function-valued registry assignments.

Next priority:

1. Add syntax chunks for `iFileName`, `RequiredSheetVersion`, and object-name comments.
2. Add nested feature/choice chunks for classes, subclasses, races, feats, magic items, creatures, and companions.
3. Expand engine function extraction beyond `function name(...)`.
4. Add 2024-specific metadata for `reqLoS`, `type: "origin"`, `descriptionFull` arrays, and source keys like `P24`/`M24`.
5. Keep source acquisition pinned to `morepurplemorebetter/2024_MPMBs-Character-Record-Sheet` on `main` for the 2024 source tree.

Useful test cases after fixes:

- Query: "How do I add psionic disciplines?" should route to `PsionicsList`.
- Query: "How do I add artisan tools?" should route to `ToolsList`.
- Query: "2024 spell with line of sight" should surface `reqLoS` examples from `pub_20240917_PHB.js`.
- Query: "Why is crusader's mantle missing?" should find `SpellsList["crusader's mantle"]`.
- Query: "How does absorbing tattoo work?" should find the function-valued `MagicItemsList` entry.
- Tool call: `mpmb_read` should be able to read `imports_source/WotC 2024/pub_20240917_PHB.js` after `ROOT_IMPORTS` is added.
