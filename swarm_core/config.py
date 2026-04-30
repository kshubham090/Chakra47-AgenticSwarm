from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise OSError(f"Missing required env var: {key}. Copy .env.example → .env and fill it in.")
    return value


# Supabase vars are optional at import time; AuditChain validates them on connect.
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:30b-a3b")
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
