"""Read-only Data Explorer for Oracle-backed MemoRizz memory."""
from __future__ import annotations

import array
import asyncio
import base64
import json
import re
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from backend.config import settings
from backend.core.activity import activity
from backend.core.memory import store

router = APIRouter(prefix="/api/data_explorer", tags=["data_explorer"])
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 4000 else value[:4000] + "…"
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, array.array):
        preview = ", ".join(f"{float(item):.4f}" for item in value[:6])
        return f"VECTOR({len(value)}) [{preview}{', …' if len(value) > 6 else ''}]"
    if isinstance(value, bytes):
        if len(value) == 16:
            return value.hex()
        preview = base64.b64encode(value[:48]).decode("ascii")
        return f"BINARY({len(value)}) {preview}{'…' if len(value) > 48 else ''}"
    if hasattr(value, "read"):
        return _json_value(value.read())
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump())
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        if len(value) > 16 and all(isinstance(item, (int, float)) for item in value):
            preview = ", ".join(f"{float(item):.4f}" for item in value[:6])
            return f"VECTOR({len(value)}) [{preview}, …]"
        return [_json_value(item) for item in value]
    return _json_value(str(value))


def _column_type(data_type: str, length: int | None, precision: int | None, scale: int | None) -> str:
    if data_type in {"VARCHAR2", "CHAR", "NVARCHAR2", "NCHAR", "RAW"} and length:
        return f"{data_type}({length})"
    if data_type == "NUMBER" and precision:
        return f"NUMBER({precision}{',' + str(scale) if scale is not None else ''})"
    return data_type


def _layer(table: str) -> str:
    name = table.lower()
    if name in {"conversation_memory", "summaries", "summary_message_links"}:
        return "episodic"
    if name in {"personas", "entity_memory", "knowledge_base"}:
        return "semantic"
    if name in {"toolbox", "workflow_memory", "skillbox", "tool_log"}:
        return "procedural"
    if name in {"short_term_memory", "semantic_cache"}:
        return "working"
    if name == "shared_memory":
        return "social"
    if name in {"agents", "agent_memories"}:
        return "durable definition"
    if name.startswith("automation_"):
        return "automation"
    return "MemoRizz system"


def _oracle_connection():
    store.initialize()
    if store.backend != "oracle":
        return None
    import oracledb

    return oracledb.connect(
        user=settings.oracle_user,
        password=settings.oracle_password,
        dsn=settings.oracle_dsn,
    )


def _filesystem_rows(table: str) -> list[dict[str, Any]]:
    from memorizz import MemoryType

    memory_type = next((item for item in MemoryType if item.value == table), None)
    if memory_type is None:
        return []
    try:
        values = store.require().list_all(memory_type) or []
    except Exception:
        return []
    rows = []
    for value in values:
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        elif not isinstance(value, dict) and hasattr(value, "__dict__"):
            value = vars(value)
        if not isinstance(value, dict):
            value = {"value": value}
        rows.append({str(key): _json_value(item) for key, item in value.items()})
    return rows


def _inferred_type(value: Any) -> str:
    if value is None:
        return "ANY"
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "NUMBER"
    if isinstance(value, (dict, list)):
        return "JSON"
    return "STRING"


def _filesystem_tables() -> list[dict[str, Any]]:
    from memorizz import MemoryType

    result = []
    for memory_type in MemoryType:
        rows = _filesystem_rows(memory_type.value)
        keys: list[str] = []
        for row in rows[:50]:
            for key in row:
                if key not in keys:
                    keys.append(key)
        columns = []
        for key in keys:
            sample = next((row.get(key) for row in rows if row.get(key) is not None), None)
            columns.append({
                "name": key,
                "type": _inferred_type(sample),
                "nullable": any(row.get(key) is None for row in rows),
                "primary_key": key in {"_id", "id"},
            })
        primary_keys = [column["name"] for column in columns if column["primary_key"]][:1]
        result.append({
            "name": memory_type.value,
            "row_count": len(rows),
            "columns": columns,
            "primary_keys": primary_keys,
            "layer": _layer(memory_type.value),
        })
    return result


def _oracle_tables(connection) -> list[dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT table_name FROM user_tables
               WHERE table_name NOT LIKE 'VECTOR$%'
                 AND table_name NOT LIKE 'DR$%'
               ORDER BY table_name"""
        )
        names = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            """SELECT table_name, column_name, data_type, nullable, column_id,
                      data_length, data_precision, data_scale
               FROM user_tab_columns
               WHERE table_name NOT LIKE 'VECTOR$%'
                 AND table_name NOT LIKE 'DR$%'
               ORDER BY table_name, column_id"""
        )
        columns_by_table: dict[str, list[dict[str, Any]]] = {name: [] for name in names}
        for table_name, column_name, data_type, nullable, _, length, precision, scale in cursor.fetchall():
            if table_name in columns_by_table:
                columns_by_table[table_name].append({
                    "name": column_name.lower(),
                    "type": _column_type(data_type, length, precision, scale),
                    "nullable": nullable == "Y",
                    "primary_key": False,
                })
        cursor.execute(
            """SELECT cols.table_name, cols.column_name, cols.position
               FROM user_constraints cons
               JOIN user_cons_columns cols ON cons.constraint_name = cols.constraint_name
               WHERE cons.constraint_type = 'P'
                 AND cols.table_name NOT LIKE 'VECTOR$%'
                 AND cols.table_name NOT LIKE 'DR$%'
               ORDER BY cols.table_name, cols.position"""
        )
        primary: dict[str, list[tuple[int, str]]] = {}
        for table_name, column_name, position in cursor.fetchall():
            primary.setdefault(table_name, []).append((position, column_name.lower()))
        for table_name, items in primary.items():
            wanted = {name for _, name in items}
            for column in columns_by_table.get(table_name, []):
                column["primary_key"] = column["name"] in wanted

        result = []
        for name in names:
            try:
                cursor.execute(f'SELECT COUNT(*) FROM "{name}"')
                row_count = int(cursor.fetchone()[0])
            except Exception:
                row_count = -1
            result.append({
                "name": name.lower(),
                "row_count": row_count,
                "columns": columns_by_table[name],
                "primary_keys": [column for _, column in primary.get(name, [])],
                "layer": _layer(name),
            })
        return result


def _catalog() -> tuple[str, str, list[dict[str, Any]]]:
    connection = _oracle_connection()
    if connection is None:
        return "filesystem", "MemoRizz files", _filesystem_tables()
    try:
        return "oracle", settings.oracle_user.upper(), _oracle_tables(connection)
    finally:
        connection.close()


def _definition(table: str) -> tuple[str, str, dict[str, Any]]:
    if not _IDENTIFIER.fullmatch(table):
        raise HTTPException(400, "Invalid table identifier")
    backend, schema, tables = _catalog()
    for item in tables:
        if item["name"].lower() == table.lower():
            return backend, schema, item
    raise HTTPException(404, "Table is not available in the active memory provider")


@router.get("/status")
def explorer_status():
    backend, schema, tables = _catalog()
    return {
        "ready": True,
        "backend": backend,
        "schema": schema,
        "tables": len(tables),
        "rows": sum(max(0, item["row_count"]) for item in tables),
        "stream": "/api/data_explorer/activity",
        "access": "read-only allowlisted browser",
    }


@router.get("/tables")
def tables():
    backend, schema, items = _catalog()
    return {"backend": backend, "schema": schema, "tables": items}


@router.get("/tables/{table}/rows")
def table_rows(table: str, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    backend, _, definition = _definition(table)
    primary_keys = definition["primary_keys"]
    if backend == "filesystem":
        rows = _filesystem_rows(definition["name"])[offset : offset + limit]
    else:
        connection = _oracle_connection()
        if connection is None:
            raise HTTPException(503, "Oracle became unavailable while reading the table")
        order = ",".join(f'"{name.upper()}"' for name in primary_keys) if primary_keys else "ROWID"
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f'SELECT * FROM "{table.upper()}" ORDER BY {order} '
                    "OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY",
                    {"offset": offset, "limit": limit},
                )
                names = [item[0].lower() for item in cursor.description]
                rows = [
                    {name: _json_value(value) for name, value in zip(names, row)}
                    for row in cursor.fetchall()
                ]
        finally:
            connection.close()
    row_keys = [
        "|".join(str(row.get(key, "")) for key in primary_keys)
        if primary_keys else str(offset + index + 1)
        for index, row in enumerate(rows)
    ]
    return {
        "table": definition["name"],
        "columns": definition["columns"],
        "primary_keys": primary_keys,
        "row_count": definition["row_count"],
        "offset": offset,
        "limit": limit,
        "rows": rows,
        "row_keys": row_keys,
    }


@router.get("/activity/recent")
def recent_activity(limit: int = Query(30, ge=1, le=100)):
    return {"events": activity.recent(limit)}


@router.get("/activity")
async def activity_stream(request: Request):
    async def generate():
        queue = activity.subscribe()
        try:
            yield {"event": "ready", "data": json.dumps({"status": "connected"})}
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield {"event": "transaction", "data": json.dumps(event)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": json.dumps({"status": "alive"})}
        finally:
            activity.unsubscribe(queue)

    return EventSourceResponse(generate())
