"""
Vector store + retrieval layer.

Implements the retrieval design choices from the capstone doc:

  - "the agent embeds the current query ... and retrieves the top 5 most
     semantically similar chunks, filtered by intake ID or Bureau when
     available" -> default k=5, optional metadata filter.

  - "For time-sensitive decisions ... the result set is filtered to the
     specific intake ID first, which typically returns 2-3 highly relevant
     chunks" -> intake-scoped retrieval, smaller k.

  - "the retrieval filter excludes superseded documents by default" ->
     every retrieval call filters out superseded=True unless explicitly
     asked to include historical/superseded versions.

  - "the agent's reasoning step is instructed to prefer the most recently
     dated chunk when multiple versions ... exist" -> results are sorted
     by date (descending) as a tie-breaker / presentation order, so the
     most recent relevant chunk surfaces first even among equally-similar
     matches.

Chroma is used as the vector store, matching the original plan (LangChain
+ Chroma, metadata filtering support). The embedding backend is whatever
embeddings.get_embeddings() returns -- TF-IDF here, swappable to a real HF
sentence-transformer on Windows (see embeddings.py).
"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from embeddings import get_embeddings

PERSIST_DIR = Path(__file__).parent.parent / "output" / "chroma_store"
TFIDF_CACHE_PATH = Path(__file__).parent.parent / "output" / "tfidf_embeddings.pkl"

COLLECTION_NAME = "bureau_token_intake_corpus"


def build_vector_store(documents: list[Document], persist: bool = True) -> Chroma:
    """Fits the embedding backend on the full corpus (required for the
    TF-IDF stand-in; a no-op for a pretrained HF model) and ingests every
    chunk into Chroma."""
    corpus_texts = [d.page_content for d in documents]

    embeddings = get_embeddings(
        corpus_for_fitting=corpus_texts,
        cache_path=str(TFIDF_CACHE_PATH) if persist else None,
    )

    persist_directory = str(PERSIST_DIR) if persist else None
    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=persist_directory,
    )

    # Chroma requires unique IDs; use source_id + a running counter to
    # disambiguate any duplicate-section chunks safely.
    ids = [f"{d.metadata.get('source_id', 'doc')}-{i}" for i, d in enumerate(documents)]
    vector_store.add_documents(documents=documents, ids=ids)

    return vector_store


def load_vector_store() -> Chroma:
    """Reload a previously persisted store without re-ingesting. Requires
    the TF-IDF cache to already exist (or use the HF backend, which needs
    no fitting)."""
    embeddings = get_embeddings(cache_path=str(TFIDF_CACHE_PATH))
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(PERSIST_DIR),
    )


def _build_filter(
    bureau: str | None = None,
    intake_id: str | None = None,
    doc_type: str | None = None,
    include_superseded: bool = False,
) -> dict | None:
    """Builds a Chroma `where` filter. Chroma needs $and for multiple
    conditions. Excludes superseded docs by default, per the doc's
    staleness-mitigation design."""
    conditions = []
    if bureau:
        conditions.append({"bureau": bureau})
    if intake_id:
        conditions.append({"intake_id": intake_id})
    if doc_type:
        conditions.append({"doc_type": doc_type})
    if not include_superseded:
        conditions.append({"superseded": False})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def retrieve(
    vector_store: Chroma,
    query: str,
    bureau: str | None = None,
    intake_id: str | None = None,
    doc_type: str | None = None,
    k: int = 5,
    include_superseded: bool = False,
) -> list[Document]:
    """
    General-purpose retrieval call matching the doc's default behavior:
    top-k semantically similar chunks, optionally filtered by Bureau/
    intake ID/doc type, superseded docs excluded by default.

    Results are re-sorted so that, among the returned top-k, more recent
    chunks are surfaced first -- approximating "prefer the most recently
    dated chunk" without discarding genuinely relevant older matches that
    semantic similarity ranked highly.
    """
    where = _build_filter(bureau, intake_id, doc_type, include_superseded)
    results = vector_store.similarity_search(query, k=k, filter=where)
    results.sort(key=lambda d: d.metadata.get("date", ""), reverse=True)
    return results


def retrieve_intake_scoped(
    vector_store: Chroma,
    query: str,
    intake_id: str,
    k: int = 3,
    include_superseded: bool = False,
) -> list[Document]:
    """
    Matches the doc's time-sensitive-decision path: "filtered to the
    specific intake ID first, which typically returns 2-3 highly relevant
    chunks without noise from unrelated intakes." Tighter k, hard intake
    scoping.
    """
    return retrieve(
        vector_store, query, intake_id=intake_id, k=k,
        include_superseded=include_superseded,
    )


def get_active_version(
    vector_store: Chroma,
    intake_id: str,
    doc_type: str,
    section: str | None = None,
) -> Document | None:
    """
    Direct lookup for the staleness-mitigation scenario: given an intake
    and document type (e.g. 'vendor_quote'), return the current
    (non-superseded), most-recently-dated chunk -- bypassing semantic
    search entirely, since this is a metadata-exact lookup, not a
    similarity query. This is the kind of check the doc describes before
    "using the old figures to brief leadership or advance an intake."
    """
    where_conditions = [
        {"intake_id": intake_id},
        {"doc_type": doc_type},
        {"superseded": False},
    ]
    if section:
        where_conditions.append({"section": section})
    where = {"$and": where_conditions}

    # Use a generic query string since we want metadata-filtered results,
    # not semantic ranking -- the filter does all the real work here.
    candidates = vector_store.similarity_search(
        "current document version", k=10, filter=where,
    )
    if not candidates:
        return None
    candidates.sort(key=lambda d: d.metadata.get("date", ""), reverse=True)
    return candidates[0]
