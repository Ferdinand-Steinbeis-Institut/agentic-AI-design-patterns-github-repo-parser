# embeddings.py
import os, json, numpy as np
from sentence_transformers import SentenceTransformer

_state = {"model": None, "device": "cpu"}

def _log(msg):
    if os.getenv("EMBED_VERBOSE", "0") == "1":
        print(f"[embeddings pid={os.getpid()}] {msg}")

def _pick_device():
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        #if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            #return "mps"
    except Exception:
        pass
    return "cpu"

def get_model():
    if _state["model"] is None:
        model_id = os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")
        device = _pick_device()
        print("Device name")
        print(device)
        _log(f"Loading SentenceTransformer model='{model_id}' on device='{device}'")
        _state["model"] = SentenceTransformer(model_id, device=device, trust_remote_code=True)
        _state["device"] = device
    return _state["model"]

def embeddings(text: str):
    """Embed a single text → JSON string (or None)."""
    if not text or not text.strip():
        return None
    vec = get_model().encode(text, normalize_embeddings=True)
    return json.dumps([float(x) for x in vec])

def embeddings_batch(texts):
    """Embed a list of texts → list of JSON strings (order-preserving)."""
    if not texts:
        return []
    to_encode = [t if (t and t.strip()) else None for t in texts]
    idx_map = [i for i, t in enumerate(to_encode) if t is not None]
    non_empty = [to_encode[i] for i in idx_map]
    out = [None] * len(texts)
    if not non_empty:
        return out

    batch = int(os.getenv("EMBED_BATCH", "16"))
    _log(f"encode batch_size={batch}, n_items={len(non_empty)}")

    model = get_model()
    vecs = model.encode(non_empty, normalize_embeddings=True, batch_size=batch, show_progress_bar=True)
    for j, i in enumerate(idx_map):
        out[i] = json.dumps([float(x) for x in vecs[j]])
    return out

def loading_vectors(s):
    try:
        return json.loads(s) if s else None
    except Exception:
        return None

def cosine_similarity(u, v) -> float:
    try:
        a = np.array(u, dtype=np.float32); b = np.array(v, dtype=np.float32)
        return float(np.dot(a, b))  # embeddings are normalized
    except Exception:
        return -1.0

def symbol_text(name, kind, doc, source, max_body=6000):
    body = (source or "")[:max_body]
    return "\n".join([p for p in [kind or "", name or "", doc or "", body] if p]).strip()

# embeddings.py
def symbol_text(name, kind, doc, source, max_body=None):
    max_body = max_body or int(os.getenv("EMBED_MAX_BODY", "1500"))
    body = (source or "")[:max_body]
    return "\n".join([p for p in [kind or "", name or "", doc or "", body] if p]).strip()
