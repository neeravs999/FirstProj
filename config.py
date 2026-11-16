"""Shared settings for the telecom RAG chatbot."""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")  # NFR-03: keys come from .env, never from code

DATA_DIR = BASE_DIR / "data"
FAQ_PATH = DATA_DIR / "faq.csv"
TICKETS_DB_PATH = DATA_DIR / "tickets.db"
GUIDE_PDF_PATH = DATA_DIR / "telecom_guide.pdf"

CHROMA_DIR = BASE_DIR / "chroma_store"          # FR-17 / NFR-05
LOG_PATH = BASE_DIR / "logs" / "interactions.jsonl"  # FR-05a

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # FR-09
# FR-13 named qwen/qwen3.6-27b; Groq has retired it, qwen3.8-27b is its successor.
LLM_MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")
TOP_K = 3                                                # FR-07
CHUNK_SIZE = 600                                         # FR-16
CHUNK_OVERLAP = 100


@lru_cache(maxsize=1)
def get_embeddings():
    """Local HuggingFace embeddings (NFR-02). Loaded once per process."""
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )
