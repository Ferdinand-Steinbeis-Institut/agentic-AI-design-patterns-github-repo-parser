from sentence_transformers import SentenceTransformer

# works with recent ST/Transformers
model = SentenceTransformer(
    "Qwen/Qwen3-Embedding-4B",
    # optional: these can help on long batches
    tokenizer_kwargs={"padding_side": "left"},
)
emb = model.encode(["hello world"], normalize_embeddings=True)
print(len(emb[0]))  # should print 2560
