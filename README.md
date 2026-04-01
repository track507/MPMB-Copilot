# MPMB-Copilot

> **Last Updated:** April 1, 2026
> **Status:** Initial end-to-end RAG MVP is running
> **Latest verified setup:** `npm run setup:all` successfully cloned the source repos, chunked them, started Docker services, and indexed **4,831 vectors across 281 unique source files**

## Overview

**MPMB-Copilot** is a RAG-powered assistant for MorePurpleMoreBetter's D&D 5e Character Record Sheet workflows and related MPMB scripting tasks.

The current backend can:

- acquire and chunk MPMB source repositories
- index those chunks into Qdrant
- retrieve tier-balanced context for a query
- generate answers through Anthropic, OpenAI, or Ollama
- stream responses over Server-Sent Events

## Current Standing

The repo is no longer blocked in setup.

- Docker-based setup has been verified end to end
- the vector index is populated and `/api/index/status` returns real metadata
- `/api/chat` and `/api/chat/stream` use the actual RAG pipeline, not placeholders
- intent detection, query analysis, prompt building, retrieval, and LLM generation are wired together
- background indexing tasks are exposed through `/api/tasks`

## What Works Today

- **Source acquisition + chunking**
  - `scripts/setup.ps1` clones or updates the 2014 MPMB branch, the 2024 branch, and the Imports repo
  - `scripts/chunk_mpmb.py` produces chunk JSON files in `data/chunked_output`

- **Indexing**
  - `POST /api/index` starts non-blocking indexing in the background
  - `GET /api/index/status` reports `collection_name`, `total_vectors`, `indexed_files`, `last_updated`, and status
  - `GET /api/tasks/{task_id}` exposes indexing progress

- **Chat pipeline**
  - `POST /api/chat` runs the full RAG pipeline and returns response metadata
  - `POST /api/chat/stream` streams responses via SSE
  - retriever logic combines authoritative chunks with example chunks
  - Anthropic, OpenAI, and Ollama are supported through LangChain wrappers

- **Operations**
  - `/api/health` reports backend, Qdrant, LLM provider, and embedding readiness
  - `/api/docs` exposes the OpenAPI docs
  - npm scripts provide a single CLI for setup, Docker lifecycle, chunking, linting, and tests

## Current Gaps

- **Session persistence is not wired yet**
  - `conversation_id` is accepted by the chat API, but conversation history loading is still stubbed

- **Source citations are still lightweight**
  - chat responses currently return retrieval summary metadata rather than full per-chunk file/line citations

- **Tool use and extended thinking are scaffolded, not implemented**
  - the settings exist in `backend/app/settings.py`, but provider calls do not yet use them

- **The backend image snapshots chunked output at build time**
  - if you regenerate chunks and want the Dockerized backend to use them, rebuild the backend image or rerun `npm run setup:docker`

- **Docker health and app health may disagree**
  - on Windows, Docker may occasionally show Qdrant as unhealthy even while `/api/health` reports Qdrant as healthy and queries succeed

## Quick Start

### Prerequisites

- Git
- Python 3.13 or newer available as `python` or `py -3`
- Node.js 24 or newer
- npm 11 or newer
- Docker Desktop or another Docker Engine setup
- a configured LLM provider in `.env`
  - Anthropic API key, OpenAI API key, or a reachable Ollama host

### Setup

1. Create `.env` from `.env.example` and fill in your provider settings.
1. Install repo tooling:

```bash
npm install
```

1. Run the full verified setup flow:

```bash
npm run setup:all
```

That command chain will:

1. clone or update the source repositories
1. run the chunker
1. build and start Docker services
1. wait for the backend to become healthy
1. trigger indexing and wait for completion

### Verify the Stack

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/index/status
```

Docs are available at:

```txt
http://localhost:8000/api/docs
```

## Local Backend Development

If you want to run the backend outside Docker:

```bash
uv sync --project backend --all-groups
npm run dev
```

Useful note:

- `npm run dev` uses `uv run --no-sync`, so you should run `uv sync --project backend --all-groups` at least once before local development

## Common Commands

```bash
# clone/update repos + run the chunker
npm run setup

# build and start containers
npm run setup:docker

# wait for backend health and trigger indexing
npm run setup:index

# full setup flow
npm run setup:all

# rerun the chunker only
npm run chunk

# local FastAPI dev server
npm run dev

# Docker lifecycle
npm run docker:up
npm run docker:down
npm run docker:logs

# quality gates
npm run check
npm run check:full
```

## API Surface

### Health

- `GET /api/health`
- `GET /api/ping`

### Chat

- `POST /api/chat`
- `POST /api/chat/stream`

### Indexing

- `GET /api/index/status`
- `POST /api/index`
- `DELETE /api/index`

### Background Tasks

- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `DELETE /api/tasks/{task_id}`

## Architecture

```txt
User Query
  -> FastAPI /api/chat
  -> query analysis + intent detection
  -> tier-aware retriever
  -> prompt builder
  -> provider-specific LLM client
  -> response / stream

Initial Setup
  -> scripts/setup.ps1
  -> scripts/chunk_mpmb.py
  -> docker compose up -d --build
  -> scripts/wait-and-index.mjs
  -> POST /api/index
  -> Qdrant vector index
```

## Repository Layout

```txt
mpmb-copilot/
├── backend/
│   ├── app/
│   │   ├── api/                 # health, chat, index, task endpoints
│   │   ├── core/                # query analysis, intent, prompts, retriever, rag engine
│   │   ├── model/               # Pydantic request/response models
│   │   ├── services/            # embeddings, indexing, LLM client, vector store, task manager
│   │   ├── config.py            # environment-backed app config
│   │   └── settings.py          # hot-reloadable behavioral settings
│   ├── pyproject.toml
│   └── uv.lock
├── data/                        # gitignored runtime data and chunk output
├── docker/
│   ├── backend/
│   │   └── Dockerfile
│   └── postgres/
│       ├── Dockerfile
│       └── init.sql
├── scripts/
│   ├── chunk_mpmb.py
│   ├── setup.ps1
│   └── wait-and-index.mjs
├── docker-compose.yml
└── package.json
```

## Roadmap

### Completed or Verified

- project structure and repo tooling
- Docker stack for backend, Postgres, and Qdrant
- source acquisition and chunking
- vector indexing into Qdrant
- initial RAG engine
- streaming chat endpoint
- multi-provider LLM client

### Next Priorities

- wire session persistence into the chat flow
- return richer per-source citations in chat responses
- connect tool use and extended thinking settings to provider calls
- add more tests and end-to-end verification
- continue frontend and persistence work

## License

This repository is licensed under the **Apache License 2.0**. See [`LICENSE`](./LICENSE).

## Content and Custom Document Policy

- This repository distributes code only and does **not** bundle third-party documentation corpora for RAG.
- Users who add custom reference files are responsible for ensuring they have legal rights to upload, index, and use that content.
- Uploaded or custom content is intended for user-provided retrieval context and is not represented as relicensed by this project.
- See:
  - [`docs/CUSTOM_DOCS_POLICY.md`](./docs/CUSTOM_DOCS_POLICY.md)
  - [`docs/TERMS_OF_USE.md`](./docs/TERMS_OF_USE.md)
