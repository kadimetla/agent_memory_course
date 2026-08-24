"""Layer 2 — Semantic memory: persona + entity memory.

The agent carries a stable **persona** (identity/voice) and an **entity memory**:
as you tell it facts ("our on-call tool is PagerPilot, owned by Ada"), it records
them as structured entities it can recall precisely. Notebook §3 + §4.
"""
from __future__ import annotations

import re

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

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
from backend.schemas import SemanticRequest

router = APIRouter(prefix="/api/semantic", tags=["semantic"])

PERSONA = {
    "name": "Memo",
    "role": "TECHNICAL_EXPERT",
    "goals": "Help engineers ship reliable LLM apps; favor correctness first, then clarity.",
    "background": "A staff-level AI platform engineer experienced in retrieval, vector databases, "
                  "evaluation, and running agents in production.",
}

INSTRUCTION = (
    "You are Memo. Answer in character. When the user states a durable fact about a person, "
    "service, or system, record it with your entity-memory tools, and recall such facts precisely "
    "when asked."
)

_sessions: dict[str, dict] = {}
USER_ID = "part6-workshop-user"


def _scope(session_id: str) -> dict[str, str]:
    return {
        "memory_id": f"appbook-semantic-{session_id}",
        "user_id": USER_ID,
        "thread_id": session_id,
    }


def _build_persona():
    from memorizz import Persona, RoleType

    return Persona(
        name=PERSONA["name"],
        role=getattr(RoleType, PERSONA["role"], RoleType.TECHNICAL_EXPERT),
        goals=PERSONA["goals"],
        background=PERSONA["background"],
    )


def _session(session_id: str) -> dict:
    s = _sessions.get(session_id)
    if s is None:
        scope = _scope(session_id)
        agent = store.build_agent(
            INSTRUCTION,
            name="Memo",
            persona=_build_persona(),
            # Facts are validated and written by trusted host code below. This
            # avoids asking a probabilistic model to manufacture storage-schema
            # fields and keeps tenant scope out of tool arguments.
            entity_memory=False,
            memory_id=scope["memory_id"],
        )
        agent.save()
        s = {"agent": agent, "scope": scope}
        _sessions[session_id] = s
    return s


def _entities(memory_id: str, user_id: str) -> list[dict]:
    """Best-effort list of captured entities, rendered defensively for the UI."""
    try:
        from memorizz.long_term.semantic.entity_memory.entity_memory import EntityMemory

        rows = EntityMemory(store.require()).list_entities(
            memory_id=memory_id, user_id=user_id
        ) or []
    except Exception:
        return []
    out = []
    for e in rows[:12]:
        if not isinstance(e, dict):
            continue
        attrs = e.get("attributes") or []
        pairs = []
        if isinstance(attrs, list):
            for a in attrs:
                if isinstance(a, dict) and a.get("name") is not None:
                    pairs.append({"name": str(a.get("name")), "value": str(a.get("value", ""))})
        out.append({
            "name": e.get("name") or e.get("entity_id") or "entity",
            "entity_type": e.get("entity_type") or "",
            "attributes": pairs,
        })
    return out


def _capture_facts(message: str, memory_id: str, user_id: str) -> None:
    """Capture the workshop's durable facts through the validated 0.6 API.

    In production this boundary would consume a reviewed structured extractor.
    The course uses transparent regexes so learners can see exactly which facts
    become durable and why.
    """
    from memorizz import EntityMemory

    entities = EntityMemory(store.require())
    tool_match = re.search(r"on-call tool is\s+([\w.-]+)", message, re.IGNORECASE)
    owner_match = re.search(r"\b([A-Z][\w.-]+)\s+owns\s+it\b", message)
    if tool_match:
        attributes = [
            {
                "name": "purpose",
                "value": "on-call tool",
                "confidence": 1.0,
                "source": "user statement",
            }
        ]
        if owner_match:
            attributes.append(
                {
                    "name": "owner",
                    "value": owner_match.group(1),
                    "confidence": 1.0,
                    "source": "user statement",
                }
            )
        entities.upsert_entity(
            name=tool_match.group(1),
            entity_type="tool",
            attributes=attributes,
            memory_id=memory_id,
            user_id=user_id,
        )

    identity = re.search(r"\bI(?:'m| am)\s+([A-Z][\w.-]+)", message)
    if identity:
        attributes = []
        role = re.search(r"\b(?:a|an)\s+([^;,]+?)(?:;|,|\.|$)", message, re.IGNORECASE)
        project = re.search(r"current project is\s+([^.;]+)", message, re.IGNORECASE)
        if role:
            attributes.append(
                {"name": "role", "value": role.group(1).strip(), "confidence": 1.0,
                 "source": "user statement"}
            )
        if project:
            attributes.append(
                {"name": "current_project", "value": project.group(1).strip(), "confidence": 1.0,
                 "source": "user statement"}
            )
        entities.upsert_entity(
            name=identity.group(1),
            entity_type="person",
            attributes=attributes,
            memory_id=memory_id,
            user_id=user_id,
        )


def _entity_context(memory_id: str, user_id: str) -> list[dict]:
    return _entities(memory_id, user_id)


@router.get("/persona")
def persona() -> dict:
    return {"persona": PERSONA}


@router.get("/entities")
def entities(session_id: str) -> dict:
    scope = _scope(session_id)
    return {"entities": _entities(scope["memory_id"], scope["user_id"])}


@router.post("/message")
async def message(req: SemanticRequest):
    reason = unavailable_reason()
    if reason:
        return sse_response(error_stream(reason))
    s = _session(req.session_id)
    agent = s["agent"]
    scope = s["scope"]

    async def events():
        await run_in_threadpool(
            _capture_facts, req.message, scope["memory_id"], scope["user_id"]
        )
        entity_context = await run_in_threadpool(
            _entity_context, scope["memory_id"], scope["user_id"]
        )
        win, segs = await run_in_threadpool(
            compute_context_segments,
            agent,
            req.message,
            history_memory_id=scope["memory_id"],
            user_id=scope["user_id"],
            thread_id=scope["thread_id"],
        )
        async for ev in prefill_context_events(win, segs):
            yield ev
        answer = await run_agent(
            lambda: agent.run(
                req.message,
                context={"scoped_entity_memory": entity_context},
                **scope,
            )
        )
        yield final_context_event(agent, win, segs)
        async for ev in pseudo_stream(answer):
            yield ev
        ents = await run_in_threadpool(
            _entities, scope["memory_id"], scope["user_id"]
        )
        yield {"type": "done", "entities": ents, "backend": store.backend}

    return sse_response(events())
