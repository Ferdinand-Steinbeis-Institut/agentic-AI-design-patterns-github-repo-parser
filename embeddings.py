# embeddings.py
import os, json, numpy as np
from sentence_transformers import SentenceTransformer

_state = {"model": None, "device": "cpu"}

def _log(msg):
    if os.getenv("EMBED_VERBOSE", "0") == "1":
        print(f"[embeddings pid={os.getpid()}] {msg}")

def _pick_device():
    """
    Choose device with an explicit override via EMBED_DEVICE.
    Default: avoid MPS to dodge 4GiB single-tensor crashes on Apple Silicon.
    """
    want = os.getenv("EMBED_DEVICE", "").strip().lower()  # "cpu" | "cuda" | "mps"
    if want in {"cpu", "cuda", "mps"}:
        return want
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        # Intentionally *not* auto-picking MPS to avoid Metal 4GiB cap
        # if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        #     return "mps"
    except Exception:
        pass
    return "cpu"

def get_model():
    if _state["model"] is None:
        model_id = os.getenv("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")
        device = _pick_device()
        _log(f"Loading SentenceTransformer model='{model_id}' on device='{device}'")

        # Use lower precision on GPU/MPS to reduce memory pressure.
        model_kwargs = {}
        if device in ("cuda", "mps"):
            # Let HF choose fp16/bf16 as supported; reduces per-tensor bytes ~2x.
            model_kwargs["dtype"] = "auto"

        model = SentenceTransformer(
            model_id,
            device=device,
            trust_remote_code=True,
            model_kwargs=model_kwargs,
        )

        # Cap sequence length; large contexts inflate attention temporaries.
        try:
            model.max_seq_length = int(os.getenv("EMBED_MAX_TOKENS", "1024"))
        except Exception:
            pass

        _state["model"] = model
        _state["device"] = device
    return _state["model"]

def embeddings(text: str):
    """Embed a single text → JSON string (or None)."""
    if not text or not text.strip():
        return None
    model = get_model()
    vec = model.encode(
        text,
        normalize_embeddings=True,
        batch_size=1,              # safer for MPS/GPU
        convert_to_numpy=True,     # keep outputs on host; avoids GPU lingering tensors
        show_progress_bar=False,
    )
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

    # Keep default batches small; you can raise via EMBED_BATCH on CUDA.
    default_batch = 1 if _state.get("device") == "mps" else 4
    batch = int(os.getenv("EMBED_BATCH", str(default_batch)))
    _log(f"encode batch_size={batch}, n_items={len(non_empty)}")

    model = get_model()
    vecs = model.encode(
        non_empty,
        normalize_embeddings=True,
        batch_size=batch,
        convert_to_numpy=True,
        show_progress_bar=bool(int(os.getenv("EMBED_PROGRESS", "0"))),
    )
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

def symbol_text(name, kind, doc, source, max_body=None):
    # Deduplicated: keep only one definition and respect EMBED_MAX_BODY
    max_body = max_body or int(os.getenv("EMBED_MAX_BODY", "1500"))
    body = (source or "")[:max_body]
    return "\n".join([p for p in [kind or "", name or "", doc or "", body] if p]).strip()
