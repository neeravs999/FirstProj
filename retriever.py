"""Merged retriever: top-3 from each collection, queried in parallel (FR-06/07).

To add a knowledge source (NFR-06): write an ingest_<name>.py that calls
write_collection("<name>", ...), then add the collection name below.
"""
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.runnables import RunnableParallel

from config import CHROMA_DIR, TOP_K, get_embeddings

COLLECTIONS = ["faq", "tickets", "guides"]


class StoreNotBuiltError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_merged_retriever() -> RunnableParallel:
    if not CHROMA_DIR.exists():
        raise StoreNotBuiltError(
            "No chroma_store/ found. Run `python ingest_all.py` once before starting the bot."
        )
    retrievers = {}
    for name in COLLECTIONS:
        store = Chroma(
            collection_name=name,
            embedding_function=get_embeddings(),
            persist_directory=str(CHROMA_DIR),
        )
        if not store.get(limit=1)["ids"]:
            raise StoreNotBuiltError(
                f"Collection '{name}' is empty. Run `python ingest_all.py` to build it."
            )
        retrievers[name] = store.as_retriever(search_kwargs={"k": TOP_K})
    return RunnableParallel(retrievers)


def retrieve(question: str) -> list[Document]:
    """Return up to 9 documents: FAQ first, then tickets, then guide chunks."""
    results = get_merged_retriever().invoke(question)
    return [doc for name in COLLECTIONS for doc in results[name]]
