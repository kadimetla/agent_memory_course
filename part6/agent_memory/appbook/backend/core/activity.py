"""Live, human-readable memory-database activity for the Data Explorer.

This is application telemetry for teaching. It deliberately reports only the
package-owned tables associated with public app routes and is not Oracle audit
data.
"""
from __future__ import annotations

import asyncio
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any


class ActivityBroker:
    def __init__(self) -> None:
        self._recent: deque[dict[str, Any]] = deque(maxlen=160)
        self._subscribers: set[asyncio.Queue] = set()
        self._sequence = 0

    def transaction_id(self) -> str:
        return uuid.uuid4().hex[:12]

    async def publish(
        self,
        *,
        transaction_id: str,
        table: str,
        operation: str,
        status: str,
        route: str,
        row_key: str | None = None,
        detail: str | None = None,
    ) -> dict[str, Any]:
        self._sequence += 1
        event = {
            "sequence": self._sequence,
            "transaction_id": transaction_id,
            "table": table.lower(),
            "operation": operation.upper(),
            "status": status,
            "route": route,
            "row_key": row_key,
            "detail": detail,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        self._recent.appendleft(event)
        for queue in tuple(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
        return event

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=96)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        return list(self._recent)[: min(max(limit, 1), 100)]


activity = ActivityBroker()


def operations_for(method: str, path: str) -> list[dict[str, str | None]]:
    """Map each appbook route to the MemoRizz tables it may touch."""
    method = method.upper()
    row_key: str | None = None
    operations: list[tuple[str, str]] = []

    if path.startswith("/api/data_explorer/tables/") and path.endswith("/rows"):
        operations = [(path.split("/")[4], "READ")]
    elif path.startswith("/api/conversation/message"):
        operations = [("agents", "READ"), ("conversation_memory", "READ"), ("conversation_memory", "WRITE")]
    elif path.startswith("/api/conversation/reload"):
        operations = [("agents", "READ"), ("conversation_memory", "READ")]
    elif path.startswith("/api/conversation/reset"):
        operations = [("conversation_memory", "WRITE")]
    elif path.startswith("/api/semantic/persona"):
        operations = [("personas", "READ")]
    elif path.startswith("/api/semantic/entities"):
        operations = [("entity_memory", "READ")]
    elif path.startswith("/api/semantic/message"):
        operations = [
            ("personas", "READ"), ("entity_memory", "READ"),
            ("conversation_memory", "READ"), ("conversation_memory", "WRITE"),
            ("entity_memory", "WRITE"),
        ]
    elif path.startswith("/api/knowledge/"):
        operations = [("knowledge_base", "READ")]
    elif path.startswith("/api/procedural/"):
        operations = [
            ("toolbox", "READ"), ("conversation_memory", "WRITE"),
            ("tool_log", "WRITE"), ("workflow_memory", "WRITE"),
        ]
    elif path.startswith("/api/coordination/"):
        operations = [("shared_memory", "READ"), ("shared_memory", "WRITE"), ("agents", "READ")]

    seen: set[tuple[str, str]] = set()
    result = []
    for table, operation in operations:
        key = (table.lower(), operation)
        if key not in seen:
            result.append({"table": table.lower(), "operation": operation, "row_key": row_key})
            seen.add(key)
    return result
