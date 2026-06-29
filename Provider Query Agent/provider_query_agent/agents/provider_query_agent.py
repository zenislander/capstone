"""
Provider Query Agent

Description: Queries cloud providers to determine AI token utilization
and the amount spent per LLM model, per Bureau.

Skill: Invokes its query tools — the AWS Query tool (Bedrock + Cost
Explorer) and GCP Query tool (Vertex AI + Cost Explorer) — when
instructed by the Orchestrator. Each tool writes its results to a JSON
file and forwards them to the Aggregator Agent.

System prompt: "Find how many tokens each Bureau (e.g., BFS, US Mint)
has used per model and how much they have spent, using the provider
query tools."

Scope note: this agent returns usage and cost only — tokens and dollars
spent, by Bureau and model. It has no knowledge of contract value,
request IDs, or the 75% threshold. Joining usage against contract value
(sourced from the RAG Agent / intake system) and computing
threshold-crossed status is gap analysis logic and belongs to the
Aggregator Agent, which is the only component that receives both this
agent's output and the RAG Agent's output together.
"""
import json
import os
import sys
from datetime import datetime, timezone
from collections import defaultdict

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "tools"))
from aws_query_tool import query_aws_bedrock_usage
from gcp_query_tool import query_gcp_vertex_usage

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "provider_query_output.json")

SYSTEM_PROMPT = (
    "Find how many tokens each Bureau (e.g., BFS, US Mint) has used per "
    "model and how much they have spent, using the provider query tools."
)


class ProviderQueryAgent:
    name = "provider_query_agent"
    system_prompt = SYSTEM_PROMPT

    def run(self, instructions: str = None):
        """
        Entry point called by the Orchestrator. Invokes both provider
        tools and merges results by Bureau and model. Writes the
        combined result to a JSON file for the Aggregator Agent to
        consume. Returns usage and cost only — no contract value, no
        percentage-of-threshold, no threshold flag. That join happens
        downstream in the Aggregator Agent, once RAG Agent output
        (contract value, request ID) is also available.
        """
        failed_sources = []

        aws_results = query_aws_bedrock_usage()

        try:
            gcp_results = query_gcp_vertex_usage()
        except Exception as e:
            print(f"\n[WARNING] GCP tool failure: {e}")
            print("[WARNING] Continuing with AWS Bedrock data only — GCP spend will be absent.")
            gcp_results = []
            failed_sources.append("gcp")

        all_results = aws_results + gcp_results

        by_bureau = defaultdict(lambda: {
            "total_spend_usd": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "models": []
        })

        for row in all_results:
            bureau_entry = by_bureau[row["bureau"]]
            bureau_entry["total_spend_usd"] += row["cost_usd"]
            bureau_entry["total_input_tokens"] += row["input_tokens"]
            bureau_entry["total_output_tokens"] += row["output_tokens"]
            bureau_entry["models"].append({
                "provider": row["provider"],
                "model": row["model"],
                "input_tokens": row["input_tokens"],
                "output_tokens": row["output_tokens"],
                "cost_usd": row["cost_usd"]
            })

        bureaus_output = []
        for bureau, entry in by_bureau.items():
            bureaus_output.append({
                "bureau": bureau,
                "total_spend_usd": round(entry["total_spend_usd"], 2),
                "total_input_tokens": entry["total_input_tokens"],
                "total_output_tokens": entry["total_output_tokens"],
                "models": entry["models"]
            })

        output = {
            "agent": self.name,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "failed_sources": failed_sources,
            "bureaus": bureaus_output
        }

        with open(OUTPUT_PATH, "w") as f:
            json.dump(output, f, indent=2)

        return output


if __name__ == "__main__":
    agent = ProviderQueryAgent()
    result = agent.run(instructions="daily_run")
    print(json.dumps(result, indent=2))
