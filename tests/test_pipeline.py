"""
Smoke tests for the core pipeline behaviors. Not exhaustive -- these check
that the key design choices from the capstone doc actually hold, so a
future change doesn't silently break the superseded-doc exclusion or the
intake-scoping logic.

Run with: python -m pytest tests/test_pipeline.py -v
(or just: python tests/test_pipeline.py)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from data_generator import generate_all
from ingestion.loaders import load_all_documents
from extraction.structured import load_structured_intake_chunks, load_structured_intakes, aggregate_tokens_by_bureau
from retrieval.store import build_vector_store, retrieve, retrieve_intake_scoped, get_active_version


def setup_module():
    generate_all()


def _build_test_store():
    docs = load_all_documents() + load_structured_intake_chunks()
    return build_vector_store(docs, persist=False)


def test_chunking_produces_all_doc_types():
    docs = load_all_documents()
    types_seen = {d.metadata["doc_type"] for d in docs}
    assert {"email", "ticket", "vendor_quote", "cebd", "policy"}.issubset(types_seen)


def test_email_chunks_are_atomic():
    """Each email should be exactly one chunk (no mid-message splitting) for
    typical synthetic email lengths."""
    docs = load_all_documents()
    emails = [d for d in docs if d.metadata["doc_type"] == "email"]
    # No email in the synthetic set should have been split (chunk_part absent)
    assert all("chunk_part" not in d.metadata for d in emails)


def test_superseded_doc_exists_and_is_flagged():
    docs = load_all_documents()
    superseded = [d for d in docs if d.metadata.get("superseded") is True]
    assert len(superseded) == 1
    assert superseded[0].metadata["doc_type"] == "vendor_quote"


def test_retrieval_excludes_superseded_by_default():
    store = _build_test_store()
    results = retrieve(store, "pricing quote", intake_id="R-1001", doc_type="vendor_quote", k=10)
    assert all(r.metadata.get("superseded") is False for r in results)


def test_retrieval_includes_superseded_when_requested():
    store = _build_test_store()
    results = retrieve(
        store, "pricing quote", intake_id="R-1001", doc_type="vendor_quote",
        k=10, include_superseded=True,
    )
    assert any(r.metadata.get("superseded") is True for r in results)


def test_intake_scoped_retrieval_has_no_cross_intake_leakage():
    store = _build_test_store()
    results = retrieve_intake_scoped(store, "vendor pricing", intake_id="R-1001", k=10)
    assert all(r.metadata.get("intake_id") == "R-1001" for r in results)


def test_get_active_version_returns_non_superseded():
    store = _build_test_store()
    active = get_active_version(store, intake_id="R-1001", doc_type="vendor_quote", section="pricing")
    assert active is not None
    assert active.metadata["superseded"] is False


def test_bureau_filter_scopes_correctly():
    store = _build_test_store()
    results = retrieve(store, "token request", bureau="IRS", k=10)
    assert all(r.metadata.get("bureau") == "IRS" for r in results)


def test_structured_aggregation_matches_raw_sum():
    intakes = load_structured_intakes()
    agg = aggregate_tokens_by_bureau(intakes)
    raw_total = sum(i.token_amount for i in intakes)
    assert agg["TOTAL"].sum() == raw_total


if __name__ == "__main__":
    setup_module()
    tests = [
        test_chunking_produces_all_doc_types,
        test_email_chunks_are_atomic,
        test_superseded_doc_exists_and_is_flagged,
        test_retrieval_excludes_superseded_by_default,
        test_retrieval_includes_superseded_when_requested,
        test_intake_scoped_retrieval_has_no_cross_intake_leakage,
        test_get_active_version_returns_non_superseded,
        test_bureau_filter_scopes_correctly,
        test_structured_aggregation_matches_raw_sum,
    ]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {t.__name__} -- {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
