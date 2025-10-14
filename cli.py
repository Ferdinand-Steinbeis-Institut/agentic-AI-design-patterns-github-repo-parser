# cli.py
"""
Description: Main entrypoint to index repos and match patterns.

export GIT_LFS_SKIP_SMUDGE=1

Run:
  python cli.py --patterns PatternsListFinal.csv --list-file repos.txt
  python cli.py --patterns PatternsListFinal.csv @repos.txt
  python cli.py --patterns PatternsListFinal.csv https://github.com/<repo> ...
"""

import os
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
from db import db_connect, ensure_schema
from patterns import load_patterns_from_csv, embed_all_patterns
from ingest import ingest_repo
from repos_list import collect_urls


def main(argv=None):
    parser = argparse.ArgumentParser(description="Index repos and match patterns.")
    parser.add_argument("--patterns", help="CSV file with patterns", default=None)
    parser.add_argument("--list-file", "-f", help="Text file with one repo URL/path per line")
    parser.add_argument("repos", nargs="*", help="repo url(s) or local path(s) or @file")
    args = parser.parse_args(argv)

    # Ensure schema exists
    ensure_schema()

    # Load (and embed) patterns if CSV provided; otherwise use what’s already in DB
    if args.patterns:
        conn = db_connect()
        try:
            load_patterns_from_csv(conn, args.patterns)
            embed_all_patterns (conn)  # embeds now so downstream matches work
            conn.commit()
        finally:
            conn.close()
    else:
        print("No patterns CSV provided, using patterns already in DB.")

    # Collect repos from positional args, @files, and optional --list-file
    urls = collect_urls(
        [*args.repos, *(["--list-file", args.list_file] if args.list_file else [])]
    )
    if not urls:
        parser.error("No repositories provided. Use positional URLs/paths, @file, or --list-file.")

    # Ingest each repo
    for repo in urls:
        ingest_repo(repo)


if __name__ == "__main__":
    # Use a safe start method to avoid HF tokenizers + fork issues on macOS/Linux
    import multiprocessing as mp
    try:
        mp.set_start_method("spawn", force=True)
    except RuntimeError:
        # Start method was already set (e.g., by a parent); that's fine
        pass

    main()

