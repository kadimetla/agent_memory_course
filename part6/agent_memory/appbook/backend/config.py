"""Central configuration for the Agent Memory Stack app.

Loads environment variables (OpenAI key, optional Oracle credentials) and exposes
a single ``settings`` object the rest of the backend imports. The app is the
interactive companion to ``agent_memory_zero_to_hero.ipynb`` and is powered by the
**memorizz** framework, so the LLM + embedding choices mirror the notebook
(OpenAI ``gpt-5.6-luna`` + ``text-embedding-3-small`` @ 256 dims).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
APP_DIR = Path(__file__).resolve().parent.parent           # .../appbook
BACKEND_DIR = APP_DIR / "backend"
FRONTEND_DIR = APP_DIR / "frontend"

# Load the most specific file first. Existing process variables always win, so a
# shell/CI override is never silently replaced by a checked-out .env file.
for candidate in (APP_DIR / ".env", APP_DIR.parent / ".env", APP_DIR.parent.parent / ".env"):
    if candidate.exists():
        load_dotenv(candidate, override=False)


class Settings:
    """Immutable-ish runtime settings, read once at import."""

    # OpenAI / model — one model string used everywhere, mirroring the notebook.
    openai_api_key: str | None = os.environ.get("OPENAI_API_KEY")
    model: str = os.environ.get("AMEM_MODEL", "gpt-5.6-luna")
    max_tokens: int = int(os.environ.get("AMEM_MAX_TOKENS", "1024"))

    # Embeddings (OpenAI) — same model + dimension as the notebook's Memory Core.
    embed_model: str = os.environ.get("AMEM_EMBED_MODEL", "text-embedding-3-small")
    embed_dimensions: int = int(os.environ.get("AMEM_EMBED_DIMENSIONS", "256"))

    # Oracle AI Database (optional). If unreachable, memorizz falls back to its
    # FileSystemProvider (FAISS) so the whole app still runs locally.
    oracle_user: str = os.environ.get("ORACLE_USER", "VECTOR")
    oracle_password: str = os.environ.get("ORACLE_PASSWORD", "VectorPwd_2025")
    oracle_dsn: str = os.environ.get("ORACLE_DSN", "localhost:1521/FREEPDB1")
    oracle_enabled: bool = os.environ.get("ORACLE_ENABLED", "1") not in {"0", "false", "False"}

    # Exact-search FileSystemProvider fallback location (used when Oracle is
    # unset or unreachable). The small course corpus deliberately avoids FAISS.
    fs_root: str = os.environ.get(
        "AMEM_FS_ROOT", str(APP_DIR / ".data" / "memorizz")
    )


settings = Settings()

# Make memorizz's embedding defaults consistent across every client (provider,
# knowledge base, entity memory) — same trick the notebook uses in §0.3.
os.environ.setdefault("MEMORIZZ_DEFAULT_EMBEDDING_PROVIDER", "openai")
os.environ.setdefault("MEMORIZZ_DEFAULT_EMBEDDING_MODEL", settings.embed_model)
os.environ.setdefault("MEMORIZZ_DEFAULT_EMBEDDING_DIMENSIONS", str(settings.embed_dimensions))
