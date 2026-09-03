"""
Wraps BAAI/bge-m3 (via sentence-transformers) for local dense embeddings — no
API key required. The model (~2.2GB) downloads once on first use and is
cached locally by Hugging Face's cache afterward.
"""

_model = None

EMBEDDING_DIM = 1024  # BGE-M3's dense embedding dimensionality


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("BAAI/bge-m3")
    return _model


def embed_texts(texts: list) -> list:
    model = get_model()
    vectors = model.encode(
        texts,
        batch_size=12,
        normalize_embeddings=True,  # needed for cosine similarity in Qdrant
        show_progress_bar=False,
    )
    return [v.tolist() for v in vectors]


def embed_text(text: str) -> list:
    return embed_texts([text])[0]
