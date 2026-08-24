# Part 6 — Agent Memory with MemoRizz 0.6

Part 6 refreshes the course around two complementary questions:

1. **What shape should the AI application take?** The image-free AI maturity
   ladder builds the same Acme Cloud assistant as a chatbot, RAG system,
   workflow, tool-using agent, and autonomous builder.
2. **How should an agent remember?** The MemoRizz 0.6 track builds a scoped,
   memory-first copilot and then examines every memory type in a dedicated field
   guide.

Each module has a runnable notebook and an interactive FastAPI appbook. Start
with the notebooks; use the appbooks to inspect the same ideas behind a UI and
streaming API.

| Module | Start here | Companion |
|---|---|---|
| [`ai_maturity_form_factors/`](ai_maturity_form_factors/) | [`notebook/ai_maturity_form_factors_notebook.ipynb`](ai_maturity_form_factors/notebook/ai_maturity_form_factors_notebook.ipynb) | [`appbook/`](ai_maturity_form_factors/appbook/) |
| [`agent_memory/`](agent_memory/) | [`agent_memory_zero_to_hero.ipynb`](agent_memory/agent_memory_zero_to_hero.ipynb), [`agent_memory_zero_to_hero_oracle.ipynb`](agent_memory/agent_memory_zero_to_hero_oracle.ipynb), then [`memory_types.ipynb`](agent_memory/memory_types.ipynb) | [`appbook/`](agent_memory/appbook/) |

Both appbooks include a persistent, resizable, read-only Data Explorer on every
page. It shows allowlisted Oracle tables, column and primary-key metadata,
paginated rows, and live application database activity without exposing an
arbitrary SQL surface.

## Design choices in this refresh

- No image blocks or image-gallery endpoints are required by the course.
- The filesystem zero-to-hero notebook uses deterministic embeddings and a
  deterministic teaching model, so it runs without a key.
- The Oracle zero-to-hero and memory-types notebooks use the dedicated
  `MEMORIZZ` schema and fail closed instead of silently switching providers.
- Set `MEMORIZZ_TUTORIAL_LLM=openai` to exercise the hosted OpenAI lane.
- Every runtime memory example supplies host-owned `memory_id`, `user_id`, and
  `thread_id` scope.
- Appbook secrets are read only from environment variables or ignored `.env`
  files. Process/CI variables take precedence.

## Quickstart

```bash
# Filesystem notebook plus Oracle-backed notebooks
python -m pip install "memorizz[filesystem,oracle]>=0.6.0,<0.7.0" jupyter
jupyter lab agent_memory

# An appbook
cd agent_memory/appbook
cp .env.example .env       # add the relevant key; .env is ignored
./run.sh
```

The AI maturity notebook requires the local Oracle database for its database-
specific RAG/SQL sections. From that module, run `./oracle.sh start` first. Its
appbook can fall back to an in-memory NumPy retriever when Oracle is unavailable.
The same helper provisions a separate 256-dimensional `MEMORIZZ` schema for the
Oracle agent-memory notebook and appbook.
