"""
patterns.py 

Description: Read the sheet with the Pattern Catalogue in CSV or Excel format and create the table in the DB based on column names


"""

import json
from embeddings import embeddings, embeddings_batch
import pandas as pd
import os
import re as _re

#################### Function to load our full Pattern Catalogue ####################

#load patterns from a CSV or Excel with set columns:
#have the following columns: Pattern Name, Description, Alias, Sub category, Category, Motivation, Solution, Resources, Link, Type, Comments.
#embeddings are computed from Description + Motivation + Solution and have Pattern Name mandatory 

def load_patterns_from_csv(conn, csv_path: str):
    ext = os.path.splitext(csv_path)[1].lower()

    def read_csv_safely(path):
        #try a few common encodings and auto-delimiter detection
        encodings = ["utf-8-sig", "utf-8", "cp1252"]
        for enc in encodings:
            try:
                return pd.read_csv(
                    path,
                    encoding=enc,
                    sep=None,
                    engine="python",
                    dtype=str,              # keep everything as text
                    keep_default_na=False,  # don't turn blanks into NaN
                )
            except Exception:
                continue

        #last resorts with explicit separators
        for sep in [",", ";", "\t", "|"]:
            try:
                return pd.read_csv(
                    path,
                    encoding="utf-8-sig",
                    sep=sep,
                    engine="python",
                    dtype=str,
                    keep_default_na=False,
                )
            except Exception:
                continue
        raise ValueError("Failed to parse CSV with common encodings/separators. Check the file format.")
    
    #deal with excel format
    if ext in [".xlsx", ".xlsm", ".xls"]:
        sheet = pd.read_excel(csv_path, dtype=str).fillna("")
    else:
        sheet = read_csv_safely(csv_path).fillna("")

    df = sheet
    #normalizing the headers
    def normalize_column(column):
        return _re.sub(r"\s+", "_", str(column).strip().lower())
    df.columns = [normalize_column(column) for column in df.columns]

    column_map = {
        "pattern_name": "name",
        "name": "name",
        "description": "description",
        "motivation": "motivation",
        "solution": "solution",
        "alias": "alias",
        "sub_category": "sub_category",
        "subcategory": "sub_category",
        "category": "category",
        "resources": "resources",
        "link": "link",
        "url": "link",
        "type": "ptype",   
        "comments": "comments",
        "comment": "comments",
    }

    keep = {}
    for column in df.columns:
        if column in column_map:
            keep[column_map[column]] = df[column].astype(str)

    word = pd.DataFrame(keep)
    if "name" not in word.columns:
        raise ValueError("The file must include a 'Pattern Name' (or a 'name') column.")

    #ensure all expected columns present
    text_cols = ["description","motivation","solution","alias","sub_category",
                 "category","resources","link","ptype","comments"]
    for col in text_cols:
        if col not in word.columns:
            word[col] = ""

    def clean_pattern_name(name: str) -> str:
        name = _re.sub(r"[\[\(]\s*\d+[a-zA-Z]*\s*[\]\)]", "", name)
        name = _re.sub(r"\s{2,}", " ", name)
        return name.strip()        
    

    #upsert rows + build embeddings from desc+mot+sol
    for _, r in word.iterrows():
        raw_name = str(r["name"]).strip()
        name = clean_pattern_name(raw_name)
        if not name:
            continue 
        description = str(r["description"]).strip()
        motivation  = str(r["motivation"]).strip()
        solution    = str(r["solution"]).strip()

        if not name:
            continue  # skip blank names

        embedding_text = " | ".join([text for text in [description, motivation, solution, name] if text])
        embedding_json = embeddings(embedding_text) if embedding_text else None
        indicators = json.dumps([])  # no keyword gating by default

        conn.execute(
            """
            INSERT INTO patterns(name, description, motivation, solution, alias, sub_category, category,
                                 resources, link, ptype, comments, indicators_json, embedding_json)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
                description     = excluded.description,
                motivation      = excluded.motivation,
                solution        = excluded.solution,
                alias           = excluded.alias,
                sub_category    = excluded.sub_category,
                category        = excluded.category,
                resources       = excluded.resources,
                link            = excluded.link,
                ptype           = excluded.ptype,
                comments        = excluded.comments,
                indicators_json = excluded.indicators_json,
                embedding_json  = excluded.embedding_json
            """,
            (name, description, motivation, solution,
             r["alias"], r["sub_category"], r["category"],
             r["resources"], r["link"], r["ptype"], r["comments"],
             indicators, embedding_json)
        )

# patterns.py
import json

def embed_all_patterns(conn):
    rows = conn.execute(
        "SELECT id, description, motivation, solution, name FROM patterns"
    ).fetchall()
    if not rows:
        return

    texts = []
    ids = []
    for pid, desc, mot, sol, name in rows:
        text = " | ".join([t for t in [name or "", desc or "", mot or "", sol or ""] if t]).strip()
        texts.append(text if text else None)
        ids.append(pid)

    vecs = embeddings_batch(texts)  # batch for speed
    for pid, ej in zip(ids, vecs):
        conn.execute("UPDATE patterns SET embedding_json=? WHERE id=?", (ej, pid))
