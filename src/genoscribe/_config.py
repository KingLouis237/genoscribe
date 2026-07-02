from __future__ import annotations

import os
from pathlib import Path

# --- Model / LLM ---
MODEL = (
    os.getenv("CLAUDE_MODEL")
    or os.getenv("ANTHROPIC_MODEL")
    or os.getenv("HF_MODEL")
    or "claude-3-haiku-20240307"
)
MAX_TOKENS = 1200

# --- Project root + data paths ---
PROJECT_ROOT = Path(__file__).resolve().parents[1]  # .../GenoScribe/src/
DATA_DIR = PROJECT_ROOT / "genomics_assistant_data"
LIBRARY_DIR = DATA_DIR / "library"
LIBRARY_FILES_DIR = DATA_DIR / "library_files"
INBOX_DIR = DATA_DIR / "inbox"
OUTPUT_DIR = DATA_DIR / "outputs"
CACHE_DIR = DATA_DIR / "cache"
VECTOR_DIR_NAME = "vectors"
STATE_FILE = DATA_DIR / "state.json"
IDF_FILE = DATA_DIR / "idf_weights.json"
STATS_FILE = DATA_DIR / "library_stats.json"
QUERY_CACHE_FILE = CACHE_DIR / "query_embeddings.json"

# --- OS integration ---
DEFAULT_DOWNLOADS_DIR = Path(
    os.getenv("GENOSCRIBE_DOWNLOADS_DIR")
    or (Path.home() / "Downloads")
)

# --- Ingest ---
SUPPORTED_EXT = {".pdf", ".txt", ".md"}

CHUNK_TARGET_SIZE = 1200
CHUNK_MAX_SIZE = 1700
CHUNK_OVERLAP_PARAS = 1

# --- Retrieval ---
BM25_K1 = 1.5
BM25_B = 0.75

DEFAULT_SEARCH_METHOD = "bm25"  # "tfidf" or "bm25"
TOP_K_DEFAULT = 6

# --- Dense retrieval / reranking ---
EMBED_MODEL = os.getenv("GENOSCRIBE_EMBED_MODEL", "sentence-transformers/multi-qa-mpnet-base-dot-v1")
EMBED_DIM = int(os.getenv("GENOSCRIBE_EMBED_DIM", "768"))
EMBED_MAX_FEATURES = int(os.getenv("GENOSCRIBE_EMBED_MAX_FEATURES", "50000"))
RERANKER_ALPHA = float(os.getenv("GENOSCRIBE_RERANKER_ALPHA", "0.6"))
QUERY_CACHE_SIZE = int(os.getenv("GENOSCRIBE_QUERY_CACHE_SIZE", "128"))
VECTOR_MANIFEST_VERSION = 1
INGESTION_PIPELINE_VERSION = 1
EMBED_BATCH_SIZE = int(os.getenv("GENOSCRIBE_EMBED_BATCH_SIZE", "8"))

# --- Evidence / Safety ---
STRICT_ON_CITE = True

# --- Structured synthesis ---
USE_STRUCTURED_PAPER_SYNTHESIS = os.getenv("GENOSCRIBE_STRUCTURED_PAPER", "0") == "1"
