# MPMB Source Material Analysis

## Repository Summary

| Repository                | Content                                       | Files         | Lines   |
| ------------------------- | --------------------------------------------- | ------------- | ------- |
| **MPMB Main (master)**    | Core engine + syntax docs (2014 edition)      | 143 .js files | ~75,000 |
| **MPMB Main (dnd2024)**   | Core engine + syntax docs (2024 edition)      | 143 .js files | ~75,000 |
| **safety-orange Imports** | All content definitions (spells, races, etc.) | 139 .js files | ~99,000 |

### Imports Repo Structure

```txt
imports_source/
├── WotC material/          # 2014 content (135 files)
│   ├── pub_*.js            # Published books (61 files) ← PRIMARY
│   ├── ua_*.js             # Unearthed Arcana (67 files)
│   ├── ps_*.js             # Plane Shift content (6 files)
│   ├── all_WotC_*.js       # Concatenated bundles (SKIP)
│   └── *.min.js            # Minified bundles (SKIP)
├── WotC 2024/              # 2024 content (4 files)
│   ├── pub_20240917_PHB.js # 2024 PHB (215K, main content)
│   ├── pub_20250218_MM.js  # 2024 MM (3.3K, minimal)
│   ├── not-reprinted_*.js  # 2014 content NOT in 2024 (2 files)
│   └── (growing as books release)
└── Homebrew/               # Example homebrew (1 file)
```

### MPMB Main Repo Structure (same for both branches)

```txt
mpmb_source/
├── _functions/             # Core engine (13 files, 41K lines)
│   ├── Functions0-3.js     # Main function library
│   ├── FunctionsImport.js  # Import/Add* functions (149K)
│   ├── FunctionsSpells.js  # Spell handling (252K)
│   └── ...
├── _variables/             # Built-in content (13 files, 25K lines)
│   ├── ListsSpells.js      # SRD spells
│   ├── ListsClasses.js     # SRD classes
│   └── ...
├── additional content syntax/  # DOCUMENTATION (15 files, 9.3K lines)
│   ├── _common attributes.js           # 3029 lines - shared attributes
│   ├── _common spell list object.js    # 157 lines
│   ├── spell (SpellsList).js           # Spell syntax
│   ├── feat (FeatsList).js             # Feat syntax
│   ├── magic item (MagicItemsList).js  # Magic item syntax
│   └── ... (one per object type)
└── additional content/     # Example content scripts
```

---

## Content Patterns (What Users Actually Write)

### Pattern 1: Object Assignment (Most Common — ~85% of content)

```javascript
ObjectType["lowercase key"] = {
	name: "Display Name",
	source: [["P", 42]],
	// ... type-specific attributes
};
```

**Object types found:**

| Object Type             | 2014 Count | 2024 Count | Description           |
| ----------------------- | ---------- | ---------- | --------------------- |
| `MagicItemsList`        | 586        | 0          | Magic items           |
| `SpellsList`            | 205        | 53         | Spells                |
| `RaceList`              | 125        | 1          | Races/species         |
| `BackgroundFeatureList` | 115        | 12         | Background features   |
| `FeatsList`             | 106        | 58         | Feats                 |
| `CreatureList`          | 87         | 0          | Creatures/wild shapes |
| `BackgroundList`        | 77         | 12         | Backgrounds           |
| `WeaponsList`           | 39         | 5          | Weapons               |
| `SourceList`            | 27         | 1          | Source books          |
| `AmmoList`              | 7          | 0          | Ammunition            |
| `GearList`              | 6          | 0          | Adventuring gear      |
| `ClassList`             | 6          | 0          | Classes               |
| `CompanionList`         | 1          | 0          | Companion templates   |

### Pattern 2: Function Calls (~15% of content)

```javascript
AddSubClass("parent class", "subclass key", {
    regExpSearch : /regex/i,
    subname : "Subclass Name",
    source : [["P", 50]],
    features : { ... }
});
```

**Function types found:**

| Function               | 2014 Count | 2024 Count | Description                                  |
| ---------------------- | ---------- | ---------- | -------------------------------------------- |
| `AddSubClass`          | 103        | 2          | Subclass definitions                         |
| `AddFeatureChoice`     | 47         | 0          | Feature options (Eldritch Invocations, etc.) |
| `AddBackgroundVariant` | 45         | 0          | Background variants                          |
| `AddRacialVariant`     | 26         | 0          | Racial variants                              |
| `AddWarlockInvocation` | 22         | 0          | Warlock invocations                          |
| `AddFightingStyle`     | 6          | 0          | Fighting styles                              |
| `AddWarlockPactBoon`   | 1          | 0          | Pact boons                                   |

### Pattern 3: File Headers (Every file)

```javascript
var iFileName = "pub_20140818_PHB.js";
RequiredSheetVersion("14.0.5-beta");
// Description comment
```

---

## Edition Differences

### What Changed Between 2014 and 2024

1. **Source keys**: `"P"` (2014 PHB) vs `"P24"` (2024 PHB)
2. **RequiredSheetVersion**: `"14.0.5-beta"` vs `"24.0.5-beta"`
3. **Spell syntax**: 2024 adds `reqLoS` (requires line of sight), `descriptionFull` can be an array of strings
4. **Feat syntax**: 2024 adds `type: "origin"` for origin feats
5. **Time notation**: 2014 uses `"1 a"` (1 action), 2024 uses `"Act"` (Action)
6. **Syntax templates**: Nearly identical structure, minor attribute additions/changes per edition
7. **Engine functions**: ~33 files changed between branches — same API, different implementations

### Edition Detection Strategy

| Signal                                   | Edition                                     |
| ---------------------------------------- | ------------------------------------------- |
| File in `WotC material/`                 | 2014                                        |
| File in `WotC 2024/`                     | 2024                                        |
| `RequiredSheetVersion("14.x")`           | 2014                                        |
| `RequiredSheetVersion("24.x")`           | 2024                                        |
| Source key contains `24` (e.g., `"P24"`) | 2024                                        |
| Branch = master                          | 2014                                        |
| Branch = dnd2024                         | 2024                                        |
| `_functions/` or `_variables/`           | Tag per branch                              |
| Syntax templates                         | Tag per branch                              |
| User-provided content                    | Detect from RequiredSheetVersion or default |

---

## Chunking Strategy

### What to Chunk

| Source             | Chunk Strategy                     | Edition Tag | Priority             |
| ------------------ | ---------------------------------- | ----------- | -------------------- |
| Syntax templates   | One chunk per documented attribute | Per branch  | HIGH (documentation) |
| Imports `pub_*.js` | One chunk per object/function call | Per folder  | HIGH (examples)      |
| Imports `ua_*.js`  | One chunk per object/function call | 2014        | MEDIUM (playtest)    |
| `_functions/*.js`  | One chunk per function definition  | Per branch  | MEDIUM (engine)      |
| `_variables/*.js`  | One chunk per object assignment    | Per branch  | LOW (SRD defaults)   |
| Imports `all_*.js` | SKIP (duplicate)                   | —           | —                    |
| Imports `*.min.js` | SKIP (unreadable)                  | —           | —                    |

### What to Skip

- `all_WotC_published.js` — concatenation of individual files (would duplicate everything)
- `all_WotC_pub+UA.js` — same
- `all_WotC_unearthed_arcana.js` — same
- `*.min.js` — minified, unreadable
- `.git/` directories
- `gulpfile.js`, `package.json` etc. from Imports repo

### Chunk Metadata Schema

```json
{
	"content": "SpellsList[\"fireball\"] = { ... };",
	"source_file": "WotC material/pub_20140818_PHB.js",
	"source_repo": "imports",
	"chunk_index": 42,
	"start_line": 4500,
	"end_line": 4520,
	"chunk_type": "object_literal",
	"edition": "2014",
	"metadata": {
		"object_type": "SpellsList",
		"object_key": "fireball",
		"display_name": "Fireball",
		"source_book": "P",
		"source_page": 241,
		"category": "spell",
		"level": 3,
		"school": "Evoc"
	}
}
```

---

## Estimated Chunk Counts

| Source                       | Est. Chunks | Notes                                 |
| ---------------------------- | ----------- | ------------------------------------- |
| 2014 Imports (pub + ua + ps) | ~1,900      | Object assignments + Add\* calls      |
| 2024 Imports                 | ~190        | Growing as books release              |
| Syntax templates (2014)      | ~300        | Documented attributes                 |
| Syntax templates (2024)      | ~300        | Documented attributes                 |
| Engine functions (2014)      | ~400        | Top-level function defs               |
| Engine functions (2024)      | ~400        | Same functions, different impl        |
| Variables/Lists (2014)       | ~300        | SRD built-in content                  |
| **Total**                    | **~3,800**  | Manageable for any embedding provider |

At 384 dimensions (bge-small) × 4 bytes × 3,800 chunks ≈ **5.8 MB** of vectors. Trivial for Qdrant.
