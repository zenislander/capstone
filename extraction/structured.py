"""
Structured extraction layer.

WHY THIS EXISTS (per our earlier discussion and the capstone doc):
RAG/semantic retrieval is good at "what did Bureau X say about issue Y" --
it's a poor fit for "what is the TOTAL token count for Bureau X across all
intakes," because semantic similarity doesn't aggregate or sum anything.
The capstone doc's own example -- intake form arrives, agent extracts
structured fields, writes them to the vector store, dashboard reads
aggregated totals -- implies a structured layer underneath the vector layer.

This module is the BRIDGE the doc describes:
  "It then formats this structured data and pushes it to the dashboard via
   API, populating the correct Bureau rows with the correct token types
   and amounts."

It does two things for every intake:
  1. Extracts structured fields (Requester, Bureau, Token Type, Token
     Amount, Model Spec, Vendor) into a Pydantic model -- this is the
     PRECISE, AGGREGATABLE record.
  2. Formats that same structured record as a single text chunk with
     metadata, suitable for insertion into the vector store -- this is
     what the doc means by "These fields are stored as a chunk in the
     vector database, tagged with metadata."

In a real deployment, step 1 would come from an LLM-based extraction call
(e.g. LangChain's structured output / `with_structured_output()`) parsing
a raw intake email or attached form. Since our synthetic data already HAS
clean structured intake records (data/intakes.json), this module's
`extract_from_raw_intake` function shows what that LLM extraction call
would look like, and `load_structured_intakes` simulates its OUTPUT by
reading the synthetic intakes directly -- so the rest of the pipeline
(the aggregation table, the dashboard push) can be built and tested now,
and the LLM call slots in later without changing anything downstream.
"""

import json
from pathlib import Path
from typing import Optional

import pandas as pd
from langchain_core.documents import Document
from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).parent.parent / "data"


class IntakeRecord(BaseModel):
    """The structured fields the capstone doc specifies:
    'Requester Name, Bureau, Token Type (e.g., Anthropic Claude, AWS
    Bedrock, OpenAI GPT-4o), Token Amount, LLM Model Specification, and
    Vendor.'"""
    intake_id: str
    ticket_id: str
    requester: str = Field(..., description="Requester Name")
    bureau: str
    token_type: str = Field(..., description="e.g. Anthropic Claude, AWS Bedrock, OpenAI GPT-4o")
    token_amount: int
    model_spec: str = Field(..., description="LLM Model Specification")
    vendor: str
    stage: str
    renewal_of: Optional[str] = None
    intake_source: str = "synthetic"


# ---------------------------------------------------------------------------
# Real deployment path (commented pattern, not executed here):
#
#   from langchain_anthropic import ChatAnthropic
#   llm = ChatAnthropic(model="claude-sonnet-4-6").with_structured_output(IntakeRecord)
#   def extract_from_raw_intake(raw_email_or_form_text: str) -> IntakeRecord:
#       return llm.invoke(
#           f"Extract the intake fields from this request:\n\n{raw_email_or_form_text}"
#       )
#
# This requires an Anthropic API key and a live model call -- intentionally
# NOT wired up in this prototype since the synthetic data already arrives
# pre-structured. The function below documents the intended call shape so
# swapping it in later is a drop-in replacement.
# ---------------------------------------------------------------------------
def extract_from_raw_intake(raw_text: str) -> "IntakeRecord":
    raise NotImplementedError(
        "LLM-based extraction requires a live model call (e.g. "
        "ChatAnthropic.with_structured_output(IntakeRecord)) and an API "
        "key. Not wired up in this offline prototype -- see module "
        "docstring for the intended pattern. Use load_structured_intakes() "
        "to work with the synthetic data, which simulates this function's "
        "output."
    )


def load_structured_intakes() -> list[IntakeRecord]:
    """Simulates the OUTPUT of extract_from_raw_intake() by reading the
    synthetic intake records directly. Returns validated IntakeRecord
    objects -- this is the precise, aggregatable table."""
    raw = json.load(open(DATA_DIR / "intakes.json"))
    return [
        IntakeRecord(
            intake_id=r["intake_id"], ticket_id=r["ticket_id"],
            requester=r["requester"], bureau=r["bureau"],
            token_type=r["token_type"], token_amount=r["token_amount"],
            model_spec=r["model_spec"], vendor=r["vendor"], stage=r["stage"],
            renewal_of=r.get("renewal_of"),
            intake_source=r.get("intake_source", "synthetic"),
        )
        for r in raw
    ]


def intakes_to_dataframe(intakes: list[IntakeRecord]) -> pd.DataFrame:
    """The structured, aggregatable table -- this is what dashboard
    queries like 'total tokens for Bureau X' should run against, NOT
    semantic search."""
    return pd.DataFrame([i.model_dump() for i in intakes])


def intake_to_vector_chunk(intake: IntakeRecord) -> Document:
    """Per the doc: 'These fields are stored as a chunk in the vector
    database, tagged with metadata including Bureau ID, intake ID, token
    provider.' This formats one structured intake record as a single
    text chunk + metadata, for insertion alongside the email/document/
    policy chunks in the same vector store."""
    content = (
        f"Intake {intake.intake_id} ({intake.ticket_id}): "
        f"{intake.requester} from {intake.bureau} requested "
        f"{intake.token_amount:,} {intake.token_type} tokens "
        f"(model: {intake.model_spec}, vendor: {intake.vendor}). "
        f"Current stage: {intake.stage}."
    )
    metadata = {
        "source_id": intake.intake_id,
        "doc_type": "structured_intake",
        "bureau": intake.bureau,
        "intake_id": intake.intake_id,
        "token_type": intake.token_type,
        "token_amount": intake.token_amount,
        "vendor": intake.vendor,
        "stage": intake.stage,
        "renewal_of": intake.renewal_of,
        "intake_source": intake.intake_source,
        "date": "none",
        "superseded": False,
    }
    return Document(page_content=content, metadata=metadata)


def load_structured_intake_chunks() -> list[Document]:
    """The full set of structured-intake chunks, ready to merge into the
    same vector store as emails/tickets/documents/policy."""
    return [intake_to_vector_chunk(i) for i in load_structured_intakes()]


def aggregate_tokens_by_bureau(intakes: list[IntakeRecord]) -> pd.DataFrame:
    """Simulates the dashboard's aggregation query: total tokens
    requested per Bureau, broken out by token type. This is the
    'populating the correct Bureau rows with the correct token types and
    amounts' step from the doc -- precise summation, not retrieval."""
    df = intakes_to_dataframe(intakes)
    pivot = df.pivot_table(
        index="bureau", columns="token_type", values="token_amount",
        aggfunc="sum", fill_value=0,
    )
    pivot["TOTAL"] = pivot.sum(axis=1)
    return pivot.sort_values("TOTAL", ascending=False)


if __name__ == "__main__":
    intakes = load_structured_intakes()
    print(f"Loaded {len(intakes)} structured intake records")
    print()

    print("=== Structured chunk example (what goes into the vector store) ===")
    chunk = intake_to_vector_chunk(intakes[0])
    print("content:", chunk.page_content)
    print("metadata:", chunk.metadata)
    print()

    print("=== Dashboard aggregation: total tokens by Bureau x Token Type ===")
    agg = aggregate_tokens_by_bureau(intakes)
    print(agg.to_string())
