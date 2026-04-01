# MPMB-Copilot: Complete Project Plan

> **Goal:** A one-command-installable, locally-run RAG chatbot that helps anyone write MPMB automation scripts for D&D 5e (2014 & 2024 editions) using Adobe Acrobat JavaScript (ES5).

---

## Architecture Overview

```txt
┌─────────────────────────────────────────────────────────────────────┐
│                        Docker Compose Stack                         │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  PostgreSQL   │  │    Qdrant    │  │   Frontend   │              │
│  │  (Sessions)   │  │  (Vectors)   │  │ (React SPA)  │              │
│  │   port 5432   │  │  port 6333   │  │   port 3000  │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                  │                       │
│         └────────┬────────┘                  │                       │
│                  │                           │                       │
│         ┌────────▼────────┐                  │                       │
│         │  FastAPI Backend │◄─────────────────┘                      │
│         │   port 8000     │                                          │
│         │                 │                                          │
│         │  ┌────────────┐ │     ┌──────────────────────┐            │
│         │  │ RAG Engine │ │────▶│  LLM Providers       │            │
│         │  │            │ │     │  • Anthropic (cloud)  │            │
│         │  │ • Chunker  │ │     │  • OpenAI (cloud)     │            │
│         │  │ • Embedder │ │     │  • Ollama (local)     │            │
│         │  │ • Retriever│ │     └──────────────────────┘            │
│         │  │ • Generator│ │                                          │
│         │  └────────────┘ │                                          │
│         └─────────────────┘                                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Source Material Strategy

### Two Source Repositories

| Repository                                            | Content                                                       | Branch Strategy                                              |
| ----------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------ |
| **morepurplemorebetter/MPMBs-Character-Record-Sheet** | Core engine: `_functions/`, syntax templates, sheet mechanics | `master` (2014), `dnd2024` (2024)                            |
| **safety-orange/Imports-for-MPMB-s-Character-Sheet**  | Content scripts: spells, races, classes, feats, items, etc.   | Likely has 2014/2024 content in separate folders or branches |

### Source Acquisition (Two Modes)

**Mode A — Auto-clone (default for new users):**
The setup script clones both repos into `data/` with both branches:

```txt
data/
├── mpmb_source/           # Main MPMB repo (master branch)
├── mpmb_source_2024/      # Main MPMB repo (dnd2024 branch)
├── imports_source/        # safety-orange Imports repo
└── user_sources/          # User's own custom scripts (optional)
```

**Mode B — User-provided folders:**
User sets paths in `.env` or via a config UI:

```env
MPMB_SOURCE_DIRS=./data/mpmb_source,./my-homebrew-scripts
MPMB_EDITION_DEFAULT=2014
```

### Edition Tagging

Every chunk gets an `edition` metadata field during indexing:

- `"2014"` — from master branch or 2014-specific content
- `"2024"` — from dnd2024 branch or 2024-specific content
- `"both"` — core engine functions that apply to both editions
- `"unknown"` — user-provided content without clear edition markers

The retriever uses edition as a filter/boost signal. Users can set a default edition in their session and override per-query ("how do I add a 2024 spell?").

---

## Phased Implementation Plan

### Phase 1: Source Pipeline & Smart Chunking

**Priority: HIGH | Estimated effort: 1-2 sessions**

The current chunker (`scripts/chunk_mpmb.py`) handles template attributes and basic function/object extraction. It needs significant upgrades:

**1a. Multi-repo source acquisition script**

- Clone/update both repos + both branches
- Support user-provided additional directories
- Detect edition from branch name, file path, and content markers

**1b. Improved chunking for Imports-style files**

The safety-orange Imports repo files look like this:

```javascript
var iFileName = "pub_20140818_PHB.js";
RequiredSheetVersion("13.0.6");

SourceList["P"] = {
	/* source definition */
};

SpellsList["acid splash"] = {
	name: "Acid Splash",
	source: [
		["P", 211],
		["SRD", 95],
	],
	level: 0,
	school: "Conj",
	time: "1 a",
	range: "60 ft",
	// ... full spell definition
};

SpellsList["aid"] = {
	/* ... */
};
// Hundreds more entries per file
```

Each top-level object assignment (`SpellsList["acid splash"] = { ... }`) should be **one chunk**. The chunker needs to:

- Parse complete object literal assignments as atomic units
- Preserve the variable name and key (e.g., `SpellsList["acid splash"]`)
- Extract rich metadata: object type (spell/race/class/feat/item), name, source book, level, school, etc.
- Tag with edition based on branch/path/content analysis
- Handle `RequiredSheetVersion()` and `iFileName` as file-level metadata

**1c. Improved chunking for core engine files**

The `_functions/` directory has the MPMB engine internals. These are large files with interconnected functions. Strategy:

- Keep the existing function-boundary chunking
- Add sliding-window overlap for large functions (>2000 chars)
- Extract function dependency graphs (what calls what)
- Tag as `edition: "both"` since engine code serves both editions

**1d. Syntax template files (already working, enhance)**

- Current template attribute extraction is good
- Add: cross-reference which template attributes are used by which object types
- Add: example values from real Imports files to enrich chunk context

**Deliverables:**

- `scripts/acquire_sources.py` — clones/updates all repos
- `scripts/chunk_mpmb.py` — upgraded with all chunking strategies
- `data/chunked_output/` — JSON files with edition-tagged chunks
- Metadata schema documented

---

### Phase 2: Embedding & Vector Storage (Mostly Done)

**Priority: HIGH | Estimated effort: 0.5-1 session**

Your embedding provider abstraction is already solid. What remains:

**2a. Fix Qdrant persistence** (your current blocker)

- Verify volume mounts work across restarts
- Test with actual data, not just health checks

**2b. Wire up the indexing pipeline end-to-end**

- Chunker → Embedding service → Qdrant upload
- Add edition-aware collection or payload filtering
- Verify the full flow: `POST /api/index` → background task → vectors in Qdrant

**2c. Embedding provider configuration**

- Default: `fastembed` with `BAAI/bge-small-en-v1.5` (free, fast, good quality, no GPU needed)
- Alternative: OpenAI `text-embedding-3-small` (paid, better quality)
- Alternative: Ollama embeddings (free, local, requires model download)
- User selects via `.env`: `EMBEDDING_PROVIDER=fastembed`

**2d. Collection design**

- Single collection `mpmb_code` with payload-based filtering
- Payload fields: `edition`, `chunk_type`, `object_type`, `source_file`, `content`
- Qdrant payload indexes on `edition` and `object_type` for fast filtered search

**Deliverables:**

- Working `POST /api/index` that indexes all chunks
- Qdrant persists across container restarts
- Multiple embedding providers configurable

---

### Phase 3: LLM Client & RAG Retrieval

**Priority: HIGH | Estimated effort: 1-2 sessions**

This is the core intelligence layer.

**3a. LLM client implementation (`app/services/llm_client.py`)**

Unified interface with provider-specific adapters:

```python
class LLMClient:
    async def generate(self, messages, model, temperature, max_tokens, stream=False):
        """Route to configured provider"""

    async def stream(self, messages, model, temperature, max_tokens):
        """Streaming generation via SSE"""

class AnthropicAdapter:
    """Uses anthropic SDK"""

class OpenAIAdapter:
    """Uses openai SDK"""

class OllamaAdapter:
    """Uses httpx to call local Ollama API"""
```

Configuration via `.env`:

```env
LLM_PROVIDER=anthropic          # or openai, ollama
LLM_MODEL=claude-sonnet-4-20250514  # provider-specific model name
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-...
# or
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=codellama
```

**3b. RAG retriever (`app/core/retriever.py`)**

```python
class RAGRetriever:
    async def retrieve(self, query: str, edition: str = None, top_k: int = 8) -> RAGContext:
        """
        1. Embed the query
        2. Search Qdrant with optional edition filter
        3. Re-rank results (optional, future enhancement)
        4. Assemble context with source attribution
        """
```

Key design decisions:

- Default `top_k=8` — enough context without overwhelming the LLM
- Edition filter: if user specifies edition, use Qdrant payload filter; otherwise search all
- Similarity threshold: 0.5 minimum (configurable)
- Return source file + line numbers for attribution in UI

**3c. System prompt engineering (`app/core/prompts.py`)**

This is where MPMB expertise lives. The system prompt should:

```
You are an expert assistant for writing automation code for MorePurpleMoreBetter's
D&D 5e Character Record Sheet. You write Adobe Acrobat JavaScript (ECMAScript 5).

CRITICAL CONSTRAINTS:
- ES5 ONLY: No let/const, arrow functions, template literals, destructuring,
  classes, for...of, spread/rest, promises, or any ES6+ features.
- Use `var` for all declarations.
- Use `console.println()` not `console.log()`.
- All code runs in Adobe Acrobat's JavaScript engine, not Node.js or browsers.

MPMB OBJECT TYPES YOU CAN CREATE:
- SpellsList["key"] = { ... }     — Spells
- ClassList["key"] = { ... }      — Classes
- ClassSubList["key"] = { ... }   — Subclasses
- RaceList["key"] = { ... }       — Races
- FeatsList["key"] = { ... }      — Feats
- MagicItemsList["key"] = { ... } — Magic Items
- CreatureList["key"] = { ... }   — Creatures/Companions
- BackgroundList["key"] = { ... } — Backgrounds
- SourceList["key"] = { ... }     — Source books

EDITION AWARENESS:
- The user's current edition is: {edition}
- 2014 and 2024 editions have different attribute structures
- Always match the edition the user is working with

RELEVANT CODE CONTEXT:
{rag_context}

When providing code:
1. Always provide complete, copy-pasteable code
2. Include the file header (iFileName, RequiredSheetVersion)
3. Include all required attributes marked REQUIRED in the syntax templates
4. Add comments explaining non-obvious attributes
5. Cite which source files your examples come from
```

**3d. RAG engine orchestrator (`app/core/rag_engine.py`)**

Ties retrieval + LLM together:

```python
class RAGEngine:
    async def generate_response(self, query, session_id, edition, stream=False):
        """
        1. Detect intent (new code, modify code, explain concept, debug)
        2. Retrieve relevant chunks
        3. Build system prompt with RAG context
        4. Load conversation history from session
        5. Call LLM (streaming or not)
        6. Save message + retrieval metadata to database
        7. Return response with source citations
        """
```

**Deliverables:**

- `app/services/llm_client.py` — multi-provider LLM client
- `app/core/retriever.py` — edition-aware RAG retrieval
- `app/core/prompts.py` — system prompt templates
- `app/core/rag_engine.py` — orchestrator
- Working `POST /api/chat` and `POST /api/chat/stream` endpoints

---

### Phase 4: Session Persistence

**Priority: MEDIUM-HIGH | Estimated effort: 0.5-1 session**

Your database schema is already defined. Implementation needed:

**4a. Database connection pool (`app/services/database.py`)**

- AsyncPG connection pool via SQLAlchemy async
- Auto-reconnect on connection loss
- Health check integration

**4b. Session service (`app/services/session_service.py`)**

```python
class SessionService:
    async def create_session(self, title, edition, settings) -> Session
    async def get_session(self, session_id) -> Session
    async def list_sessions(self, user_id=None, limit=50) -> list[Session]
    async def update_session(self, session_id, **kwargs) -> Session
    async def delete_session(self, session_id)  # soft delete

    async def add_message(self, session_id, role, content, **llm_metadata) -> Message
    async def get_messages(self, session_id, limit=100) -> list[Message]

    async def track_retrieval(self, message_id, chunks, scores) -> list[MessageRetrieval]
```

**4c. API endpoints for session management**

```
GET    /api/sessions              — List sessions
POST   /api/sessions              — Create session
GET    /api/sessions/{id}         — Get session with messages
PUT    /api/sessions/{id}         — Update session (title, settings)
DELETE /api/sessions/{id}         — Soft delete session
GET    /api/sessions/{id}/messages — Get messages (paginated)
```

**4d. Wire sessions into chat flow**

- Chat requests include `session_id`
- Conversation history loaded from DB for context
- Messages saved after each exchange
- RAG retrieval metadata tracked per message

**Deliverables:**

- `app/services/database.py` — connection pool
- `app/services/session_service.py` — session CRUD
- `app/api/sessions.py` — session endpoints
- Chat endpoint uses session history

---

### Phase 5: Frontend (Simple React SPA)

**Priority: MEDIUM | Estimated effort: 1-2 sessions**

A clean, functional chat interface. Nothing fancy — focus on usability.

**5a. Tech stack**

- React 18 (Vite for dev/build)
- Tailwind CSS for styling
- Served as static files from a lightweight container (nginx or the backend itself)
- No authentication needed (local tool)

**5b. Core components**

```
frontend/
├── src/
│   ├── components/
│   │   ├── ChatWindow.jsx       — Main chat interface
│   │   ├── MessageBubble.jsx    — Individual message with code highlighting
│   │   ├── CodeBlock.jsx        — Syntax-highlighted ES5 code with copy button
│   │   ├── SessionSidebar.jsx   — Session list and management
│   │   ├── SettingsPanel.jsx    — Edition, provider, model selection
│   │   ├── SourceCitation.jsx   — Expandable source references
│   │   └── StatusBar.jsx        — Connection status, index health
│   ├── hooks/
│   │   ├── useChat.js           — Chat API + SSE streaming
│   │   ├── useSessions.js       — Session CRUD
│   │   └── useSettings.js       — User preferences
│   ├── App.jsx
│   └── main.jsx
├── Dockerfile                   — Multi-stage: build + nginx
├── package.json
└── vite.config.js
```

**5c. Key features**

- **Streaming responses** via SSE — text appears as it generates
- **Code syntax highlighting** — Prism.js or highlight.js with JavaScript support
- **Copy code button** — one click to copy generated code
- **Edition toggle** — switch between 2014/2024 context
- **Provider selection** — dropdown to switch LLM provider/model
- **Session management** — sidebar with conversation history
- **Source citations** — expandable panels showing which MPMB files were referenced
- **Index status** — indicator showing if vectors are loaded and healthy
- **Dark mode** — because developers

**5d. Docker integration**

- Add `frontend` service to `docker-compose.yml`
- Nginx serves built React app
- Reverse proxy API requests to backend

**Deliverables:**

- `frontend/` directory with complete React app
- Dockerfile for frontend
- Updated `docker-compose.yml` with frontend service

---

### Phase 6: One-Command Setup

**Priority: HIGH | Estimated effort: 0.5 session**

The goal: someone clones the repo, runs one command, and has a working system.

**6a. Setup script (`setup.sh` / `setup.ps1`)**

Your existing PowerShell scripts are thorough. Add:

- Cross-platform bash script for Linux/Mac
- Auto-detect OS and run appropriate script
- Interactive `.env` wizard (ask for API keys, choose providers)
- Clone source repos
- Run chunking
- Build + start Docker
- Trigger indexing
- Open browser to frontend

**6b. Simplified Docker Compose**

- All services start with `docker compose up -d`
- Backend auto-indexes on first startup if Qdrant is empty
- Frontend auto-connects to backend
- No manual steps required after initial setup

**6c. First-run experience**

- Frontend shows setup wizard on first visit if no API key configured
- Or: backend detects missing config and returns helpful error messages
- Ollama option requires no API key — just needs Ollama installed locally

**6d. README.md rewrite**

- Quick start (3 steps: clone, configure, run)
- Provider comparison table
- Troubleshooting
- Contributing guide

**Deliverables:**

- `setup.sh` — bash setup script
- Updated `setup.ps1` — PowerShell setup script
- Updated `docker-compose.yml` — complete stack
- Updated `README.md` — user-facing documentation
- `.env.example` — documented configuration template

---

## Configuration Matrix

### LLM Providers

| Provider  | Text Gen                 | Embeddings                | API Key Required | Local |
| --------- | ------------------------ | ------------------------- | ---------------- | ----- |
| Anthropic | ✅ Claude Sonnet/Opus    | ❌                        | Yes              | No    |
| OpenAI    | ✅ GPT-4o/4o-mini        | ✅ text-embedding-3-small | Yes              | No    |
| Ollama    | ✅ codellama/llama3/etc. | ✅ nomic-embed-text/etc.  | No               | Yes   |
| FastEmbed | ❌                       | ✅ bge-small-en-v1.5      | No               | Yes   |

### Recommended Configurations

| Persona          | LLM                       | Embeddings                      | Cost         |
| ---------------- | ------------------------- | ------------------------------- | ------------ |
| **Free/Local**   | Ollama (codellama)        | FastEmbed (bge-small)           | $0           |
| **Budget Cloud** | OpenAI (gpt-4o-mini)      | OpenAI (text-embedding-3-small) | ~$0.01/query |
| **Best Quality** | Anthropic (Claude Sonnet) | FastEmbed (bge-small)           | ~$0.01/query |
| **Hybrid**       | Anthropic (Claude Sonnet) | Ollama (nomic-embed-text)       | ~$0.01/query |

---

## Data Flow: End-to-End

### Indexing Flow

```
1. acquire_sources.py
   ├── git clone morepurplemorebetter/MPMBs-Character-Record-Sheet (master)
   ├── git clone morepurplemorebetter/MPMBs-Character-Record-Sheet (dnd2024 branch)
   ├── git clone safety-orange/Imports-for-MPMB-s-Character-Sheet
   └── (optional) user-provided directories

2. chunk_mpmb.py
   ├── Template files → template_attribute chunks (edition: both)
   ├── Core _functions/ → function chunks (edition: both)
   ├── Imports 2014 content → object_literal chunks (edition: 2014)
   ├── Imports 2024 content → object_literal chunks (edition: 2024)
   └── User scripts → auto-detected chunks

3. POST /api/index
   ├── Load JSON chunk files
   ├── Generate embeddings (configurable provider)
   ├── Upload to Qdrant with edition/type metadata
   └── Track in PostgreSQL document_chunks table
```

### Query Flow

```
1. User sends message via frontend
   ├── Session context (edition, conversation history)
   └── Query text

2. Backend receives POST /api/chat/stream
   ├── Load session + conversation history from PostgreSQL
   ├── Detect edition preference (session default or query inference)
   └── Pass to RAG engine

3. RAG Engine
   ├── Embed query
   ├── Search Qdrant (filtered by edition if specified)
   ├── Retrieve top-k chunks with scores
   ├── Build system prompt with RAG context
   ├── Append conversation history
   └── Call LLM provider (streaming)

4. Response streams back
   ├── SSE chunks sent to frontend
   ├── Frontend renders incrementally
   ├── Code blocks syntax-highlighted
   └── Source citations attached

5. Post-response
   ├── Save user message to PostgreSQL
   ├── Save assistant message to PostgreSQL
   ├── Track which chunks were retrieved (message_retrievals)
   └── Update session updated_at
```

---

## File Structure (Target State)

```
mpmb-copilot/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── chat.py          # Chat endpoints (implemented)
│   │   │   ├── health.py        # Health check (done)
│   │   │   ├── index.py         # Indexing endpoints (done)
│   │   │   ├── sessions.py      # NEW: Session CRUD
│   │   │   └── tasks.py         # Background tasks (done)
│   │   ├── core/
│   │   │   ├── prompts.py       # NEW: System prompt engineering
│   │   │   ├── rag_engine.py    # NEW: RAG orchestrator
│   │   │   ├── retriever.py     # NEW: Vector retrieval
│   │   │   ├── chunker.py       # Exists (placeholder)
│   │   │   └── embeddings.py    # Exists (placeholder)
│   │   ├── model/               # All done
│   │   ├── services/
│   │   │   ├── llm_client.py    # NEW: Multi-provider LLM client
│   │   │   ├── database.py      # NEW: Async DB connection pool
│   │   │   ├── session_service.py # NEW: Session persistence
│   │   │   ├── embeddings.py    # Done (multi-provider)
│   │   │   ├── indexer.py       # Done
│   │   │   ├── qdrant.py        # Done
│   │   │   └── task_manager.py  # Done
│   │   ├── config.py            # Done (extend for new settings)
│   │   └── main.py              # Done (add new routers)
│   ├── Dockerfile               # Done
│   └── pyproject.toml           # Done (may need new deps)
│
├── frontend/                    # NEW: React SPA
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── Dockerfile
│   ├── package.json
│   └── vite.config.js
│
├── scripts/
│   ├── acquire_sources.py       # NEW: Multi-repo clone/update
│   ├── chunk_mpmb.py            # Upgrade existing
│   ├── init.sql                 # Done
│   ├── setup.sh                 # NEW: Bash setup
│   └── setup.ps1                # Upgrade existing
│
├── data/                        # Gitignored runtime data
├── docker-compose.yml           # Update with frontend
├── .env.example                 # Update with all options
└── README.md                    # Rewrite for end users
```

---

## Implementation Order (Recommended)

| Order | Phase       | What                       | Why First                                  |
| ----- | ----------- | -------------------------- | ------------------------------------------ |
| 1     | **Phase 1** | Source pipeline + chunking | Everything depends on having good chunks   |
| 2     | **Phase 2** | Embedding + Qdrant fix     | Can't retrieve without indexed vectors     |
| 3     | **Phase 3** | LLM client + RAG retrieval | Core intelligence — makes it actually work |
| 4     | **Phase 4** | Session persistence        | Needed for conversation context in RAG     |
| 5     | **Phase 5** | Frontend                   | Usable product                             |
| 6     | **Phase 6** | One-command setup          | Polish for distribution                    |

Phases 1-3 get you a **working API-level MVP** you can test with curl.
Phase 4 adds memory across conversations.
Phase 5 makes it usable by humans.
Phase 6 makes it distributable.

---

## Open Questions to Resolve

1. **Imports repo structure:** Need to inspect `safety-orange/Imports-for-MPMB-s-Character-Sheet` to understand its folder/file organization and how 2024 content is separated from 2014 content. This directly affects the chunking strategy.

2. **Embedding model choice:** FastEmbed with `bge-small-en-v1.5` is the easiest default (no API key, no GPU, 384 dimensions). But code-specific models like `nomic-embed-text` via Ollama might retrieve better. Worth benchmarking once chunks exist.

3. **System prompt size:** The MPMB syntax templates are quite large. We may need to dynamically include only the relevant template section (e.g., spell template when asking about spells) rather than the entire template reference. This is a retrieval strategy question.

4. **dnd2024 branch content:** Need to verify what's different in the dnd2024 branch — is it entirely separate syntax templates, or just modified attribute sets? This affects how we tag and retrieve.

5. **Frontend complexity:** A simple chat UI is straightforward. But features like "edit and re-run" previous code, "diff between 2014/2024 versions," or "validate generated code against ESLint" would be more valuable. Start simple, iterate.

---

## Next Steps: What to Build First

**Session 1 target:** Get the source pipeline and chunking working end-to-end.

1. Inspect the safety-orange Imports repo structure
2. Write `scripts/acquire_sources.py`
3. Upgrade `scripts/chunk_mpmb.py` with Imports-aware chunking
4. Run the full pipeline and verify chunk quality
5. Fix Qdrant persistence and test indexing

This gives us real data to build the RAG retriever against.
