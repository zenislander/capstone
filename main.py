"""
Main entry point for the Bureau LLM-Token-Intake RAG prototype.

Run modes:
  python3 main.py build      -- generate synthetic data, ingest, build vector store
  python3 main.py demo       -- run a fixed set of demo queries showing each
                                 retrieval pattern from the capstone doc
  python3 main.py query "<question>" [--bureau X] [--intake R-1001]
                              -- ask an ad hoc question against the live store
  python3 main.py aggregate  -- print the structured Bureau x Token Type
                                 aggregation table (precise, non-semantic)
  python3 main.py run        -- run the full agent pipeline: Provider Query Agent
                                 -> Aggregator Agent (RAG join + dashboard output)

See README.md for the full architecture writeup and the Option A (Windows /
real HuggingFace embeddings) vs Option B (this sandbox's TF-IDF stand-in)
explanation.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from data_generator import generate_all
from merge_bfs_scenario import merge_bfs_scenario
from merge_bep_scenario import merge_bep_scenario
from merge_irs_scenario import merge_irs_scenario
from merge_signed_cebds import merge_signed_cebds
from merge_pipeline_intakes import merge_pipeline_intakes
from ingestion.loaders import load_all_documents
from extraction.structured import (
    load_structured_intakes,
    load_structured_intake_chunks,
    aggregate_tokens_by_bureau,
)
from retrieval.store import (
    build_vector_store,
    load_vector_store,
    retrieve,
    retrieve_intake_scoped,
    get_active_version,
)
from retrieval.dashboard import handle_new_intake_event, refresh_bureau_summary
from aggregator.aggregator_agent import AggregatorAgent
from gap_analysis.gap_analysis_agent import GapAnalysisAgent
from dashboard.dashboard import render as render_dashboard
from gap_analysis.gap_analysis_agent import MODEL as GAP_MODEL


def cmd_build():
    print("Step 1/4: Generating synthetic data...")
    generate_all()
    
    print("\nStep 2/4: Merging BFS scenario...")
    merge_bfs_scenario()

    print("\nStep 2b/4: Merging IRS renewal scenario...")
    merge_irs_scenario()

    print("\nStep 2c/4: Merging BEP renewal scenario...")
    merge_bep_scenario()

    print("\nStep 2d/4: Merging signed CEBDs...")
    merge_signed_cebds()

    print("\nStep 2e/4: Merging pipeline intakes (R-05522, R-02233)...")
    merge_pipeline_intakes()

    print("\nStep 3/3: Loading and chunking all corpora...")
    docs = load_all_documents()
    structured_chunks = load_structured_intake_chunks()
    all_docs = docs + structured_chunks
    print(f"  Total chunks: {len(all_docs)}")

    print("\nStep 4/4: Building vector store (fitting embedding backend)...")
    build_vector_store(all_docs, persist=True)
    print("\nDone. Vector store persisted to output/chroma_store/")
    print("Run `python3 main.py demo` to see it in action.")


def _print_results(results, label):
    print(f"\n--- {label} ({len(results)} results) ---")
    if not results:
        print("  (none)")
        return
    for r in results:
        meta = r.metadata
        flags = []
        if meta.get("superseded"):
            flags.append("SUPERSEDED")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        contract = meta.get("contract_value_usd")
        try:
            contract_str = f" | contract_value_usd=${float(contract):,.2f}" if contract and str(contract).lower() != "none" else ""
        except (TypeError, ValueError):
            contract_str = ""
        print(f"  [{meta.get('doc_type')}] {meta.get('source_id')} "
              f"| bureau={meta.get('bureau')} | date={meta.get('date')}{contract_str}{flag_str}")
        preview = r.page_content.replace("\n", " ")[:110]
        print(f"      {preview}...")


def cmd_demo():
    store = load_vector_store()

    _print_results(
        retrieve(store, "approval status for Bureau token request", k=5),
        "Demo 1: General semantic query, top-5 default",
    )

    _print_results(
        retrieve_intake_scoped(store, "vendor pricing quote", intake_id="R-1001", k=3),
        "Demo 2: Intake-scoped retrieval (tight k=3, no cross-intake noise)",
    )

    _print_results(
        retrieve(store, "pricing quote", intake_id="R-1001", doc_type="vendor_quote", k=5),
        "Demo 3a: Superseded EXCLUDED by default",
    )
    _print_results(
        retrieve(store, "pricing quote", intake_id="R-1001", doc_type="vendor_quote", k=5, include_superseded=True),
        "Demo 3b: Superseded INCLUDED on request",
    )

    active = get_active_version(store, intake_id="R-1001", doc_type="vendor_quote", section="pricing")
    print("\n--- Demo 4: Direct active-version lookup (bypasses semantic search) ---")
    print(f"  {active.metadata if active else 'None found'}")

    _print_results(
        retrieve(store, "token allocation issue", bureau="IRS", k=5),
        "Demo 5: Bureau-filtered query",
    )

    print("\n--- Demo 6: Dashboard push simulation (single new intake) ---")
    handle_new_intake_event(store, intake_id="R-1003")

    print("\n--- Demo 7: Dashboard Bureau summary refresh (aggregation via retrieval) ---")
    summary = refresh_bureau_summary(store, bureaus=["BFS", "IRS", "OCC"])
    for bureau, totals in summary.items():
        print(f"  {bureau}: {totals}")

    print("\n--- Demo 8: Precise structured aggregation (NOT retrieval-based) ---")
    intakes = load_structured_intakes()
    print(aggregate_tokens_by_bureau(intakes).to_string())


def cmd_query(question: str, bureau: str | None, intake: str | None, doc_type: str | None):
    store = load_vector_store()
    results = retrieve(store, question, bureau=bureau, intake_id=intake, doc_type=doc_type, k=5)
    _print_results(results, f"Query: \"{question}\"")


def _load_provider_query_agent():
    """Loads ProviderQueryAgent from its subfolder (path contains spaces)."""
    agent_path = (
        Path(__file__).parent
        / "Provider Query Agent"
        / "provider_query_agent"
        / "agents"
        / "provider_query_agent.py"
    )
    spec = importlib.util.spec_from_file_location("provider_query_agent", agent_path)
    module = importlib.util.module_from_spec(spec)
    # Make the tools subfolder importable for the agent module
    tools_path = str(agent_path.parent.parent / "tools")
    if tools_path not in sys.path:
        sys.path.insert(0, tools_path)
    spec.loader.exec_module(module)
    return module.ProviderQueryAgent


def cmd_run():
    print("=" * 60)
    print("Step 1/2: Running Provider Query Agent...")
    print("=" * 60)
    ProviderQueryAgent = _load_provider_query_agent()
    pqa = ProviderQueryAgent()
    pqa_result = pqa.run()
    bureaus_found = [b["bureau"] for b in pqa_result.get("bureaus", [])]
    print(f"  Provider Query Agent complete. Bureaus: {bureaus_found}")

    print("\n" + "=" * 60)
    print("Step 2/2: Running Aggregator Agent (RAG join + dashboard output)...")
    print("=" * 60)
    agg = AggregatorAgent()
    agg_result = agg.run()

    print("\n" + "=" * 60)
    print("Run complete.")
    print(f"  Overall data quality : {agg_result['overall_data_quality']}")
    print(f"  Usage monitor rows   : {len(agg_result['usage_monitor'])}")
    print(f"  Intake pipeline rows : {len(agg_result['intake_pipeline'])}")
    print(f"  Errors logged        : {len(agg_result['errors'])}")
    print(f"  Output               : output/aggregator_output.json")
    if agg_result["errors"]:
        print(f"  Error log            : output/aggregator_error_log.json")

    print("\n" + "=" * 60)
    print("Step 3/3: Running Gap Analysis Agent (Claude API)...")
    print("=" * 60)
    gap_agent = GapAnalysisAgent()
    gap_result = gap_agent.run()

    render_dashboard(agg_result, gap_result, GAP_MODEL)


def cmd_aggregate():
    intakes = load_structured_intakes()
    df = aggregate_tokens_by_bureau(intakes)
    print("Bureau x Token Type aggregation (precise, structured -- not semantic search):\n")
    print(df.to_string())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("build", help="Generate data, ingest, build vector store")
    sub.add_parser("demo", help="Run fixed demo queries")
    sub.add_parser("aggregate", help="Print structured Bureau x Token Type table")
    sub.add_parser("run", help="Run Provider Query Agent + Aggregator Agent pipeline")

    q = sub.add_parser("query", help="Ask an ad hoc question")
    q.add_argument("question")
    q.add_argument("--bureau", default=None)
    q.add_argument("--intake", default=None)
    q.add_argument("--doc-type", default=None, dest="doc_type")

    args = parser.parse_args()

    if args.command == "build":
        cmd_build()
    elif args.command == "demo":
        cmd_demo()
    elif args.command == "aggregate":
        cmd_aggregate()
    elif args.command == "query":
        cmd_query(args.question, args.bureau, args.intake, args.doc_type)
    elif args.command == "run":
        cmd_run()


if __name__ == "__main__":
    main()
