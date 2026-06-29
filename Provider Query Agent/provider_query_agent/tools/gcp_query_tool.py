"""
GCP Query tool — used by the Provider Query Agent.

In production this tool would call Google Cloud Logging (Vertex AI
prediction logs) and GCP Cloud Billing / Cost Tables. For this mock
implementation, it reads a pre-generated Cloud Logging-shaped JSON log
and a pricing reference CSV from disk, and produces the same rollup a
live API integration would.
"""
import json
import csv
import os
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
LOG_PATH = os.path.join(DATA_DIR, "vertex_invocation_log.json")
PRICELIST_PATH = os.path.join(DATA_DIR, "vertex_pricelist.csv")

# Set True to simulate a GCP Cloud Logging API outage.
# Revert to False to restore normal GCP data retrieval.
SIMULATE_GCP_FAILURE = False


def _load_pricelist():
    prices = {}
    with open(PRICELIST_PATH) as f:
        for row in csv.DictReader(f):
            prices[(row["model_id"], row["token_type"])] = float(row["price_per_1k_tokens_usd"])
    return prices


def query_gcp_vertex_usage():
    """
    Returns per-Bureau, per-model token usage and cost, sourced from the
    mock Cloud Logging entries (standing in for live Vertex AI prediction
    logs + Cloud Billing).
    """
    if SIMULATE_GCP_FAILURE:
        raise RuntimeError(
            "SIMULATED FAILURE: GCP Cloud Logging API unavailable "
            "(connection timeout after 30s — IAM credentials may have expired)"
        )

    with open(LOG_PATH) as f:
        log = json.load(f)

    prices = _load_pricelist()

    rollup = defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})

    for entry in log["entries"]:
        bureau = entry["labels"]["bureau"]
        model = entry["jsonPayload"]["model"]
        usage = entry["jsonPayload"]["response"]["usageMetadata"]
        input_tokens = usage["promptTokenCount"]
        output_tokens = usage["candidatesTokenCount"]

        input_price = prices.get((model, "input"), 0)
        output_price = prices.get((model, "output"), 0)
        cost = (input_tokens / 1000) * input_price + (output_tokens / 1000) * output_price

        key = (bureau, model)
        rollup[key]["input_tokens"] += input_tokens
        rollup[key]["output_tokens"] += output_tokens
        rollup[key]["cost_usd"] += cost

    results = []
    for (bureau, model), totals in rollup.items():
        results.append({
            "provider": "gcp",
            "bureau": bureau,
            "model": model,
            "input_tokens": totals["input_tokens"],
            "output_tokens": totals["output_tokens"],
            "cost_usd": round(totals["cost_usd"], 4)
        })

    return results


if __name__ == "__main__":
    out = query_gcp_vertex_usage()
    print(json.dumps(out, indent=2))
