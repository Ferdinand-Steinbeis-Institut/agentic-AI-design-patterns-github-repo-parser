""" db.py 

Description

This script is responsible for:
1. Database connections
- Opens and configures SQLite connections (db, db_connect) 
- Applies concurrency-friendly pragmas (WAL journaling, busy timeouts)

2. Schema management and migrations
- Defines and ensures the core schema (repos, files, symbols, patterns, pattern_hits)
- Adds new columns if missing (for chanity check with new column migrations)
- Cleans duplicates and enforces uniqueness constraints across runs
- Provides convenience view (pattern_hits_enriched) for easier joins (providing repo_name).

3. Repository metadata management
- Handles insertion/upsertion of repos (upsert_repo)
- Recovers repo branch name via git rev-parse

4. Helper queries
- Look up repo_id from a given symbol_id (get_repo_id_for_symbol)

"""

import sqlite3
import subprocess
import time
from pathlib import Path
from file_index import snippet_hash

#import our constants 
from constants import (
    DB_PATH, 
    SCHEMA,
)

##################### DB Helpers ####################

def configure(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Apply pragmas for concurrency."""
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


#context manager style connection
def db():
    conn = sqlite3.connect(DB_PATH, timeout=60)
    return configure(conn)

#open raw connection
def db_connect(path=DB_PATH):
    conn = sqlite3.connect(path, timeout=60)
    return configure(conn)

#################### Ensure Schema - Sanity checks for new columns ###################
# mostly sanity checks after incorporating more columns 

def ensure_schema():
    """Create or migrate schema."""
    with db() as conn:
        #first create base schema
        conn.executescript(SCHEMA)

        #in symbols table add: source, embedding_json in case the are missing
        cols = {r[1] for r in conn.execute("PRAGMA table_info(symbols)").fetchall()}
        if "source" not in cols:
            conn.execute("ALTER TABLE symbols ADD COLUMN source TEXT")
        if "embedding_json" not in cols:
            conn.execute("ALTER TABLE symbols ADD COLUMN embedding_json TEXT")

        #in patterns table: add extra columns from csv file with patterns (maybe will be needed for further analysis)
        patterns_cols = {r[1] for r in conn.execute("PRAGMA table_info(patterns)").fetchall()}
        for col in ("motivation", "solution", "alias", "sub_category", "category",
                    "resources", "link", "ptype", "comments", "embedding_json"):
            if col not in patterns_cols:
                conn.execute(f"ALTER TABLE patterns ADD COLUMN {col} TEXT")

        #in pattern_hits table: ensure the newer columns exist for older DBs (prob not needed with new runs)
        ph_cols = {r[1] for r in conn.execute("PRAGMA table_info(pattern_hits)").fetchall()}
        if "code_snippet" not in ph_cols:
            conn.execute("ALTER TABLE pattern_hits ADD COLUMN code_snippet TEXT")
        if "pattern_name" not in ph_cols:
            conn.execute("ALTER TABLE pattern_hits ADD COLUMN pattern_name TEXT")
        if "snippet_hash" not in ph_cols:
            conn.execute("ALTER TABLE pattern_hits ADD COLUMN snippet_hash TEXT")

        #backfill snippet_hash if missing
        rows = conn.execute("""
            SELECT id, code_snippet
            FROM pattern_hits
            WHERE (snippet_hash IS NULL OR snippet_hash = '') AND code_snippet IS NOT NULL
        """).fetchall()
        for _id, cs in rows:
            conn.execute("UPDATE pattern_hits SET snippet_hash=? WHERE id=?",
                         (snippet_hash(cs), _id))

        #deal with the retrieval of duplicate symbols under same pattern name
        conn.execute("""
        DELETE FROM pattern_hits
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM pattern_hits
            GROUP BY pattern_id, snippet_hash, repo_id
        )
        """)

        #enforce uniqueness (repo-aware indexes)
        conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_ph_pattern_snippet_repo
        ON pattern_hits(pattern_id, snippet_hash, repo_id)
        """)

        #helpful indexes (idempotent)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_files_repo_id ON files(repo_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_symbols_file_id ON symbols(file_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pattern_hits_repo_id ON pattern_hits(repo_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pattern_hits_symbol_id ON pattern_hits(symbol_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pattern_hits_pattern_id ON pattern_hits(pattern_id)")

        #View for easer and enriched pattern_hits, by adding repo_name join - can delete 
        conn.execute("""
        CREATE VIEW IF NOT EXISTS pattern_hits_enriched AS
        SELECT
          ph.*,
          r.name AS repo_name,
          r.url  AS repo_url
        FROM pattern_hits ph
        JOIN repos r ON r.id = ph.repo_id
        """)

#get the repo_id for every code snippet
def get_repo_id_for_symbol(conn, symbol_id: int) -> int:
    cur = conn.execute(
        """
        SELECT r.id
        FROM symbols s
        JOIN files f ON f.id = s.file_id
        JOIN repos r ON r.id = f.repo_id
        WHERE s.id = ?
        """,
        (symbol_id,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"No repo found for symbol_id={symbol_id}")
    return int(row[0])


#################### Repository Management ####################

#helper for locked db errors
def retry_locked(callable_, retries=6, base_delay=0.25):
    for i in range(retries):
        try:
            return callable_()
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower():
                time.sleep(base_delay * (2 ** i))
                continue
            raise

#insert or update repo row, return repo_id
def upsert_repo(conn, url: str, path: Path) -> int:
    name = path.name
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True, capture_output=True, text=True
        )
        branch = out.stdout.strip()
    except Exception:
        branch = None
    ts = int(time.time())

    def do():
        conn.execute("""
            INSERT INTO repos(url, name, local_path, default_branch, last_sync_ts)
            VALUES(?,?,?,?,?)
            ON CONFLICT(url) DO UPDATE SET local_path=excluded.local_path,
                                          default_branch=excluded.default_branch,
                                          last_sync_ts=excluded.last_sync_ts
        """, (url, name, str(path), branch, ts))
        return conn.execute("SELECT id FROM repos WHERE url=?", (url,)).fetchone()[0]

    return retry_locked(do)
