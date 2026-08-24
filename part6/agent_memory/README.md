# Agent Memory — MemoRizz 0.6

This module separates the agent-level journey from the memory-type reference:

- [`agent_memory_zero_to_hero.ipynb`](agent_memory_zero_to_hero.ipynb) builds
  **Memo**, an engineering copilot, from stateless calls through episodic,
  semantic, procedural, cache, compaction, shared-memory, and observability
  capabilities.
- [`agent_memory_zero_to_hero_oracle.ipynb`](agent_memory_zero_to_hero_oracle.ipynb)
  runs the same memory-first lifecycle with a fail-closed MemoRizz
  `OracleProvider`, database preflight, native VECTOR retrieval, reload, and
  verified transactional cleanup.
- [`memory_types.ipynb`](memory_types.ipynb) is the Oracle-backed field guide to
  all current `MemoryType` values—their unit shape, owner, operations,
  lifecycle, failure modes, and selection rules.
- [`appbook/`](appbook/) turns five major layers into an interactive streaming
  application and uses the MemoRizz 0.6 APIs demonstrated in the notebooks.

The filesystem zero-to-hero notebook runs locally with deterministic embeddings
and a teaching model. Both Oracle notebooks keep deterministic reasoning but use
OpenAI embeddings at 256 dimensions by default; all vectors and memory records
are persisted and searched in Oracle AI Database. These assertions prove scope
and persistence mechanics; they do not claim production retrieval quality.

## Run the notebooks

```bash
python -m pip install "memorizz[filesystem,oracle]>=0.6.0,<0.7.0" jupyter
jupyter lab .
```

To replace the deterministic model in the zero-to-hero notebook with OpenAI:

```bash
export OPENAI_API_KEY="..."
export MEMORIZZ_TUTORIAL_LLM=openai
export MEMORIZZ_TUTORIAL_MODEL=gpt-5.6-luna
```

Credentials are read from the process and are never written into a notebook or
persisted agent configuration.

## Run the Oracle edition

Provision the course database and its dedicated `MEMORIZZ` schema, then copy
the ignored environment template and add your OpenAI key:

```bash
../ai_maturity_form_factors/oracle.sh start
cp appbook/.env.example appbook/.env
jupyter lab agent_memory_zero_to_hero_oracle.ipynb memory_types.ipynb
```

The separate schema is intentional: MemoRizz 0.6 uses 256-dimensional memory
vectors, while the maturity notebook's `VECTOR.ACME_DOCS` table uses 768
dimensions. The Oracle notebooks never fall back to filesystem. Each cleans its
unique tutorial scope after a successful run unless
`MEMORIZZ_TUTORIAL_KEEP_DATA=1` is set.
