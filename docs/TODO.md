# TODO

## Current baseline

- [x] Clone the main MPMB source repos (2014 + 2024)
- [x] Clone the Imports repo
- [x] Chunk the corpus into semantic units
- [x] Produce JSON chunk outputs for later embedding + Qdrant indexing

## Core product direction

- [ ] Treat this project as an **example-first, authoritative-grounded** copilot
- [ ] Keep authoritative material as the source of truth for what is valid
- [ ] Keep examples as the primary source for how users actually implement content
- [ ] Optimize for real user questions like:
    - “How do I build my own subclass?”
    - “How do I get started writing a race?”
    - “How do I fix why this import is not loading?”

---

## 1) Immediate next work

- [ ] Finalize a single Qdrant payload schema for all indexed chunks
- [ ] Reindex the current chunk outputs with richer metadata and source tiers
- [ ] Build the first retriever with metadata filters + vector search
- [ ] Add a lexical layer for exact symbols like `AddSubClass`, `SourceList`, and `RequiredSheetVersion`
- [ ] Add intent-based query routing
- [ ] Split retrieval into authoritative vs example buckets
- [ ] Add retrieval/result caching
- [ ] Ingest the MPMB community Google Sheet as a discovery layer for community examples
- [ ] Build eval prompts focused on beginner how-to, generation, lookup, and debugging

---

## 2) Retrieval philosophy

### Main rule

- [ ] Most answers should combine:
    - 1–3 authoritative chunks for correctness
    - 2–5 example chunks for implementation guidance

### Why community ingestion matters

- [ ] “What is valid?” should come from syntax templates, engine behavior, and official docs
- [ ] “How do I implement X?” should come from examples, especially minimal working examples
- [ ] Do not let examples override authoritative requirements
- [ ] Do not let authoritative material crowd out practical examples for beginner queries

### Default answer composition

- [ ] Beginner how-to:
    - 1 syntax/authoritative chunk
    - 1 helper/engine chunk if needed
    - 2–4 examples
- [ ] Debugging:
    - engine/functions first
    - exact symbol matches
    - syntax template for required structure
    - examples only as supporting context
- [ ] Exact API lookup:
    - lexical + authoritative first
- [ ] “Show me examples”:
    - examples first
    - one authoritative guardrail chunk

---

## 3) Payload schema and corpus metadata

### Required payload fields

- [ ] Add `doc_id`
- [ ] Add `edition`
- [ ] Add `source_repo`
- [ ] Add `source_kind`
- [ ] Add `source_tier`
- [ ] Add `chunk_type`
- [ ] Add `object_type`
- [ ] Add `object_key`
- [ ] Add `source_file`
- [ ] Add `start_line`
- [ ] Add `end_line`
- [ ] Add `url` when available
- [ ] Add `author` when available
- [ ] Add `sheet_tab` when content comes from community discovery
- [ ] Add `license_or_access`
- [ ] Add `fetch_status`
- [ ] Add `parse_status`
- [ ] Add `index_version`
- [ ] Add `corpus_version`
- [ ] Add `ingest_batch_id`

### Source kinds

- [ ] Standardize `source_kind` values:
    - `syntax_template`
    - `engine_function`
    - `built_in_variable`
    - `official_import`
    - `official_example`
    - `community_registry_entry`
    - `community_script`
    - `adobe_doc`
    - `user_script`

### Source tiers

- [ ] Standardize `source_tier` values:
    - `authoritative`
    - `official_example`
    - `community_example`
    - `metadata_only`
    - `user_content`

### Qdrant filter fields

- [ ] Add payload indexes for:
    - `edition`
    - `source_kind`
    - `source_tier`
    - `chunk_type`
    - `object_type`
    - `author`
    - `sheet_tab`

---

## 4) Retrieval strategy

### Hybrid retrieval

- [ ] Keep vector retrieval for semantic matching
- [ ] Add keyword/BM25 retrieval for exact symbols and field names
- [ ] Merge and rerank lexical + vector results
- [ ] Boost exact symbol hits when the query contains code identifiers

### Metadata-first narrowing

- [ ] Infer `edition` from the query when possible
- [ ] Infer likely `object_type` from phrases like:
    - subclass
    - class
    - race
    - feat
    - spell
    - background
    - magic item
- [ ] Infer likely `intent`
- [ ] Use metadata filters before broad vector search when the query is structured

### Parent/neighbor retrieval

- [ ] Retrieve the atomic chunk first
- [ ] Optionally pull file-level or nearby context when helpful
- [ ] Preserve file header context like `RequiredSheetVersion(...)` when generation requires it

---

## 5) Query routing

### First-pass intents

- [ ] Add a rule-based classifier for:
    - `how_to_start`
    - `generate_code`
    - `modify_existing_code`
    - `debug_code`
    - `find_symbol`
    - `find_examples`
    - `edition_compare`
    - `authoritative_explain`
    - `community_discovery`

### Retrieval profiles

- [ ] `authoritative_explain`
    - syntax templates first
    - engine functions next
    - Adobe docs next
    - examples only as support

- [ ] `how_to_start`
    - one authoritative guardrail chunk
    - one simple official example
    - one richer official or community example
    - helper functions only if needed

- [ ] `generate_code`
    - template + examples
    - minimal engine context
    - strict edition filtering

- [ ] `debug_code`
    - engine and exact symbols first
    - syntax requirements next
    - examples only if they resemble the failing pattern

- [ ] `find_examples`
    - examples first
    - group by simple vs advanced
    - prefer public and fetchable examples

- [ ] `community_discovery`
    - sheet metadata first
    - show provenance, trust, and fetchability
    - do not pretend metadata-only entries are indexed code

---

## 6) Authoritative vs examples

### Authoritative sources

- [ ] Treat these as the source of truth:
    - syntax templates
    - engine functions / built-in behavior
    - official Acrobat JavaScript docs
    - official imports and official MPMB-maintained content

### Example-heavy sources

- [ ] Treat these as implementation guidance:
    - official import files
    - additional content examples
    - community scripts
    - user scripts

### Example selection quality

- [ ] Rank examples by:
    - simplest working example
    - edition match
    - object type match
    - public availability
    - provenance clarity
    - popularity / recurrence if later measurable

### Starter packs

- [ ] Build starter packs for:
    - subclass
    - race
    - feat
    - spell
    - class
    - background
    - source entry

- [ ] Each starter pack should include:
    - one syntax chunk
    - one minimal official example
    - one richer official or community example
    - one helper/function chunk if needed

---

## 7) Community sheet ingestion

### Why this matters

- [ ] The community sheet should become the discovery hub for examples beyond the official repos
- [ ] Use it to find public 1st-party and 3rd-party scripts, not just as a document to quote
- [ ] Preserve provenance, author, and source tab so users can inspect where examples came from

### Tab-aware ingestion plan

- [ ] Capture and preserve the sheet tabs as source metadata:
    - `5e SRD`
    - `5e WotC (non-SRD)`
    - `2024 WotC (5.5e)`
    - `Other WotC`
    - `3rd Party`
    - `DMsGuild`
    - `Homebrew`
    - `D&D Wiki`
    - `Unpublished`

### Row normalization

- [ ] Export or scrape the sheet into normalized JSON
- [ ] Capture per-row metadata:
    - `sheet_tab`
    - `row_id`
    - `package_name`
    - `script_name`
    - `author`
    - `source_label`
    - `edition`
    - `repo_url`
    - `script_url`
    - `notes`
    - `last_seen_at`

### Registry model

- [ ] Create a `community_sources` registry
- [ ] Track:
    - source URL
    - raw script URL
    - author
    - category
    - trust tier
    - access tier
    - fetch status
    - parse status
    - index status

### Access and trust policy

- [ ] `5e WotC (non-SRD)` and `2024 WotC (5.5e)`:
    - likely official/example-weighted
- [ ] `Other WotC`:
    - official-ish but may be scattered
- [ ] `3rd Party` and `Homebrew`:
    - strong example candidates
- [ ] `DMsGuild`:
    - likely metadata-only unless access/licensing is clear
- [ ] `D&D Wiki`:
    - low-trust community example tier
- [ ] `Unpublished`:
    - metadata/discovery only unless explicit public script access exists

### Ingestion policy

- [ ] Ingest metadata for all visible public entries
- [ ] Fetch and chunk full scripts only when:
    - the script is publicly accessible
    - the URL is stable
    - provenance is preserved
    - licensing/access is acceptable
- [ ] If a script is discoverable but not fetchable:
    - keep it in discovery results
    - do not index fake or empty content

---

## 8) Caching

### Embedding cache

- [ ] Cache query embeddings by normalized query
- [ ] Include `edition` and `intent` in the cache key when relevant

### Retrieval-result cache

- [ ] Cache retrieval results by:
    - normalized query
    - edition
    - retrieval profile
    - index version

### Answer cache

- [ ] Cache high-frequency educational answers for:
    - “How do I make a subclass?”
    - “How do I start a race file?”
    - “What does `RequiredSheetVersion` do?”
    - “What changed in 2024?”
- [ ] Do not blindly cache user-specific generation or debugging responses

### Metrics

- [ ] Track:
    - embedding cache hit rate
    - retrieval cache hit rate
    - average retrieval latency
    - rerank latency
    - average context size
    - example-vs-authoritative mix by intent

---

## 9) Prompt and answer assembly

- [ ] Label retrieved context buckets:
    - authoritative rules
    - official examples
    - community examples
    - engine behavior notes
    - edition notes

- [ ] Make the assistant explain provenance naturally:
    - “The syntax template requires...”
    - “A minimal official example looks like...”
    - “A community example from the sheet shows...”

- [ ] Prevent example drift:
    - required structure comes from authoritative chunks
    - examples illustrate implementation patterns
    - generation must satisfy authoritative rules first

---

## 10) Evaluation

### Retrieval evals

- [ ] Build benchmark prompts for:
    - beginner how-to
    - exact symbol lookup
    - code generation
    - debugging
    - edition comparison
    - find-example tasks

- [ ] Score:
    - correct edition retrieved
    - correct object type retrieved
    - authoritative chunk present
    - useful example present
    - best chunk rank

### Answer evals

- [ ] Score:
    - correctness
    - implementation usefulness
    - beginner friendliness
    - edition correctness
    - debugging usefulness
    - provenance quality

### Comparison tests

- [ ] Compare:
    - authoritative only
    - authoritative + official examples
    - authoritative + official + community examples
    - official-only examples vs community-heavy examples

---

## 11) Recommended implementation order

### Phase 1 — retrieval foundations

- [ ] finalize payload schema
- [ ] reindex current chunks
- [ ] add Qdrant payload indexes
- [ ] add hybrid retrieval

### Phase 2 — routing

- [ ] add rule-based intent classifier
- [ ] add retrieval profiles
- [ ] route queries by profile

### Phase 3 — examples

- [ ] separate authoritative vs example buckets
- [ ] build starter packs
- [ ] add community-sheet ingestion

### Phase 4 — caching + evals

- [ ] add embedding and retrieval caches
- [ ] add answer caching for FAQ-style questions
- [ ] add retrieval/answer eval suite

---

## 12) Final decision to keep in mind

- [ ] Authoritative material answers: **what is valid**
- [ ] Examples answer: **how people actually build it**
- [ ] For this product, the best answers should intentionally combine both
