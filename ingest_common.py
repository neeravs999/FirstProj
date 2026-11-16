"""Helper that (re)builds one Chroma collection. Re-running is idempotent (FR-17)."""
from langchain_chroma import Chroma
from langchain_core.documents import Document

from config import CHROMA_DIR, get_embeddings


def write_collection(name: str, docs: list[Document], ids: list[str]) -> None:
    store = Chroma(
        collection_name=name,
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
        collection_metadata={"hnsw:space": "cosine"},
    )
    store.reset_collection()  # drop old vectors so re-runs never duplicate
    store.add_documents(docs, ids=ids)
    print(f"[{name}] stored {len(docs)} documents in {CHROMA_DIR}")
