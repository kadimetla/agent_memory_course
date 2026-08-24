"""Layer 3 — Knowledge base (semantic memory / RAG).

Ingest the Acme Cloud corpus via memorizz `KnowledgeBase`, retrieve the most
relevant passages by vector similarity, then stream a grounded, cited answer.
Exposes retrieval on its own (`/search`) so the UI can show *what* was retrieved.
Notebook §5.
"""
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from backend.core import knowledge as kb
from backend.core.memory import (
    compute_context_segments,
    error_stream,
    final_context_event,
    prefill_context_events,
    pseudo_stream,
    run_agent,
    store,
    unavailable_reason,
)
from backend.core.sse import sse_response
from backend.schemas import KnowledgeRequest

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])
USER_ID = "part6-workshop-user"


@router.post("/search")
async def search(req: KnowledgeRequest) -> dict:
    reason = unavailable_reason()
    if reason:
        return {"backend": store.backend, "hits": [], "error": reason}
    hits = await run_in_threadpool(kb.search, store.require(), req.query, req.k)
    return {"backend": store.backend, "hits": hits}


@router.post("/answer")
async def answer(req: KnowledgeRequest):
    reason = unavailable_reason()
    if reason:
        return sse_response(error_stream(reason))

    async def events():
        scope = {
            "memory_id": "appbook-knowledge",
            "user_id": USER_ID,
            "thread_id": f"rag-{uuid4()}",
        }
        hits = await run_in_threadpool(kb.search, store.require(), req.query, req.k)
        yield {"type": "sources", "backend": store.backend, "hits": hits}

        context = "\n".join(f"[{i + 1}] {h['content']}" for i, h in enumerate(hits))
        instruction = (
            "You are the Acme Cloud support assistant. Answer the question using ONLY the context "
            "below. Cite the sources you use with bracketed numbers like [1]. If the answer is not "
            "in the context, say you don't have that information.\n\n"
            f"Context:\n{context}"
        )
        agent = store.build_agent(
            instruction,
            name="KB",
            memory_id=scope["memory_id"],
            ephemeral=True,
        )
        win, segs = await run_in_threadpool(
            compute_context_segments,
            agent,
            req.query,
            base_instruction="You are the Acme Cloud support assistant. Answer only from the retrieved context and cite sources [n].",
            kb_hits=hits,
            history_memory_id=scope["memory_id"],
            user_id=scope["user_id"],
            thread_id=scope["thread_id"],
        )
        async for ev in prefill_context_events(win, segs):
            yield ev
        result = await run_agent(lambda: agent.run(req.query, **scope))
        yield final_context_event(agent, win, segs)
        async for ev in pseudo_stream(result):
            yield ev
        yield {"type": "done"}
        agent.close(close_memory_provider=False)

    return sse_response(events())
