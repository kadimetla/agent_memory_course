"""AI Maturity Ladder — FastAPI application.

Mounts one router per form factor, warms the retriever in the background on
startup, and serves the static frontend from the same origin.

Run from the `app/` directory:
    uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import FRONTEND_DIR
from backend.core.activity import activity, operations_for
from backend.core.automations import automation_store
from backend.core.retrieval import store
from backend.routers import agent, builder, chat, data_explorer, meta, rag, workflow


async def _scheduler_loop() -> None:
    """Fire any due automations roughly every 15s — Form Factor 5's in-app scheduler."""
    while True:
        await asyncio.sleep(15)
        try:
            await run_in_threadpool(automation_store.tick)
        except Exception:  # noqa: BLE001 — never let the scheduler crash the app
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the embedding model + Oracle connection without blocking startup.
    threading.Thread(target=store.initialize, daemon=True).start()
    scheduler = asyncio.create_task(_scheduler_loop())
    try:
        yield
    finally:
        scheduler.cancel()


app = FastAPI(title="AI Maturity Ladder", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def database_activity(request, call_next):
    path = request.url.path
    if path == "/api/data_explorer/activity":
        return await call_next(request)
    operations = operations_for(request.method, path)
    transaction_id = activity.transaction_id()
    started = perf_counter()
    for item in operations:
        await activity.publish(transaction_id=transaction_id, status="active", route=path, **item)
    try:
        response = await call_next(request)
        status = "committed" if response.status_code < 400 else "rolled_back"
        return response
    except Exception:
        status = "rolled_back"
        raise
    finally:
        detail = f"{(perf_counter() - started) * 1000:.1f} ms"
        for item in operations:
            await activity.publish(
                transaction_id=transaction_id,
                status=status,
                route=path,
                detail=detail,
                **item,
            )


for r in (meta.router, data_explorer.router, chat.router, rag.router,
          workflow.router, agent.router, builder.router):
    app.include_router(r)

# Serve the SPA last so the API routes win.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
