# Agentic AI Pattern Detection in Repositories 

Aim of the Project:

# Code Structure

Folder_Name/
├─ parsers/
│  ├─ generic.py          # helpers
│  ├─ ipynb_parser.py     # extracts symbols from .ipynb cells
│  └─ python_parser.py    # AST-based extractor for classes/functions/methods
├─ repos_cache/           # local clones of analyzed repos
├─ __init__.py
├─ cli.py                 # entrypoint (CLI): schema init, load patterns, ingest repos
├─ constants.py           # configuration 
├─ db.py                  # DB connection, schema migrations, repo upsert
├─ embeddings.py          # embed text, load vectors, cosine similarity, symbol_text
├─ file_index.py          # detect_lang, sha256_bytes, snippet_hash
├─ gittools.py            # git_clone_or_update (shallow clone + fetch/pull)
├─ ingest.py              # e2e pipeline: indexes files, gets symbols, gets embeddings, finds matches
├─ patterns.py            # load_patterns_from_csv, helpers for patterns table
├─ PatternsListFinal.csv  # pattern catalog
├─ repos_list.py          # supports --list-file and @file shorthand for repos
├─ repos.txt              # list of repos
├─ requirements.txt

# Setup 
First, clone the repository:

``` git clone https://github.com/<repo-url> ```

## Create Virtual Environment: 

For this you need conda or miniconda installed and python 3.12

```cd``` in the cloned repository directory and run the following commands: 

``` conda create -n repo-parser python=3.12.7 -y ``` 

``` conda activate repo-parser ```

``` pip install -r requirements.txt ```


For running it on mac with .venv:
``` python3.12 -m venv .venv ```
``` source .venv/bin/activate ```
``` pip install -r requirements.txt ```

On pip run: ``` export EMBED_VERBOSE=1 export GIT_LFS_SKIP_SMUDGE=1 export EMBED_BATCH=16 python cli.py --patterns PatternsListFinal.csv --list-file repos.txt ```

To set it up on uv:
``` uv venv ```
``` source .venv/bin/activate ```
``` uv pip install sentence-transformers ```


Env settings to prevent the crash using mps

``` export EMBED_DEVICE=mps ``` 
``` export EMBED_BATCH=1 ```
``` export EMBED_MAX_TOKENS=512 ```

On uv run: ``` EMBED_VERBOSE=1 EMBED_BATCH=16 GIT_LFS_SKIP_SMUDGE=1 uv run python cli.py --patterns PatternsListFinal.csv --list-file repos.txt ``` 




## [IGNORE] Run on cli with: 

``` python cli.py --patterns PatternsListFinal.csv --list-file repos.txt ```

or 

``` python cli.py --patterns PatternsListFinal.csv @repos.txt ```


If you want (a) specific repositories(-y) : 
``` python cli.py --patterns PatternsListFinal.csv https://github.com/<repo-url>  https://github.com/<repo-url> ... ```
