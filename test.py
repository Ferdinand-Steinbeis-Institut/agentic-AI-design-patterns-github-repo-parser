import os
os.environ["EMBED_VERBOSE"] = "1"
os.environ["EMBED_BATCH"] = "16"

from embeddings import embeddings_batch
texts = ["hello world", "agentic AI patterns", "test batch"]
embeddings_batch(texts)
