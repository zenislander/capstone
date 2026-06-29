# Bureau LLM-Token-Intake RAG Prototype

A working implementation of the retrieval architecture described in
*Capstone Submission 3.1 — Retrieval-Augmented Design*: a vector-backed
retrieval layer over email, ServiceNow tickets, procurement documents
(CEBDs/vendor quotes), and policy text, supporting an agent that tracks
LLM token requests/allocations per Treasury Bureau.

## What "token utilization per agency" means in this system

Not LLM API billing/cost telemetry — **Bureau-level token *allocation
requests*** moving through an intake/approval pipeline (ServiceNow ticket →
technical review → cost estimate → CEBD → approval → provisioning), each
tagged with Bureau, token type/vendor (Anthropic Claude, AWS Bedrock,
OpenAI GPT-4o, Azure OpenAI), and token amount.

## Architecture

```
data_generator.py          Synthetic emails, tickets, documents, policy
        |
        v
ingestion/loaders.py       Type-specific chunking:
                              - email: 1 chunk/message (atomic)
                              - ticket: 1 chunk/ticket (stage history)
                              - documents: split by section
                              - policy: split by numbered clause
                              ~400 token cap enforced as a safety net
        |
        v
extraction/structured.py   Structured field extraction (Requester, Bureau,
                            Token Type, Amount, Model Spec, Vendor) into:
                              - a Pydantic-validated table (precise aggregation)
                              - a vector-store chunk (per the design doc)
        |
        v
embeddings.py               Swappable embedding backend (see below)
        |
        v
retrieval/store.py          Chroma vector store + retrieval functions:
                              - top-k default (5), metadata-filterable
                              - intake-scoped tightening (k=3)
                              - superseded-document exclusion (default on)
                              - direct active-version lookup (bypasses
                                semantic search for exact metadata lookups)
        |
        v
retrieval/dashboard.py       Simulated "agent writes structured intake ->
                              dashboard reads aggregated totals" data flow
        |
        v
main.py                      CLI: build / demo / query / aggregate
```

## Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
```

```bash
python main.py build     # generate data, chunk, embed, build vector store
python main.py demo      # run all 8 demo queries from the design doc
python main.py aggregate # precise Bureau x Token Type table
python main.py query "what issues has IRS raised?" --bureau IRS
```

## Embedding backend: Option A vs Option B

This was built and tested in a network-sandboxed environment with no
access to `huggingface.co`, so it ships with **two interchangeable
backends** behind a single `Embeddings` interface (`embeddings.py`):

| | Option B (default here) | Option A (use on your machine) |
|---|---|---|
| Backend | TF-IDF + SVD (scikit-learn) | `sentence-transformers/all-MiniLM-L6-v2` |
| Matching | Lexical (keyword/n-gram overlap) | Semantic (meaning-based) |
| Setup | None, works offline immediately | One-time ~80MB download from huggingface.co |
| Quality | Fine for this synthetic corpus's vocabulary; will NOT recognize paraphrases ("token quota" vs "token allocation") | Recognizes semantic similarity even across different wording |

**To switch to Option A on Windows**, either:
```bash
set EMBEDDING_BACKEND=huggingface     # Windows cmd
$env:EMBEDDING_BACKEND="huggingface"  # PowerShell
```
or edit the default in `embeddings.py`:
```python
BACKEND = os.environ.get("EMBEDDING_BACKEND", "huggingface")  # was "tfidf"
```
Nothing else in the codebase changes — `retrieval/store.py`,
`ingestion/loaders.py`, and `main.py` all call `get_embeddings()` and are
indifferent to which backend answers. Delete `output/chroma_store` and
`output/tfidf_embeddings.pkl` and re-run `python main.py build` after
switching, since the two backends produce incompatible vector spaces.

## Known limitations (read before extending)

1. **Structured field extraction is simulated, not live.** `extraction/structured.py`'s
   `load_structured_intakes()` reads already-clean synthetic data instead of
   running a real LLM extraction call against raw email text. The intended
   call shape (`ChatAnthropic(...).with_structured_output(IntakeRecord)`) is
   documented in that file's `extract_from_raw_intake()` stub but requires
   an Anthropic API key to actually run.

2. **Retrieval-based aggregation does not reliably scale.** `retrieval/dashboard.py`'s
   `refresh_bureau_summary()` demonstrates the doc's "agent queries vector
   store, dashboard reads aggregated totals" flow, but top-k similarity
   search has no completeness guarantee — it happens to match the precise
   table in this prototype only because `k=20` exceeds every synthetic
   Bureau's true intake count. At real scale, use
   `extraction/structured.py`'s `aggregate_tokens_by_bureau()` (a real
   pandas groupby over the structured table) to back any dashboard number
   that needs to be correct, not retrieval.

3. **TF-IDF (Option B) requires re-fitting on the full corpus before use**
   and has a closed vocabulary — a query using a word never seen during
   `fit()` is silently ignored for that term. This is a real limitation
   of the lexical stand-in, not present in the pretrained semantic model
   (Option A).

4. **The 400-token chunk cap is approximated** as ~4 characters/token
   (a common English-text heuristic) rather than a real tokenizer count,
   since none of the installed packages run a tokenizer compatible with
   every embedding backend. Close enough for chunking decisions; don't
   rely on it for exact token budgeting against a model's context window.

5. **Dashboard push is a stub.** `retrieval/dashboard.py`'s `push_to_dashboard()`
   logs the payload it would send rather than making a real API call —
   there's no real dashboard backend in this prototype.

## Files

```
data_generator.py       Synthetic corpus generator
embeddings.py           Swappable Embeddings backend (TF-IDF / HuggingFace)
ingestion/loaders.py    Type-specific chunking -> LangChain Documents
extraction/structured.py  Pydantic intake model, structured table, dashboard chunk
retrieval/store.py      Chroma vector store + filtered retrieval functions
retrieval/dashboard.py  Simulated dashboard push / aggregation data flow
main.py                 CLI entry point
requirements.txt        Pinned dependencies
data/                   Generated synthetic JSON (created by `build`)
output/chroma_store/    Persisted Chroma vector store (created by `build`)
```
