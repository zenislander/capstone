"""
Ingestion pipeline: loads the four synthetic corpora and converts each into
LangChain `Document` objects using the type-specific chunking strategy
described in the capstone doc:

  - Email messages: ATOMIC. One chunk per email, no splitting. Splitting a
    message mid-sentence loses conversational meaning. Sender/date/subject
    attached as metadata.
  - ServiceNow tickets: one chunk per ticket, summarizing the full stage
    history (these are short structured records, not long enough to need
    section splitting).
  - Long documents (CEBDs, vendor quotes): split by SECTION (scope, pricing,
    terms, etc.), each section becomes its own chunk. Title, Bureau, and
    intake ID attached as metadata.
  - Policy documents: split by numbered CLAUSE, to allow precise citation.

A ~400 token cap is enforced as a safety net using RecursiveCharacterTextSplitter
on any individual chunk that runs long (rare in this synthetic data, but the
real email/document corpus won't be this tidy).

Every chunk's metadata includes: bureau, intake_id, doc_type, date, superseded.
Chroma metadata only supports flat scalar values (str/int/float/bool), so
None values are normalized to a sentinel and nested fields are flattened.
"""

import json
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA_DIR = Path(__file__).parent.parent / "data"

# Rough token cap. We approximate tokens as ~4 chars/token (a common
# heuristic for English text) since we're not running a real tokenizer here.
MAX_TOKENS = 400
MAX_CHARS = MAX_TOKENS * 4

_overflow_splitter = RecursiveCharacterTextSplitter(
    chunk_size=MAX_CHARS,
    chunk_overlap=50,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def _clean_metadata(meta: dict) -> dict:
    """Chroma requires flat scalar metadata values. Normalize None -> ''
    (or a sentinel) and drop nested structures."""
    cleaned = {}
    for k, v in meta.items():
        if v is None:
            cleaned[k] = "none"
        elif isinstance(v, (str, int, float, bool)):
            cleaned[k] = v
        else:
            cleaned[k] = json.dumps(v)
    return cleaned


def _cap_chunk(text: str, base_metadata: dict, id_prefix: str) -> list[Document]:
    """Apply the ~400 token safety cap. Returns 1 Document in the common case,
    multiple only if the source text actually exceeds the cap."""
    if len(text) <= MAX_CHARS:
        return [Document(page_content=text, metadata=_clean_metadata(base_metadata))]

    pieces = _overflow_splitter.split_text(text)
    docs = []
    for i, piece in enumerate(pieces):
        meta = {**base_metadata, "chunk_part": i, "chunk_of": len(pieces)}
        docs.append(Document(page_content=piece, metadata=_clean_metadata(meta)))
    return docs


def load_emails() -> list[Document]:
    """One chunk per email message. Atomic by design."""
    emails = json.load(open(DATA_DIR / "emails.json"))
    docs = []
    for e in emails:
        recipients = e.get("recipients", [])
        to_line = f"\nTo: {', '.join(recipients)}" if recipients else ""
        content = f"Subject: {e['subject']}\nFrom: {e['sender']}{to_line}\nDate: {e['date']}\n\n{e['body']}"
        meta = {
            "source_id": e["email_id"],
            "doc_type": "email",
            "email_kind": e["kind"],
            "bureau": e["bureau"],
            "intake_id": e["intake_id"],
            "date": e["date"],
            "superseded": False,
            "stage": e.get("stage", "none"),
            "sender": e["sender"],
            "recipients": ", ".join(recipients) if recipients else "none",
        }
        docs.extend(_cap_chunk(content, meta, e["email_id"]))
    return docs


def load_tickets() -> list[Document]:
    """One chunk per ticket: stage history summarized into a narrative block.
    Structured intake records, kept whole since they're short."""
    tickets = json.load(open(DATA_DIR / "tickets.json"))
    docs = []
    for t in tickets:
        history_lines = [
            f"  - {h['stage']} ({h['timestamp']}): {h['note']}"
            for h in t["stage_history"]
        ]
        content = (
            f"ServiceNow Ticket: {t['ticket_id']}\n"
            f"Intake: {t['intake_id']}\n"
            f"Bureau: {t['bureau']}\n"
            f"Current Stage: {t['current_stage']}\n\n"
            f"Stage History:\n" + "\n".join(history_lines)
        )
        meta = {
            "source_id": t["ticket_id"],
            "doc_type": "ticket",
            "bureau": t["bureau"],
            "intake_id": t["intake_id"],
            "date": t["stage_history"][-1]["timestamp"],
            "superseded": False,
            "current_stage": t["current_stage"],
        }
        docs.extend(_cap_chunk(content, meta, t["ticket_id"]))
    return docs


def load_documents() -> list[Document]:
    """CEBDs and vendor quotes: split by SECTION. Each section = one chunk."""
    documents = json.load(open(DATA_DIR / "documents.json"))
    docs = []
    for d in documents:
        content = f"{d['title']} -- Section: {d['section']}\n\n{d['content']}"
        meta = {
            "source_id": d["doc_id"],
            "doc_type": d["doc_type"],  # "vendor_quote" or "cebd"
            "section": d["section"],
            "title": d["title"],
            "bureau": d["bureau"],
            "intake_id": d["intake_id"],
            "date": d["date"],
            "superseded": d["superseded"],
            "superseded_by": d.get("superseded_by"),
            "contract_value_usd": d.get("contract_value_usd"),
        }
        docs.extend(_cap_chunk(content, meta, d["doc_id"]))
    return docs


def load_policy() -> list[Document]:
    """Policy corpus: split by numbered CLAUSE for precise citation."""
    clauses = json.load(open(DATA_DIR / "policy.json"))
    docs = []
    for c in clauses:
        content = f"Policy {c['clause_number']} ({c['section_title']}): {c['content']}"
        meta = {
            "source_id": c["doc_id"],
            "doc_type": "policy",
            "clause_number": c["clause_number"],
            "section_title": c["section_title"],
            "bureau": None,
            "intake_id": None,
            "date": c["date"],
            "superseded": False,
        }
        docs.extend(_cap_chunk(content, meta, c["doc_id"]))
    return docs


def load_all_documents() -> list[Document]:
    """Load and chunk all four corpora into a single flat list of LangChain
    Documents, ready for embedding + Chroma ingestion."""
    all_docs = []
    all_docs.extend(load_emails())
    all_docs.extend(load_tickets())
    all_docs.extend(load_documents())
    all_docs.extend(load_policy())
    return all_docs


if __name__ == "__main__":
    docs = load_all_documents()
    print(f"Total chunks: {len(docs)}")
    by_type = {}
    for d in docs:
        by_type[d.metadata["doc_type"]] = by_type.get(d.metadata["doc_type"], 0) + 1
    for k, v in by_type.items():
        print(f"  {k}: {v}")
    print()
    print("Sample email chunk:")
    sample = next(d for d in docs if d.metadata["doc_type"] == "email")
    print("  metadata:", sample.metadata)
    print("  content preview:", sample.page_content[:150].replace("\n", " | "))
