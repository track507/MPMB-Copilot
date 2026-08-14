# Backend

FastAPI service that powers MPMB-Copilot's chat, retrieval, and indexing.

> See the [root README](../README.md) for the user-facing pitch and quick start. This document is for working *inside* `backend/`.

## Stack

- **FastAPI** — HTTP + Server-Sent Events
- **PydanticAI** — agent loop, multi-provider LLM client (Anthropic / OpenAI / Ollama), tool-use orchestration
- **SQLAlchemy 2.0 (async)** — sessions and messages persistence
- **Qdrant client** — hybrid retrieval (dense + BM25, RRF-fused)
- **FastEmbed** — local embedding model (`BAAI/bge-small-en-v1.5`)
- **uv** — package manager (replaces pip/poetry)

## Layout

```
backend/
├── app/
│   ├── api/                    # FastAPI routers
│   │   ├── chat.py             # POST /api/chat, POST /api/chat/stream — the SSE loop lives here
│   │   ├── sessions.py         # session CRUD
│   │   ├── index.py            # POST /api/index, GET /api/index/status
│   │   └── tasks.py            # background-task progress
│   ├── core/                   # business logic
│   │   ├── agent.py            # build_agent() + non-streaming generate()
│   │   ├── rag_engine.py       # streaming RAG pipeline + tool-event emission
│   │   ├── retriever.py        # tier-aware dual search with intent budgets
│   │   ├── chunker.py          # MPMB JS → JSON chunks
│   │   ├── intent.py           # query intent classifier
│   │   ├── query_analysis.py   # edition / object-type detection
│   │   ├── prompts.py          # system prompt + tool-use addendum
│   │   └── tools/              # MPMB read-only tool implementations
│   │       ├── source_paths.py # security boundary for path resolution
│   │       └── mpmb_tools.py   # mpmb_read / mpmb_grep / mpmb_function
│   ├── services/
│   │   ├── llm/providers.py    # provider switch (anthropic/openai/ollama)
│   │   ├── llm/messages.py     # history → PydanticAI message conversion
│   │   ├── vector/qdrant.py    # Qdrant client wrapper
│   │   ├── embedding/          # FastEmbed wrapper
│   │   ├── db/                 # SQLAlchemy models, session_service
│   │   ├── task_manager.py     # background-task registry for indexing
│   │   └── title_generator.py  # auto-title sessions after first message
│   ├── model/schemas/          # Pydantic request/response shapes
│   ├── config.py               # env-backed config (pydantic-settings)
│   ├── settings.py             # hot-reloadable behavioral settings
│   └── main.py                 # FastAPI app + lifespan
├── tests/                      # pytest suite (70+ tests)
├── pyproject.toml
└── uv.lock
```

## Running

The backend is normally launched via the root `pnpm run dev` (which starts both backend and frontend with concurrent logging). Two other ways:

**Local dev only:**

```bash
# from repo root, NOT from backend/
pnpm run dev:backend
```

Runs the port pre-flight check, then `uvicorn app.main:app --reload --reload-dir backend/app --host 127.0.0.1 --port 8000`.

The loopback bind is deliberate: `AUTH_DISABLED` is honored only while the server is bound to loopback, and a non-loopback bind with no admin account demands a one-time setup token (see `docs/AUTH.md`).

**Inside Docker:**

```bash
pnpm run docker:up
```

Brings up postgres, qdrant, and `mpmb-backend` (image built from `docker/backend/Dockerfile`). The local `pnpm run dev:backend` and the Docker backend can't both run — they fight for port 8000. Pick one mode.

## Environment

`backend/app/config.py` reads `.env` from the **repo root** via `Path(__file__).resolve().parents[2] / ".env"`. There is **no** `backend/.env` — don't create one.

Key vars (full list in `.env.example`):

| Var | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for the default provider |
| `DEFAULT_LLM_PROVIDER` | `anthropic` | `anthropic`, `openai`, or `ollama` |
| `DEFAULT_MODEL` | `claude-sonnet-4-6` | Model id passed to PydanticAI |
| `POSTGRES_HOST` | `127.0.0.1` | Use `127.0.0.1`, not `localhost` (Windows IPv6 fallback) |
| `POSTGRES_PORT` | `5433` | Compose maps host 5433 → container 5432 |
| `QDRANT_HOST` | `127.0.0.1` | Same IPv6 caveat |
| `QDRANT_PORT` | `6333` | |
| `MPMB_SOURCE_DIR` | `./data/mpmb_source` | 2014 sources clone target |
| `MPMB_SOURCE_2024_DIR` | `./data/mpmb_source_2024` | 2024 sources clone target |
| `MPMB_REPO_URL` | `https://github.com/morepurplemorebetter/MPMBs-Character-Record-Sheet.git` | 2014 source repo |
| `MPMB_REPO_2024_URL` | `https://github.com/morepurplemorebetter/2024_MPMBs-Character-Record-Sheet.git` | 2024 source repo |
| `MPMB_REPO_BRANCH_2014` | `master` | 2014 source branch |
| `MPMB_REPO_BRANCH_2024` | `main` | 2024 source branch |
| `ENABLE_TOOL_USE` | `false` | Set to `true` to expose `mpmb_read` / `mpmb_grep` / `mpmb_function` to the model |
| `MAX_TOOL_CALLS` | `8` | Per-request tool-call cap |

## Tests

```bash
# from backend/
uv run pytest                  # 70 tests, ~2 seconds
uv run pytest -v               # verbose
uv run pytest tests/core/      # subset

# from root (uses uv via pnpm)
pnpm test
```

Tests don't hit Postgres or Qdrant — the retriever and DB are mocked at the boundary.

## Tool use

When `ENABLE_TOOL_USE=true`, the system prompt gets a `TOOL_USE_ADDENDUM` (in `core/prompts.py`) and the agent receives a `FunctionToolset[Deps]`. The three tools live in `core/tools/mpmb_tools.py`:

- **`mpmb_function(root, name, edition)`** — fetch a function or top-level variable's full body
- **`mpmb_read(root, path, start_line=, end_line=)`** — quote verbatim lines from a known file
- **`mpmb_grep(root, pattern, edition, path_glob=)`** — pattern search across files

All three go through `core/tools/source_paths.py` for security: root allowlist, no `..`, no hidden dirs, denied subdirs (`.git`, `.venv`, `node_modules`), extension allowlist, size cap, symlink containment.

The streaming SSE loop in `core/rag_engine.py:stream()` watches PydanticAI's `agent.iter()` for `FunctionToolCallEvent` and `FunctionToolResultEvent`, then emits `event: "tool_start"` and `event: "tool_end"` SSE chunks so the frontend can render the pill and footer.

## Streaming format

`POST /api/chat/stream` returns SSE chunks. Each line is `data: <JSON>\n\n`:

```jsonc
// content delta
{"chunk": "Here is the ", "done": false}

// tool fired
{"chunk": "", "done": false, "event": "tool_start", "tool": {"name": "mpmb_function"}}
{"chunk": "", "done": false, "event": "tool_end",   "tool": {"name": "mpmb_function", "status": "success", "duration_ms": 42.1}}

// final
{"chunk": "", "done": true, "metadata": { "session_id": "...", "tools": {...}, "retrieval": {...}, "timing": {...} }}
data: [DONE]
```

## Common gotchas

- **Embedding model first-load takes ~30s.** First chat request after backend boot triggers FastEmbed to download `BAAI/bge-small-en-v1.5`. Cached after that.
- **Reload watches only `backend/app/`.** Editing files outside that path won't trigger uvicorn reload — that's intentional, otherwise `node_modules` churn would restart the backend constantly.
- **`POSTGRES_PASSWORD` only sticks at first volume init.** Changing it in `.env` later does nothing unless you nuke the volume or `ALTER USER` inside the container.
- **Stale uvicorn zombies.** If `pnpm run dev:backend` errors with "port 8000 in use," kill stray Python processes (see root README troubleshooting).
