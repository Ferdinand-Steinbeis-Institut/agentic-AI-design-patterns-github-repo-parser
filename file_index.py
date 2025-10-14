"""
file_index.py 

Description: General helpers across modules

1. Snippet hashing (providing stable identifiers for code/doc fragments)
2. File hashing (deduplicate and track changes in file level)
3. Language detection (figure out what parser needs to be utilized according to file type either ast, or md, or notebook, or config)

"""

from pathlib import Path
import hashlib
from constants import PY_EXT, SPECIAL_FILENAMES, TEXT_LANG_BY_SUFFIX

#a hash for every snippet to help with identification and tracking
def snippet_hash(text: str | None) -> str:
    if not text:
        text = ""
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

#checksum/ hash - unique identifier for each file (in files table of db)
def sha256_bytes(p: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

#detecting language of the codefile - special files, extensions
def detect_lang(p: Path) -> str:
    if p.suffix in PY_EXT: 
        return "python"
    if p.name in SPECIAL_FILENAMES:
        return SPECIAL_FILENAMES[p.name]
    if p.suffix in TEXT_LANG_BY_SUFFIX:
        return TEXT_LANG_BY_SUFFIX[p.suffix]
    return "unknown"
