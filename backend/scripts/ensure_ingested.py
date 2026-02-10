# Copyright 2026 Piotr Synak
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Purpose:
# Ensure the knowledge base is ingested into Postgres.
#
# Behavior:
# - If `knowledge_chunks` already has rows AND the knowledge hash is unchanged, it exits successfully (no-op).
# - If empty (or table missing), it runs `scripts/ingest_cards.py`.
# - If the knowledge hash changed since last run, it runs `scripts/ingest_cards.py` again.
# - Set FORCE_REINGEST=1 to force a rebuild (will TRUNCATE + reinsert).

from __future__ import annotations

import hashlib
import os
import runpy
import time
from pathlib import Path

import psycopg

INGEST_LOCK_ID = 684321002  # arbitrary constant


def _wait_for_db(database_url: str, *, timeout_s: float = 60.0) -> None:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with psycopg.connect(database_url):
                return
        except Exception as exc:
            last_error = exc
            time.sleep(1.0)
    raise RuntimeError(f"Database not reachable within {timeout_s}s") from last_error


def _get_count(database_url: str) -> int:
    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM knowledge_chunks;")
                return int(cursor.fetchone()[0])
    except Exception:
        # If the table doesn't exist yet, treat as empty.
        return 0


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _compute_knowledge_hash(knowledge_root: Path) -> str:
    """Compute a stable hash of the knowledge directory contents.

    Hash includes relative file paths + file contents for all files under
    `knowledge_root`.
    """

    hasher = hashlib.sha256()
    if not knowledge_root.exists():
        return hasher.hexdigest()

    files = [p for p in knowledge_root.rglob("*") if p.is_file()]
    files.sort(key=lambda p: str(p.relative_to(knowledge_root)).replace("\\", "/"))

    for path in files:
        rel = str(path.relative_to(knowledge_root)).replace("\\", "/")
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")

    return hasher.hexdigest()


def _ensure_ingestion_state_table(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_ingestion_state (
                    id INTEGER PRIMARY KEY,
                    knowledge_hash_sha256 TEXT NOT NULL,
                    embeddings_provider TEXT NOT NULL,
                    embeddings_model TEXT,
                    embeddings_dimensions INTEGER NOT NULL,
                    cards_count INTEGER,
                    chunks_count INTEGER,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )
        conn.commit()


def _load_ingestion_state(database_url: str) -> dict | None:
    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT knowledge_hash_sha256,
                           embeddings_provider,
                           embeddings_model,
                           embeddings_dimensions
                    FROM knowledge_ingestion_state
                    WHERE id = 1;
                    """
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return {
                    "knowledge_hash_sha256": str(row[0]),
                    "embeddings_provider": str(row[1]),
                    "embeddings_model": row[2] if row[2] is None else str(row[2]),
                    "embeddings_dimensions": int(row[3]),
                }
    except Exception:
        return None


def _update_ingestion_state(
    *,
    database_url: str,
    knowledge_hash_sha256: str,
    embeddings_provider: str,
    embeddings_model: str | None,
    embeddings_dimensions: int,
) -> None:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO knowledge_ingestion_state (
                    id,
                    knowledge_hash_sha256,
                    embeddings_provider,
                    embeddings_model,
                    embeddings_dimensions,
                    cards_count,
                    chunks_count
                )
                VALUES (
                    1, %s, %s, %s, %s,
                    (SELECT COUNT(DISTINCT card_id) FROM knowledge_chunks),
                    (SELECT COUNT(*) FROM knowledge_chunks)
                )
                ON CONFLICT (id)
                DO UPDATE SET
                    knowledge_hash_sha256 = EXCLUDED.knowledge_hash_sha256,
                    embeddings_provider = EXCLUDED.embeddings_provider,
                    embeddings_model = EXCLUDED.embeddings_model,
                    embeddings_dimensions = EXCLUDED.embeddings_dimensions,
                    cards_count = EXCLUDED.cards_count,
                    chunks_count = EXCLUDED.chunks_count,
                    updated_at = now();
                """,
                (
                    knowledge_hash_sha256,
                    embeddings_provider,
                    embeddings_model,
                    embeddings_dimensions,
                ),
            )
        conn.commit()


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required.")

    _wait_for_db(database_url)

    force = (os.getenv("FORCE_REINGEST") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    count = _get_count(database_url)

    embeddings_provider = (os.getenv("EMBEDDINGS_PROVIDER") or "").strip() or "stub"
    embeddings_model = (os.getenv("EMBEDDINGS_MODEL") or "").strip() or None
    try:
        embeddings_dimensions = int(os.getenv("EMBEDDINGS_DIMENSIONS") or "1536")
    except Exception:
        embeddings_dimensions = 1536

    knowledge_root = Path("/knowledge")
    current_hash = _compute_knowledge_hash(knowledge_root)

    # Single-runner safety (important with multiple backend replicas).
    # Advisory locks are session-scoped, so we must keep the connection open.
    lock_conn = psycopg.connect(database_url)
    try:
        with lock_conn.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s);", (INGEST_LOCK_ID,))
        lock_conn.commit()

        _ensure_ingestion_state_table(database_url)
        previous_state = _load_ingestion_state(database_url)

        state_matches = (
            previous_state is not None
            and previous_state.get("knowledge_hash_sha256") == current_hash
            and previous_state.get("embeddings_provider") == embeddings_provider
            and (previous_state.get("embeddings_model") or None) == embeddings_model
            and int(previous_state.get("embeddings_dimensions"))
            == embeddings_dimensions
        )

        if count > 0 and state_matches and not force:
            print(
                f"knowledge_chunks already populated (rows={count}) and knowledge hash unchanged. Skipping ingest. "
                "Set FORCE_REINGEST=1 to force a rebuild.",
                flush=True,
            )
            return

        script_dir = Path(__file__).resolve().parent
        ingest_path = script_dir / "ingest_cards.py"
        if not ingest_path.exists():
            raise RuntimeError(f"ingest_cards.py not found at {ingest_path}")

        # Run the ingestion script as if it was executed directly.
        # This avoids relying on `scripts` being a Python package.
        runpy.run_path(str(ingest_path), run_name="__main__")

        # Persist the new ingestion state (best-effort).
        try:
            _update_ingestion_state(
                database_url=database_url,
                knowledge_hash_sha256=current_hash,
                embeddings_provider=embeddings_provider,
                embeddings_model=embeddings_model,
                embeddings_dimensions=embeddings_dimensions,
            )
        except Exception as exc:
            print(
                f"Warning: failed to persist knowledge_ingestion_state: {exc}",
                flush=True,
            )
    finally:
        try:
            with lock_conn.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s);", (INGEST_LOCK_ID,))
            lock_conn.commit()
        except Exception:
            pass
        lock_conn.close()


if __name__ == "__main__":
    main()
