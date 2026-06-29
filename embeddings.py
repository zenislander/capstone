"""
Swappable embedding backend.

WHY THIS FILE EXISTS:
LangChain's vector stores (Chroma, etc.) expect an object implementing the
`Embeddings` interface: `embed_documents(list[str]) -> list[list[float]]`
and `embed_query(str) -> list[float]`. As long as something implements that
interface, every other piece of this pipeline (chunking, Chroma storage,
retrieval, metadata filtering) is completely indifferent to *how* the
vectors were produced.

This project uses that to its advantage:

- HERE (sandbox demo): no internet access to huggingface.co, so we use a
  TF-IDF vectorizer (scikit-learn) wrapped to satisfy the same interface.
  TF-IDF is LEXICAL (keyword-overlap based), not semantic -- it has no
  notion that "token allocation" and "LLM quota" mean similar things. It
  works fine for demoing the *plumbing* (chunking, metadata filters,
  Chroma storage/retrieval, structured extraction) against this synthetic
  corpus's vocabulary, but it will not generalize the way a real sentence
  embedding model does.

- ON WINDOWS (your machine, real deployment): swap to
  `HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")`.
  This is a single line change (see `get_embeddings()` below) -- nothing
  else in the codebase needs to know or care. The first run on your
  machine will auto-download the ~80MB model from huggingface.co, then
  reuse the local cache on every run after that. No API key needed.

To switch: change BACKEND below from "tfidf" to "huggingface", or simply
set the environment variable EMBEDDING_BACKEND=huggingface.
"""

import os
import pickle
from pathlib import Path

import numpy as np
from langchain_core.embeddings import Embeddings
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD

# ---------------------------------------------------------------------------
# Configuration: this is the ONE line that changes between sandbox and
# Windows. Everything downstream (ingestion, retrieval) is agnostic.
# ---------------------------------------------------------------------------
BACKEND = os.environ.get("EMBEDDING_BACKEND", "huggingface")  # "tfidf" or "huggingface"
HF_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TARGET_DIM = 384  # matches all-MiniLM-L6-v2's output dim, for drop-in parity


class TfidfEmbeddings(Embeddings):
    """
    A LangChain-compatible Embeddings implementation backed by TF-IDF +
    dimensionality reduction (TruncatedSVD / LSA), so it behaves like a
    fixed-length dense embedding model the rest of the pipeline expects.

    Limitations vs. a real sentence embedding model (be upfront about this
    in any writeup or demo):
      - Lexical, not semantic: "token quota" and "token allocation" will
        NOT be recognized as similar unless they share vocabulary with the
        fitted corpus.
      - Must be FIT on a representative corpus before use. Unlike a
        pretrained transformer, this has no general language knowledge --
        it only knows the vocabulary it was fit on. This is why ingestion
        fits the vectorizer once on the full synthetic corpus before
        embedding individual chunks.
      - Vocabulary is closed: a query using a word never seen during fit
        will be ignored for that term.
    """

    def __init__(self, target_dim: int = TARGET_DIM, cache_path: str | None = None):
        self.target_dim = target_dim
        self.cache_path = cache_path
        self._vectorizer: TfidfVectorizer | None = None
        self._svd: TruncatedSVD | None = None
        self._fitted = False

    def fit(self, corpus: list[str]) -> None:
        """Fit TF-IDF + SVD on the full corpus. Call this once during ingestion,
        before embedding any individual document or query."""
        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            max_features=20000,
        )
        tfidf_matrix = self._vectorizer.fit_transform(corpus)

        # SVD component count can't exceed min(n_samples, n_features) - 1
        n_components = min(self.target_dim, tfidf_matrix.shape[0] - 1, tfidf_matrix.shape[1] - 1)
        n_components = max(n_components, 2)
        self._svd = TruncatedSVD(n_components=n_components, random_state=42)
        self._svd.fit(tfidf_matrix)
        self._fitted = True

        if self.cache_path:
            self.save(self.cache_path)

    def save(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"vectorizer": self._vectorizer, "svd": self._svd}, f)

    def load(self, path: str) -> None:
        with open(path, "rb") as f:
            state = pickle.load(f)
        self._vectorizer = state["vectorizer"]
        self._svd = state["svd"]
        self._fitted = True

    def _ensure_fitted(self):
        if not self._fitted:
            raise RuntimeError(
                "TfidfEmbeddings must be fit() on a corpus before use, or "
                "load() a previously saved fit. This differs from a "
                "pretrained HF model, which works out of the box."
            )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        self._ensure_fitted()
        tfidf_matrix = self._vectorizer.transform(texts)
        reduced = self._svd.transform(tfidf_matrix)
        # Pad to target_dim if SVD produced fewer components (small corpora)
        if reduced.shape[1] < self.target_dim:
            pad = np.zeros((reduced.shape[0], self.target_dim - reduced.shape[1]))
            reduced = np.hstack([reduced, pad])
        # L2-normalize so cosine similarity behaves sanely, same convention
        # sentence-transformers models typically follow
        norms = np.linalg.norm(reduced, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        reduced = reduced / norms
        return reduced.tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]


def get_embeddings(corpus_for_fitting: list[str] | None = None, cache_path: str | None = None) -> Embeddings:
    """
    Factory function -- this is what the rest of the codebase calls.
    Returns a ready-to-use Embeddings object regardless of backend.

    Args:
        corpus_for_fitting: required for the "tfidf" backend on first fit.
            Ignored for "huggingface" backend (pretrained, no fitting needed).
        cache_path: where to persist/load a fitted TF-IDF state, so repeated
            runs don't need to refit.
    """
    if BACKEND == "huggingface":
        # =====================================================================
        # WINDOWS / REAL DEPLOYMENT PATH
        # Requires internet access to huggingface.co on first run only.
        # =====================================================================
        from langchain_huggingface import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(model_name=HF_MODEL_NAME)

    elif BACKEND == "tfidf":
        # =====================================================================
        # SANDBOX DEMO PATH (no internet to huggingface.co available)
        # =====================================================================
        emb = TfidfEmbeddings(cache_path=cache_path)
        if cache_path and Path(cache_path).exists():
            emb.load(cache_path)
        elif corpus_for_fitting:
            emb.fit(corpus_for_fitting)
        else:
            raise ValueError(
                "TF-IDF backend needs either a corpus_for_fitting (first run) "
                "or an existing cache_path to load from."
            )
        return emb

    else:
        raise ValueError(f"Unknown EMBEDDING_BACKEND: {BACKEND}")
