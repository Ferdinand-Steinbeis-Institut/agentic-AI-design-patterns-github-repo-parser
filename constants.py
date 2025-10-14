""" 
constants.py

Description: Creating a database in sqlite to store all the repositories and parse them.

Database schema: 5 tables 

files: id | repo_id | path | rel_path | lang | sha256 
pattern_hits: id | pattern_id | pattern_name | symbol_id | reason | code_snippet | snippet_hash | repo_id
patterns: id | name | description | indicators_json | embedding_json | motivation | solution | alias | sub_category | category | resources | link  | ptype | comments
repos: id | url | name | local_path | default_branch | last_sync_ts
symbols: id | file_id | kind | name | lineno | end_lineno | signature | docstring | parent_name | source | embedding_json 

"""

from pathlib import Path

# setting the database using sqlite,  and also the directory for storing in cache all the repos
DB_PATH = "repos_index.sqlite3"
CACHE_DIR = Path("repos_cache").resolve()
CACHE_DIR = Path("C:/repos_cache") 

PY_EXT = {".py"}

# the files we want to take into consideration during parsing the repositories that we think have important information
# about agentic pattern initialization

SPECIAL_FILENAMES = {
    "Dockerfile": "dockerfile",
    "requirements.txt": "requirements",
    "environment.yml": "yaml",
    "environment.yaml": "yaml",
    "pyproject.toml": "toml",
    "README.md": "markdown",
}

TEXT_LANG_BY_SUFFIX = {
    ".ipynb": "ipynb",
    ".md": "markdown",
    ".txt": "text",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
}

SCHEMA = """ 
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS repos(
  id INTEGER PRIMARY KEY,
  url TEXT UNIQUE,
  name TEXT,
  local_path TEXT,
  default_branch TEXT,
  last_sync_ts INTEGER
);

CREATE TABLE IF NOT EXISTS files(
  id INTEGER PRIMARY KEY,
  repo_id INTEGER,
  path TEXT,
  rel_path TEXT,
  lang TEXT,
  sha256 TEXT,
  FOREIGN KEY(repo_id) REFERENCES repos(id)
);

CREATE TABLE IF NOT EXISTS symbols(
  id INTEGER PRIMARY KEY,
  file_id INTEGER,
  kind TEXT,
  name TEXT,
  lineno INTEGER,
  end_lineno INTEGER,
  signature TEXT,
  docstring TEXT,
  parent_name TEXT,
  source TEXT,
  embedding_json TEXT,
  FOREIGN KEY(file_id) REFERENCES files(id)
);

CREATE TABLE IF NOT EXISTS patterns(
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE,
  description TEXT,
  indicators_json TEXT,
  embedding_json TEXT,
  motivation TEXT,
  solution TEXT,
  alias TEXT,
  sub_category TEXT,
  category TEXT,
  resources TEXT,
  link TEXT,
  ptype TEXT,
  comments TEXT
);

CREATE TABLE IF NOT EXISTS pattern_hits(
  id INTEGER PRIMARY KEY,
  pattern_id INTEGER,
  pattern_name TEXT,
  symbol_id INTEGER,
  reason TEXT,
  code_snippet TEXT,
  snippet_hash TEXT,
  repo_id INTEGER,
  FOREIGN KEY(pattern_id) REFERENCES patterns(id),
  FOREIGN KEY(symbol_id) REFERENCES symbols(id),
  FOREIGN KEY(repo_id) REFERENCES repos(id)
);
"""
