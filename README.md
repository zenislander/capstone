# Bureau LLM Token Intake Monitor

A multi-agent RAG system for a Federal Agency that monitors LLM token contract consumption across bureaus, tracks active renewal requests in the intake pipeline, and surfaces contract risk via a Claude-powered gap analysis — all rendered in a Rich terminal dashboard.

Built as a capstone project for the Agency LLM Token Intake system.

---

## What the system does

Six bureaus procure LLM API tokens under fixed-dollar contracts. This system answers two questions at every run:

1. **How much of each bureau's contract has been consumed?** — by joining live cloud provider spend (AWS Bedrock + GCP Vertex AI) against signed contract values retrieved from a RAG vector store.
2. **Is a renewal on track to arrive before the contract runs out?** — by querying the intake pipeline for active renewal requests and their current stage.

The gap analysis agent (Claude `claude-sonnet-4-6`) interprets both signals together and assigns a risk status to every bureau.

---

## Architecture

```
Provider Query Agent
  ├── aws_query_tool.py       Reads AWS Bedrock mock invocation log
  └── gcp_query_tool.py       Reads GCP Vertex AI mock invocation log
          │
          ▼
  provider_query_output.json  Per-bureau spend totals + failed_sources flag
          │
          ▼
Aggregator Agent
  ├── RAG vector store         Chroma + HuggingFace all-MiniLM-L6-v2 (384-dim)
  │     ├── emails             Scenario + synthetic email threads
  │     ├── tickets            ServiceNow stage histories
  │     ├── documents          CEBDs, vendor quotes (with superseded-doc handling)
  │     ├── policy             Numbered-clause policy corpus
  │     └── structured intakes Intake records with bureau, stage, renewal_of metadata
  ├── Signed CEBD lookup       Per-bureau contract value via RAG metadata filter
  ├── Intake pipeline query    Scenario-tagged, non-provisioned intakes per bureau
  └── Threshold + quality      75% threshold, 3-state reliability model
          │
          ▼
  aggregator_output.json      usage_monitor + intake_pipeline + failed_data_sources
          │
          ▼
Gap Analysis Agent
  └── Claude API (claude-sonnet-4-6)
        Assigns: action_required | monitor | on_track | data_gap
          │
          ▼
  gap_analysis.json
          │
          ▼
Rich Terminal Dashboard
  ├── Header                  Timestamp · overall quality · error count
  ├── Data Source Warning      Red banner when a provider tool has failed
  ├── Usage Monitor           Bureau · contract · spend · % consumed · threshold
  ├── Intake Pipeline         Bureau · request · stage · renewal linkage
  └── Gap Analysis            Color-coded risk panels with Claude narrative
```

---

## Setup

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add your Anthropic API key:

```bash
cp .env.example .env
# then edit .env:
ANTHROPIC_API_KEY=sk-ant-api03-...
```

---

## Running the system

### Build — generate synthetic data and construct the vector store

```bash
python main.py build
```

Generates synthetic emails, tickets, documents, and policy; merges all scenario intakes (BFS R-05642, IRS R-05526, BEP R-07788, plus pipeline intakes R-05522 and R-02233); chunks and embeds everything into a persistent Chroma vector store.

### Run — execute the full agent pipeline and render the dashboard

```bash
python main.py run
```

Runs all four stages in sequence:
1. Provider Query Agent — fetches AWS + GCP spend
2. Aggregator Agent — RAG join, threshold computation, pipeline query
3. Gap Analysis Agent — Claude API risk assessment
4. Dashboard render — prints the full Rich terminal output

### Query — ad hoc retrieval against the live vector store

```bash
python main.py query "BFS renewal CEBD customer estimate" --bureau BFS
python main.py query "show me all IRS emails" --bureau IRS --doc-type email
python main.py query "active requests in the intake pipeline"
```

### Demo — run the fixed 8-query demonstration set

```bash
python main.py demo
```

Exercises: general semantic search, intake-scoped tightening, superseded-document exclusion, active-version direct lookup, bureau-filtered queries, dashboard push simulation, aggregation.

### Aggregate — precise Bureau × Token Type table

```bash
python main.py aggregate
```

Pandas groupby over the structured intake table — not retrieval-based, guaranteed complete.

---

## Gap analysis risk statuses

| Status | Meaning |
|---|---|
| `action_required` | ≥75% consumed AND no renewal, or renewal at an early stage (Inquiry → Customer estimate approval) |
| `monitor` | ≥75% consumed AND renewal at Executive approval or later — likely to land before contract exhausts |
| `on_track` | Below 75% threshold |
| `data_gap` | Data quality is `incomplete` or `failed`, or no signed CEBD found — short-circuits threshold logic |

Customer estimate approval is explicitly classified as too early to count as "nearly done" — funding prep, funding receipt, contracting, and execution still remain.

---

## Reliability model

The aggregator uses a three-state data quality classification on every bureau row:

| State | Cause |
|---|---|
| `success` | Provider data is fresh, signed CEBD found, join complete |
| `incomplete` | A provider tool failed, or signed CEBD missing for this bureau |
| `failed` | Provider output timestamp unchanged from previous run (stale data) |

Every non-success state is simultaneously:
- Logged to `output/aggregator_error_log.json`
- Surfaced as an `anomalies[]` entry on the affected dashboard row
- Sent as an admin email alert (stub — prints to console; replace with `smtplib` in production)

---

## Simulating a GCP tool failure

Open `Provider Query Agent/provider_query_agent/tools/gcp_query_tool.py` and set:

```python
SIMULATE_GCP_FAILURE = True
```

On the next `python main.py run`:
- The GCP tool raises a `RuntimeError` (simulated IAM timeout)
- The Provider Query Agent catches it, continues with AWS-only data, and sets `failed_sources: ["gcp"]`
- The Aggregator downgrades all bureau rows to `incomplete` and fires an admin alert
- The dashboard shows a red warning banner: **DATA SOURCE FAILURE DETECTED**
- Spend figures are visibly understated; gap analysis classifies every bureau as `data_gap`

Revert to `SIMULATE_GCP_FAILURE = False` and re-run to confirm full recovery.

A similar toggle exists for synthetic email generation in `data_generator.py`:

```python
SYNTHETIC_EMAILS_DISABLED = True   # scenario emails only
SYNTHETIC_EMAILS_DISABLED = False  # restore full synthetic generation
```

---

## Intake pipeline stages

| Raw stage | Display name |
|---|---|
| Intake Received | Inquiry |
| Technical Review | Discovery |
| Cost Estimation | Estimation |
| Approved | Executive approval |
| CEBD Drafted | Customer estimate approval |
| Provisioned | (excluded from pipeline view) |

---

## Scenario intakes

Three bureaus have real email-thread scenarios (23–12 emails each) representing active renewal requests:

| Bureau | Request | Renews | Amount | Stage |
|---|---|---|---|---|
| BFS | R-05642 | R-04321 | $50,000 | Customer estimate approval |
| IRS | R-05526 | R-01234 | $10,000 | Cost Estimation |
| BEP | R-07788 | R-07765 | $5,000 | Approved |

Two additional non-renewal scenario intakes are also in the pipeline (IRS R-05522 at Technical Review, BFS R-02233 at Approved). OCC has no in-flight intake and shows "No request found."

---

## Project structure

```
main.py                          CLI entry point (build / run / demo / query / aggregate)
data_generator.py                Synthetic corpus generator (18 intakes, emails, tickets, docs, policy)
embeddings.py                    HuggingFace embedding backend (all-MiniLM-L6-v2)

Provider Query Agent/
  provider_query_agent/
    agents/provider_query_agent.py   Fan-out tool orchestration, failed_sources propagation
    tools/aws_query_tool.py          AWS Bedrock mock log reader
    tools/gcp_query_tool.py          GCP Vertex AI mock log reader + SIMULATE_GCP_FAILURE flag
    data/                            Mock invocation logs, pricelists, contracts.json

aggregator/aggregator_agent.py   RAG join, threshold, pipeline, reliability model
gap_analysis/gap_analysis_agent.py  Claude API gap analysis
dashboard/dashboard.py           Rich terminal dashboard renderer

ingestion/loaders.py             Type-specific chunking → LangChain Documents
extraction/structured.py         Pydantic intake model, structured table, vector chunk builder
retrieval/store.py               Chroma vector store + filtered retrieval
retrieval/dashboard.py           Simulated dashboard push / aggregation

bfs_scenario/bfs_emails.json     23-email BFS thread (R-05642)
irs_scenario/irs_emails.json     IRS renewal thread (R-05526)
bep_scenario/bep_emails.json     BEP renewal thread (R-07788)

merge_bfs_scenario.py            Merges BFS scenario into data/
merge_irs_scenario.py            Merges IRS scenario into data/
merge_bep_scenario.py            Merges BEP scenario into data/
merge_signed_cebds.py            Merges signed CEBD records into data/
merge_pipeline_intakes.py        Merges additional pipeline intakes (R-05522, R-02233)

.env.example                     API key template (copy to .env, never commit .env)
requirements.txt                 Pinned dependencies
output/                          Generated run artifacts (gitignored)
data/                            Generated synthetic data (gitignored)
```

---

## Dependencies

Key packages: `langchain`, `langchain-chroma`, `langchain-text-splitters`, `langchain-huggingface`, `chromadb`, `sentence-transformers`, `anthropic`, `python-dotenv`, `rich`, `pandas`, `pydantic`.

See `requirements.txt` for pinned versions.
