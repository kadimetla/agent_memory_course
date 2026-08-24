# The Agent Memory Stack — App

A FastAPI + vanilla-JS application that turns the
[`agent_memory_zero_to_hero.ipynb`](../agent_memory_zero_to_hero.ipynb) workshop into an
interactive, sleek (light/dark) web app. The sidebar is the **memory stack**: each layer adds
one capability, climbing from a single conversation to a coordinating multi-agent team. It is
powered by **MemoRizz 0.6** on **Oracle AI Database** with an exact-search
filesystem fallback.

| # | Memory layer | Page | What it shows |
|---|--------------|------|----------------|
| 1 | **Conversation** | `#/conversation` | Episodic `CONVERSATION_MEMORY`; remembers across turns and across a restart (`MemAgent.load`). |
| 2 | **Persona & Entities** | `#/semantic` | Semantic memory: a stable `PERSONAS` identity + structured `ENTITY_MEMORY` facts. |
| 3 | **Knowledge Base** | `#/knowledge` | RAG over a `KnowledgeBase` (vector search) + a grounded, cited answer. |
| 4 | **Procedural** | `#/procedural` | Tools + a recalled `WORKFLOW_MEMORY` runbook + first-class, lifecycle-aware `SKILLBOX` retrieval. |
| 5 | **Coordination** | `#/coordination` | `SHARED_MEMORY`: a lead + Researcher + Reviewer collaborating, via `MultiAgentOrchestrator`. |

A prominent **Memory Data Explorer** panel on the overview opens the persistent,
resizable explorer that sits at the bottom of every page. It
browses the MemoRizz-owned tables in the active `MEMORIZZ` schema, shows real
columns, primary keys and paginated rows, summarizes VECTOR and large LOB cells,
and highlights memory reads and writes through a live SSE activity rail. Oracle's
generated index backing tables are excluded, and the browser surface is strictly
read-only. With the filesystem fallback, the same UI exposes virtual tables for
the current `MemoryType` stores.

## Run

```bash
# from this directory
./run.sh
# → http://127.0.0.1:8000
```

`run.sh` activates the **`oracle_demos`** conda env if present, installs the requirements on
first run, and starts uvicorn. Or manually:

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000   # run from appbook/
```

> [!IMPORTANT]
> **In a Codespace, open the app from the Ports panel → 🌐 Open in Browser.** Confirm it's up with
> `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/health` (`200` = up).

## Requirements & graceful degradation

- **`OPENAI_API_KEY`** — required for generated answers (the LLM `gpt-5.6-luna` **and** the embeddings
  `text-embedding-3-small` @ 256d). Read from `appbook/.env`, or the
  course's existing `../.env` / `../../.env`. Without it, health and local
  retrieval still initialize with a deterministic teaching embedder, while
  model-backed routes return a clear error.
- **Oracle AI Database** — optional. Run
  `../../ai_maturity_form_factors/oracle.sh start` to provision the dedicated
  256-dimensional `MEMORIZZ` schema, then copy `.env.example` to `.env`. The app
  builds a MemoRizz `OracleProvider` and auto-creates its memory stores. If
  Oracle is unset or unreachable it falls back to MemoRizz's
  **`FileSystemProvider`** under `appbook/.data/memorizz`, so the whole app still runs. The
  active backend is shown in the sidebar and on each page.

Every request-serving memory operation supplies host-owned `memory_id`,
`user_id`, and `thread_id` values. The app also uses `.with_model(...)`,
`memory_capabilities()`, a first-class `Skillbox`, governed cache-compatible
model configuration, and typed provider capability reporting from MemoRizz 0.6.

## Architecture

```
appbook/
├── backend/
│   ├── main.py              FastAPI app; warms the Memory Core; serves the SPA
│   ├── config.py            env loading, model, embeddings, Oracle creds
│   ├── schemas.py           Pydantic request bodies
│   ├── core/
│   │   ├── activity.py      read/write activity broker for the explorer
│   │   ├── memory.py        the Memory Core: memorizz provider (Oracle→filesystem) + helpers
│   │   ├── knowledge.py     the Acme Cloud corpus, ingested via KnowledgeBase
│   │   └── sse.py           EventSourceResponse helper
│   └── routers/             one per memory layer + health + data_explorer
└── frontend/                index.html · styles.css · app.js (no build step)
```

Every layer streams its output to the browser over Server-Sent Events. The frontend is a
dependency-free single-page app (hash router, theme toggle, SSE-over-`fetch`). The backend uses
MemoRizz primitives throughout — `MemAgent`, `Persona`, `EntityMemory`, `KnowledgeBase`,
`Workflow`, `Skillbox`, and `SharedMemory` — the same APIs taught in the notebooks.
