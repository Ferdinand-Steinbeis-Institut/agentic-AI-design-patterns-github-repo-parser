"""
ingest.py

Description: E2E ingestion pipeline for analyzing repositories and detecting
agentic AI patterns in their source code.

Pipeline:
1. Index repo files in the DB (files table), storing path, language, checksum.
2. Extract symbols using language parsers.
3. Store extracted symbols in the symbols table.
4. Compute embeddings for both patterns and symbols for semantic search.
5. Match patterns ↔ symbols using cosine similarity.
6. Insert hits into pattern_hits table.
7. ingest_repo(url) executes the whole pipeline for a given repo.
"""

import os
import json
import re
import hashlib

from gittools import git_clone_or_update
from file_index import sha256_bytes, detect_lang, snippet_hash
from parsers.python_parser import parse_python_symbols
from parsers.ipynb_parser import parse_ipynb_symbols
from parsers.generic import make_single_symbol
from db import db, upsert_repo
from embeddings import embeddings, embeddings_batch, loading_vectors, cosine_similarity, symbol_text


# ---------------------------------------------------------------------
# Indexing and symbol extraction
# ---------------------------------------------------------------------

def index_file(conn, repo_id: int, abs_path, rel_path: str, lang: str):
    digest = sha256_bytes(abs_path)
    conn.execute("""
        INSERT INTO files(repo_id, path, rel_path, lang, sha256)
        VALUES(?,?,?,?,?)
    """, (repo_id, str(abs_path), rel_path, lang, digest))
    cur = conn.execute("SELECT last_insert_rowid()")
    return cur.fetchone()[0]


def upsert_symbols(conn, file_id: int, symbols):
    for s in symbols:
        conn.execute("""
            INSERT INTO symbols(file_id, kind, name, lineno, end_lineno, signature,
                                docstring, parent_name, source)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (
            file_id, s["kind"], s["name"], s["lineno"], s["end_lineno"],
            s["signature"], s["docstring"], s["parent_name"], s.get("source", "")
        ))


# ---------------------------------------------------------------------
# Keyword scan (legacy, optional)
# ---------------------------------------------------------------------

def pattern_scan(conn):
    patterns = conn.execute("SELECT id, name, indicators_json FROM patterns").fetchall()
    if not patterns:
        return

    rows = conn.execute("""
        SELECT s.id, s.name, s.kind, s.docstring, s.source, f.repo_id
        FROM symbols s
        JOIN files  f ON f.id = s.file_id
    """).fetchall()

    for (sym_id, name, kind, doc, src, repo_id) in rows:
        text = " ".join([name or "", doc or ""]).lower()
        for (pid, pname, indicators_json) in patterns:
            try:
                inds = json.loads(indicators_json or "[]")
            except Exception:
                inds = []
            reasons = [w for w in inds if w and w.lower() in text]
            if reasons:
                code_snippet = src
                h = snippet_hash(code_snippet)
                conn.execute("""
                    INSERT OR IGNORE INTO pattern_hits
                      (pattern_id, pattern_name, symbol_id, reason, code_snippet, snippet_hash, repo_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    pid, pname, sym_id,
                    f"matched: {', '.join(sorted(set(reasons)))}",
                    code_snippet, h, repo_id
                ))


#########################################################
# Helpers for batching, caching, and filters
#########################################################

def _chunks(lst, n):
    """Yield successive n-sized chunks from a list."""
    for i in range(0, len(lst), n):
        yield lst[i:i+n]


def _hash_text(t: str) -> str:
    return hashlib.sha256((t or "").encode("utf-8")).hexdigest()


def _too_small(name, doc, src):
    L = len((doc or "")) + len((src or ""))
    return L < int(os.getenv("EMBED_MIN_LEN", "120"))  # skip tiny symbols


# ---------------------------------------------------------------------
# Embedding utilities
# ---------------------------------------------------------------------

def embed_symbols_for_repo(conn, repo_id: int):
    """Compute embeddings for all symbols in a given repo (batched + cached)."""
    rows = conn.execute("""
        SELECT s.id, s.name, s.kind, s.docstring, s.source
        FROM symbols s
        JOIN files f ON s.file_id = f.id
        WHERE f.repo_id = ? AND (s.embedding_json IS NULL OR s.embedding_json = '')
    """, (repo_id,)).fetchall()

    if not rows:
        return

    # Filter out tiny symbols
    rows = [r for r in rows if not _too_small(r[1], r[3], r[4])]
    if not rows:
        return

    # Ensure cache table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS embeddings_cache(
            text_hash TEXT PRIMARY KEY,
            embedding_json TEXT
        )
    """)

    # Precompute texts + hashes
    records = []
    for (sid, name, kind, doc, src) in rows:
        text = symbol_text(name, kind, doc, src)
        if not text:
            continue
        th = _hash_text(text)
        records.append((sid, text, th))

    if not records:
        return

    # Lookup cached embeddings
    hashes = tuple(r[2] for r in records)
    cached = {}
    if hashes:
        q = f"SELECT text_hash, embedding_json FROM embeddings_cache WHERE text_hash IN ({','.join('?'*len(hashes))})"
        cached = dict(conn.execute(q, hashes).fetchall())

    to_embed = [(sid, txt, th) for (sid, txt, th) in records if th not in cached]
    chunk = int(os.getenv("EMBED_CHUNK", "512"))

    # Embed missing ones
    for block in _chunks(to_embed, chunk):
        texts = [txt for (_, txt, _) in block]
        vecs = embeddings_batch(texts)
        conn.executemany(
            "INSERT OR REPLACE INTO embeddings_cache(text_hash, embedding_json) VALUES(?,?)",
            [(th, ej) for ((_, _, th), ej) in zip(block, vecs)]
        )
        if os.getenv("EMBED_VERBOSE","0") == "1":
            print(f"[ingest] repo {repo_id}: newly embedded {len(block)} symbols")

    # Update all symbols from cache
    updates = []
    for (sid, _, th) in records:
        ej = cached.get(th)
        if ej is None:
            row = conn.execute("SELECT embedding_json FROM embeddings_cache WHERE text_hash=?", (th,)).fetchone()
            ej = row[0] if row else None
        updates.append((ej, sid))

    conn.executemany("UPDATE symbols SET embedding_json=? WHERE id=?", updates)

    if os.getenv("EMBED_VERBOSE","0") == "1":
        print(f"[ingest] repo {repo_id}: total {len(records)}, cached {len(records)-len(to_embed)}, newly embedded {len(to_embed)}")


# ---------------------------------------------------------------------
# Semantic matching (patterns ↔ symbols)
# ---------------------------------------------------------------------

WORD = re.compile(r"\b\w+\b", re.IGNORECASE)

def has_any_indicator_wholeword(text: str, indicators) -> bool:
    if not indicators:
        return True
    txt = text or ""
    for word in indicators:
        word = (word or "").strip()
        if not word:
            continue
        if re.search(rf"\b{re.escape(word)}\b", txt, flags=re.IGNORECASE):
            return True
    return False


def semantic_match(conn, topk: int = 50, min_cos: float = 0.45):
    """Perform semantic similarity matching between patterns and symbols."""
    pats = conn.execute("""
        SELECT id, name, description, indicators_json, embedding_json
        FROM patterns
    """).fetchall()

    syms = conn.execute("""
        SELECT s.id, s.name, s.kind, s.docstring, s.source, s.embedding_json, f.repo_id
        FROM symbols s
        JOIN files f ON f.id = s.file_id
        WHERE s.embedding_json IS NOT NULL AND s.embedding_json <> ''
    """).fetchall()

    symbol_vectors = []
    for (sid, name, kind, doc, src, svj, repo_id) in syms:
        sv = loading_vectors(svj)
        if sv is None:
            continue
        symbol_vectors.append((sid, name, kind, doc, src, sv, repo_id))

    for (pid, pname, pdesc, inds_json, pvj) in pats:
        pv = loading_vectors(pvj)
        if pv is None:
            continue
        try:
            indicators = json.loads(inds_json or "[]")
        except Exception:
            indicators = []

        scored = []
        for (sid, name, kind, doc, src, sv, repo_id) in symbol_vectors:
            score = cosine_similarity(pv, sv)
            if score >= min_cos:
                scored.append((score, sid, name, kind, doc, src, repo_id))

        scored.sort(reverse=True, key=lambda x: x[0])
        candidates = scored[:topk]

        for (score, sid, name, kind, doc, src, repo_id) in candidates:
            text_for_check = " ".join([name or "", doc or "", src or ""])
            if not has_any_indicator_wholeword(text_for_check, indicators):
                continue
            reason = f"semantic={score:.2f}"
            code_snippet = (src or "")[:8000]
            h = snippet_hash(code_snippet)
            conn.execute("""
                INSERT OR IGNORE INTO pattern_hits
                    (pattern_id, pattern_name, symbol_id, reason, code_snippet, snippet_hash, repo_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (pid, pname, sid, reason, code_snippet, h, repo_id))


# ---------------------------------------------------------------------
# End-to-end ingestion
# ---------------------------------------------------------------------

def ingest_repo(url: str):
    """Main pipeline to clone, index, parse, embed, and match patterns for a repo."""
    repo_root = git_clone_or_update(url)

    with db() as conn:
        repo_id = upsert_repo(conn, url, repo_root)

        # Clear old data for this repo
        conn.execute("""
            DELETE FROM pattern_hits
            WHERE symbol_id IN (
                SELECT id FROM symbols
                WHERE file_id IN (SELECT id FROM files WHERE repo_id=?)
            )
        """, (repo_id,))
        conn.execute("""
            DELETE FROM symbols
            WHERE file_id IN (SELECT id FROM files WHERE repo_id=?)
        """, (repo_id,))
        conn.execute("DELETE FROM files WHERE repo_id=?", (repo_id,))

        # Ensure embedding_json columns
        for table in ("symbols", "patterns"):
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if "embedding_json" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN embedding_json TEXT")

        # Walk repo files
        for file_paths in repo_root.rglob("*"):
            if not file_paths.is_file() or ".git" in file_paths.parts:
                continue
            lang = detect_lang(file_paths)
            if lang == "unknown":
                continue

            relative_path = str(file_paths.relative_to(repo_root))
            file_id = index_file(conn, repo_id, file_paths, relative_path, lang)

            try:
                src = file_paths.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            try:
                if lang == "python":
                    symbols = parse_python_symbols(src)
                    upsert_symbols(conn, file_id, symbols)
                elif lang == "ipynb":
                    symbols = parse_ipynb_symbols(src)
                    if symbols:
                        upsert_symbols(conn, file_id, symbols)
                elif lang in ("yaml", "json", "toml", "ini", "dockerfile", "requirements"):
                    symbols = make_single_symbol("config", relative_path, src)
                    upsert_symbols(conn, file_id, symbols)
                elif lang in ("markdown", "text"):
                    symbols = make_single_symbol("doc", relative_path, src)
                    upsert_symbols(conn, file_id, symbols)
            except Exception as e:
                print(f"[WARN] Skipping {relative_path} ({e})")

        # Run analyses
        pattern_scan(conn)
        embed_symbols_for_repo(conn, repo_id)
        semantic_match(conn, topk=50, min_cos=0.45)

        if os.getenv("EMBED_VERBOSE", "0") == "1":
            print(f"[ingest] Finished {url} (repo_id={repo_id})")



