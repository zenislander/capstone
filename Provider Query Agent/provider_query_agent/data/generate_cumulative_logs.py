"""
Generates AWS Bedrock and GCP Vertex AI mock invocation logs representing
CUMULATIVE usage since each contract went into execution (signed CEBD
date) through today, rather than a fixed 5-day window.

Design choice, stated explicitly: per-call token sizes and per-token
prices are kept realistic (real Anthropic/Google rates, real single-call
token ranges). A single scaling factor is applied per Bureau so that the
cumulative dollar total matches the dashboard mockup's target percentage
of contract value. This keeps the LOG STRUCTURE and PRICING fully
realistic; only the call VOLUME is calibrated to hit the target, which is
the one variable that should reasonably differ a lot Bureau to Bureau in
practice (some Bureaus simply use the service far more than others).
"""
import json
import csv
import random
from datetime import datetime, timedelta, timezone

random.seed(42)

TODAY = datetime(2026, 6, 28, tzinfo=timezone.utc)

# Real contract execution start dates, extracted from signed CEBDs.
# US Mint has no signed CEBD on record - flagged explicitly, placeholder
# start date used only so the mock log has *a* value; the Aggregator
# Agent's gap analysis should treat US Mint as a missing-record /
# human-in-the-loop case, not silently trust this placeholder.
CONTRACTS = [
    {"bureau": "IRS", "request_id": "R-01234", "contract_value_usd": 100000,
     "start": "2026-02-14", "target_pct": 55.0, "cebd_on_file": True},
    {"bureau": "BFS", "request_id": "R-04321", "contract_value_usd": 50000,
     "start": "2026-03-28", "target_pct": 80.0, "cebd_on_file": True},
    {"bureau": "BEP", "request_id": "R-07765", "contract_value_usd": 50000,
     "start": "2026-04-11", "target_pct": 77.0, "cebd_on_file": True},
    {"bureau": "OCC", "request_id": "R-09988", "contract_value_usd": 50000,
     "start": "2026-01-22", "target_pct": 78.0, "cebd_on_file": True},
    {"bureau": "US Mint", "request_id": "R-03311", "contract_value_usd": 60000,
     "start": "2026-02-01", "target_pct": 48.0, "cebd_on_file": False},
]

AWS_MODELS = [
    "anthropic.claude-haiku-4-5-v1:0",
    "anthropic.claude-sonnet-4-6-v1:0",
    "anthropic.claude-opus-4-7-v1:0",
]
AWS_WEIGHTS = [0.55, 0.35, 0.10]

GCP_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro"]
GCP_WEIGHTS = [0.7, 0.3]

AWS_SHARE = 0.65  # illustrative provider split of spend

ACCOUNT_ID = "123456789012"
REGION = "us-east-1"
PROJECT_ID = "treasury-ai-procurement-prod"
LOCATION = "us-central1"

# Moderate, realistic call volume - same order of magnitude as the
# original (first) version of this mock data, NOT scaled into the
# thousands/day. This keeps individual log entries and daily volume
# believable; only the final per-event token size gets one documented
# scale-up pass to reach the target dollar total.
CALLS_PER_DAY_AWS = (5, 10)   # random range, per bureau, per day
CALLS_PER_DAY_GCP = (3, 6)


def load_prices(path):
    prices = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            prices[(row["model_id"], row["token_type"])] = float(row["price_per_1k_tokens_usd"])
    return prices


aws_prices = load_prices("bedrock_pricelist.csv")
gcp_prices = load_prices("vertex_pricelist.csv")


def realistic_tokens():
    return random.randint(150, 4000), random.randint(50, 1500)


def call_cost(model, input_tokens, output_tokens, prices):
    return (input_tokens / 1000) * prices.get((model, "input"), 0) + \
           (output_tokens / 1000) * prices.get((model, "output"), 0)


aws_events = []
gcp_entries = []
calibration_log = []

for c in CONTRACTS:
    bureau = c["bureau"]
    start_date = datetime.strptime(c["start"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    n_days = (TODAY - start_date).days + 1
    target_spend = c["contract_value_usd"] * c["target_pct"] / 100

    # --- Pass 1: generate a realistic, moderate-volume set of calls
    # spread across the full contract-to-date period, at REAL per-call
    # token sizes. Track raw (unscaled) cost as we go. ---
    bureau_aws_calls = []
    bureau_gcp_calls = []
    raw_cost = 0.0

    for day_offset in range(n_days):
        day = start_date + timedelta(days=day_offset)

        n_aws_today = random.randint(*CALLS_PER_DAY_AWS)
        for _ in range(n_aws_today):
            ts = day + timedelta(seconds=random.randint(13 * 3600, 21 * 3600))
            model = random.choices(AWS_MODELS, weights=AWS_WEIGHTS, k=1)[0]
            input_tokens, output_tokens = realistic_tokens()
            cost = call_cost(model, input_tokens, output_tokens, aws_prices)
            raw_cost += cost
            bureau_aws_calls.append((ts, model, input_tokens, output_tokens))

        n_gcp_today = random.randint(*CALLS_PER_DAY_GCP)
        for _ in range(n_gcp_today):
            ts = day + timedelta(seconds=random.randint(13 * 3600, 21 * 3600))
            model = random.choices(GCP_MODELS, weights=GCP_WEIGHTS, k=1)[0]
            input_tokens, output_tokens = realistic_tokens()
            cost = call_cost(model, input_tokens, output_tokens, gcp_prices)
            raw_cost += cost
            bureau_gcp_calls.append((ts, model, input_tokens, output_tokens))

    # --- Pass 2: one documented scale factor to land on the target
    # cumulative dollar total. Applied uniformly to every call's token
    # counts for this bureau, preserving relative call-to-call variation
    # and each model's realistic share of usage. ---
    scale_factor = target_spend / raw_cost if raw_cost > 0 else 1.0

    calibration_log.append({
        "bureau": bureau,
        "contract_start": c["start"],
        "days_in_execution": n_days,
        "n_aws_calls": len(bureau_aws_calls),
        "n_gcp_calls": len(bureau_gcp_calls),
        "raw_unscaled_cost_usd": round(raw_cost, 4),
        "target_spend_usd": round(target_spend, 2),
        "scale_factor_applied": round(scale_factor, 2),
        "cebd_on_file": c["cebd_on_file"]
    })

    for ts, model, input_tokens, output_tokens in bureau_aws_calls:
        scaled_in = max(1, round(input_tokens * scale_factor))
        scaled_out = max(1, round(output_tokens * scale_factor))
        request_id = (
            f"{random.randint(10**7,10**8-1):08x}-{random.randint(1000,9999)}-"
            f"{random.randint(1000,9999)}-{random.randint(1000,9999)}-"
            f"{random.randint(10**11,10**12-1):012x}"
        )
        message = {
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "accountId": ACCOUNT_ID,
            "region": REGION,
            "requestId": request_id,
            "operation": "InvokeModel",
            "modelId": model,
            "bureau": bureau,
            "inputTokenCount": scaled_in,
            "outputTokenCount": scaled_out,
            "inferenceRegion": "in-region"
        }
        aws_events.append({
            "logStreamName": f"bedrock-invocations/{bureau.replace(' ', '-')}",
            "timestamp": int(ts.timestamp() * 1000),
            "message": json.dumps(message)
        })

    for ts, model, input_tokens, output_tokens in bureau_gcp_calls:
        scaled_in = max(1, round(input_tokens * scale_factor))
        scaled_out = max(1, round(output_tokens * scale_factor))
        trace_id = f"{random.randint(10**31, 10**32-1):032x}"
        insert_id = f"{random.randint(10**12, 10**13-1):x}"
        entry = {
            "logName": f"projects/{PROJECT_ID}/logs/aiplatform.googleapis.com%2Fprediction",
            "resource": {
                "type": "aiplatform.googleapis.com/Endpoint",
                "labels": {
                    "project_id": PROJECT_ID,
                    "location": LOCATION,
                    "endpoint_id": "vertex-genai-endpoint"
                }
            },
            "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "severity": "INFO",
            "insertId": insert_id,
            "trace": f"projects/{PROJECT_ID}/traces/{trace_id}",
            "labels": {"bureau": bureau},
            "jsonPayload": {
                "model": model,
                "request": {
                    "endpoint": f"projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{model}"
                },
                "response": {
                    "usageMetadata": {
                        "promptTokenCount": scaled_in,
                        "candidatesTokenCount": scaled_out,
                        "totalTokenCount": scaled_in + scaled_out
                    }
                }
            }
        }
        gcp_entries.append(entry)

aws_events.sort(key=lambda e: e["timestamp"])
gcp_entries.sort(key=lambda e: e["timestamp"])

aws_log = {
    "logGroupName": "/aws/bedrock/model-invocations",
    "logStreams": sorted(set(e["logStreamName"] for e in aws_events)),
    "events": aws_events
}
gcp_log = {
    "logName": f"projects/{PROJECT_ID}/logs/aiplatform.googleapis.com%2Fprediction",
    "entries": gcp_entries
}

with open("bedrock_invocation_log.json", "w") as f:
    json.dump(aws_log, f, indent=2)
with open("vertex_invocation_log.json", "w") as f:
    json.dump(gcp_log, f, indent=2)

with open("log_calibration_notes.json", "w") as f:
    json.dump(calibration_log, f, indent=2)

print(json.dumps(calibration_log, indent=2))
print(f"\nTotal AWS events: {len(aws_events)}")
print(f"Total GCP entries: {len(gcp_entries)}")
