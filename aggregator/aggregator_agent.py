"""
Aggregator Agent

Joins the Provider Query Agent's output (token usage + spend by bureau/model)
with the RAG Agent's output (active signed CEBDs, intake pipeline) to produce
a dashboard-ready JSON with two sections:

  1. usage_monitor  — spend vs. contract value, % consumed, 75% threshold flag,
                      per-model breakdown, data quality annotation
  2. intake_pipeline — active intake requests and their current pipeline stage
                       per bureau, sourced from the RAG vector store

Reliability model (three data quality states):
  - success    : provider data is fresh, active signed CEBD found, join complete
  - incomplete : one provider tool failed OR signed CEBD missing for a bureau
  - failed     : provider output missing entirely OR timestamp unchanged (stale)

Anomalies are never silently dropped — every non-success state is:
  1. Logged to output/aggregator_error_log.json
  2. Surfaced as an anomalies[] entry on the affected dashboard row
  3. Sent as an admin email alert (stub — see notify_admin())
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from retrieval.store import load_vector_store, retrieve

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROVIDER_OUTPUT_PATH = (
    ROOT / "Provider Query Agent" / "provider_query_agent" / "data" / "provider_query_output.json"
)
CONTRACTS_PATH = (
    ROOT / "Provider Query Agent" / "provider_query_agent" / "data" / "contracts.json"
)
OUTPUT_DIR = ROOT / "output"
AGGREGATOR_OUTPUT_PATH = OUTPUT_DIR / "aggregator_output.json"
ERROR_LOG_PATH = OUTPUT_DIR / "aggregator_error_log.json"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
THRESHOLD = 0.75
ADMIN_EMAIL = "dashboard-admin@treasury.gov"

INTAKE_PIPELINE_QUERY = (
    "current stage status of token allocation request intake pipeline"
)

STAGE_ORDER = {
    "Intake Received": 1,
    "Technical Review": 2,
    "Cost Estimation": 3,
    "Approved": 4,
    "CEBD Drafted": 5,
    "Provisioned": 6,
}

STAGE_DISPLAY = {
    "Intake Received": "Inquiry",
    "Technical Review": "Discovery",
    "Cost Estimation": "Estimation",
    "Approved": "Executive approval",
    "CEBD Drafted": "Customer estimate approval",
    "Provisioned": "Provisioned",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path):
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def notify_admin(subject: str, body: str) -> None:
    """
    STUB — simulates sending an alert email to the designated admin.
    In production replace with smtplib or an email API:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["To"] = ADMIN_EMAIL
        msg.set_content(body)
        smtp.send_message(msg)
    """
    print(f"\n[EMAIL ALERT] To: {ADMIN_EMAIL}")
    print(f"  Subject: {subject}")
    print(f"  Body:    {body}")


def _log_error(errors: list, source: str, bureau: str, message: str) -> None:
    entry = {
        "timestamp": _now(),
        "level": "ERROR",
        "source": source,
        "bureau": bureau,
        "message": message,
    }
    errors.append(entry)
    print(f"[ERROR] {entry['timestamp']} | {source} | {bureau} | {message}")


def _detect_staleness(current_provider: dict, previous_output: dict | None) -> tuple[str, list]:
    """
    Compares the provider output timestamp against the previous aggregator run.
    Returns (quality_status, anomalies[]).
    """
    anomalies = []
    if previous_output is None:
        return "success", anomalies

    prev_ts = previous_output.get("provider_generated_at")
    curr_ts = current_provider.get("generated_at")

    if prev_ts and curr_ts and curr_ts == prev_ts:
        msg = (
            f"Provider output timestamp unchanged from previous run ({prev_ts}) "
            "— data may be stale."
        )
        anomalies.append(msg)
        return "failed", anomalies

    return "success", anomalies


# ---------------------------------------------------------------------------
# RAG queries
# ---------------------------------------------------------------------------
def _query_active_cebd(store, bureau: str) -> dict | None:
    """
    Query: 'show me all active signed CEBDs' filtered by bureau + doc_type.
    Returns contract metadata or None if not found.
    """
    results = retrieve(
        store,
        query="show me all active signed CEBDs",
        bureau=bureau,
        doc_type="signed CEBD",
        k=1,
    )
    if not results:
        return None
    meta = results[0].metadata
    return {
        "request_id": meta.get("intake_id"),
        "contract_value_usd": meta.get("contract_value_usd"),
        "contract_date": meta.get("date"),
        "source_id": meta.get("source_id"),
    }


def _query_intake_pipeline(store, bureau: str) -> list[dict]:
    """
    Queries for scenario-tagged, non-Provisioned intake records for a bureau.
    Returns deduped entries with renews_for and raw stage for sorting.
    """
    results = retrieve(
        store,
        query=INTAKE_PIPELINE_QUERY,
        bureau=bureau,
        doc_type="structured_intake",
        k=20,
    )
    seen = set()
    entries = []
    for r in results:
        meta = r.metadata
        intake_id = meta.get("intake_id")
        stage = str(meta.get("stage", "none"))
        source = str(meta.get("intake_source", "none")).lower()

        if stage in ("Provisioned", "none") or source != "scenario":
            continue
        if intake_id in seen:
            continue
        seen.add(intake_id)

        renewal_raw = meta.get("renewal_of", "none")
        entries.append({
            "request_id": intake_id,
            "stage_raw": stage,
            "renews_for": renewal_raw if str(renewal_raw).lower() not in ("none", "") else None,
        })
    return entries


def _build_intake_pipeline_section(store, bureaus: list) -> list[dict]:
    """
    Builds the dashboard intake pipeline section.
    Renewals first (sorted by stage advancement), then non-renewals (same
    sort), then "No request found" for bureaus with no in-flight intakes.
    """
    renewals = []
    non_renewals = []
    no_request = []

    for bureau in bureaus:
        entries = _query_intake_pipeline(store, bureau)
        if not entries:
            no_request.append({
                "bureau": bureau,
                "request_id": None,
                "stage": "No request found",
                "renews_for": None,
            })
            continue
        for e in entries:
            row = {
                "bureau": bureau,
                "request_id": e["request_id"],
                "stage": STAGE_DISPLAY.get(e["stage_raw"], e["stage_raw"]),
                "renews_for": e["renews_for"],
            }
            order_key = STAGE_ORDER.get(e["stage_raw"], 0)
            if e["renews_for"]:
                renewals.append((order_key, row))
            else:
                non_renewals.append((order_key, row))

    renewals.sort(key=lambda x: x[0])
    non_renewals.sort(key=lambda x: x[0])

    return [r for _, r in renewals] + [r for _, r in non_renewals] + no_request


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------
class AggregatorAgent:
    name = "aggregator_agent"

    def run(self) -> dict:
        errors = []
        generated_at = _now()

        print(f"\n[Aggregator] Starting run at {generated_at}")

        # ----------------------------------------------------------------
        # 1. Load provider output — hard failure if missing
        # ----------------------------------------------------------------
        provider_output = _load_json(PROVIDER_OUTPUT_PATH)
        previous_output = _load_json(AGGREGATOR_OUTPUT_PATH)

        if provider_output is None:
            msg = "provider_query_output.json not found — Provider Query Agent may not have run."
            _log_error(errors, "aggregator", "ALL", msg)
            notify_admin(
                subject="DASHBOARD ERROR: Provider Query output missing",
                body=msg,
            )
            result = {
                "agent": self.name,
                "generated_at": generated_at,
                "overall_data_quality": "failed",
                "usage_monitor": [],
                "intake_pipeline": [],
                "errors": errors,
            }
            _write_json(AGGREGATOR_OUTPUT_PATH, result)
            _write_json(ERROR_LOG_PATH, errors)
            return result

        # ----------------------------------------------------------------
        # 2. Staleness check via timestamp comparison
        # ----------------------------------------------------------------
        provider_quality, provider_anomalies = _detect_staleness(
            provider_output, previous_output
        )

        if provider_anomalies:
            for msg in provider_anomalies:
                _log_error(errors, "provider_query_agent", "ALL", msg)
            notify_admin(
                subject="DASHBOARD WARNING: Stale provider data detected",
                body="\n".join(provider_anomalies),
            )

        # ----------------------------------------------------------------
        # 2b. Failed data sources (e.g. GCP tool outage)
        # ----------------------------------------------------------------
        failed_sources = provider_output.get("failed_sources", [])
        if "gcp" in failed_sources:
            gcp_msg = (
                "GCP Cloud Logging tool failed — Vertex AI spend is absent. "
                "Bureau totals reflect AWS Bedrock only and are UNDERSTATED. "
                "Threshold calculations are unreliable until GCP data is restored."
            )
            provider_anomalies.append(gcp_msg)
            if provider_quality == "success":
                provider_quality = "incomplete"
            _log_error(errors, "provider_query_agent", "ALL", gcp_msg)
            notify_admin(
                subject="DASHBOARD WARNING: GCP Cloud Logging tool failed",
                body=gcp_msg,
            )

        # ----------------------------------------------------------------
        # 3. Build bureau spend lookup
        # ----------------------------------------------------------------
        spend_by_bureau = {b["bureau"]: b for b in provider_output.get("bureaus", [])}

        # ----------------------------------------------------------------
        # 4. Load contracts (Bureau / Request ID pairs)
        # ----------------------------------------------------------------
        contracts = _load_json(CONTRACTS_PATH) or []

        # ----------------------------------------------------------------
        # 5. Load RAG vector store once — reused for all bureau queries
        # ----------------------------------------------------------------
        print("[Aggregator] Loading RAG vector store...")
        store = load_vector_store()

        usage_monitor = []

        # ----------------------------------------------------------------
        # 6. Per Bureau / Request ID: query RAG, join, compute threshold
        # ----------------------------------------------------------------
        for contract in contracts:
            bureau = contract["bureau"]
            request_id = contract["request_id"]
            row_anomalies = list(provider_anomalies)

            print(f"[Aggregator] Processing {bureau} / {request_id}...")

            # -- Active signed CEBD lookup --------------------------------
            cebd = _query_active_cebd(store, bureau)

            if cebd is None:
                msg = (
                    f"No active signed CEBD found in RAG for {bureau} / {request_id}. "
                    "Threshold calculation not possible — human review required."
                )
                _log_error(errors, "rag_agent", bureau, msg)
                notify_admin(
                    subject=f"DASHBOARD ERROR: No active contract found for {bureau}",
                    body=msg,
                )
                row_anomalies.append(msg)
                contract_value_usd = None
                pct_consumed = None
                threshold_flag = None
                row_quality = "incomplete"
            else:
                contract_value_usd = cebd.get("contract_value_usd")
                spend = spend_by_bureau.get(bureau, {}).get("total_spend_usd", 0.0)
                pct_consumed = (
                    round(spend / contract_value_usd, 4)
                    if contract_value_usd
                    else None
                )
                threshold_flag = (
                    pct_consumed >= THRESHOLD if pct_consumed is not None else None
                )
                row_quality = provider_quality

                if threshold_flag:
                    msg = (
                        f"{bureau} has consumed {pct_consumed * 100:.1f}% of contract value "
                        f"(${spend:,.2f} of ${contract_value_usd:,}) — "
                        f"threshold of {THRESHOLD * 100:.0f}% exceeded."
                    )
                    _log_error(errors, "aggregator", bureau, msg)
                    notify_admin(
                        subject=f"DASHBOARD ALERT: {bureau} at {pct_consumed * 100:.1f}% contract consumption",
                        body=msg,
                    )
                    row_anomalies.append(msg)

            spend_entry = spend_by_bureau.get(bureau, {})

            usage_monitor.append({
                "bureau": bureau,
                "request_id": request_id,
                "contract_value_usd": contract_value_usd,
                "total_spend_usd": spend_entry.get("total_spend_usd"),
                "total_input_tokens": spend_entry.get("total_input_tokens"),
                "total_output_tokens": spend_entry.get("total_output_tokens"),
                "pct_consumed": pct_consumed,
                "threshold_flag": threshold_flag,
                "data_quality": row_quality,
                "anomalies": row_anomalies,
                "models": spend_entry.get("models", []),
            })

        # ----------------------------------------------------------------
        # 7a. Build intake pipeline section
        #     Only bureaus where a signed CEBD was found (contract_value_usd
        #     is not None) are included — US Mint (INCOMPLETE) is excluded.
        # ----------------------------------------------------------------
        active_cebd_bureaus = [
            row["bureau"] for row in usage_monitor if row["contract_value_usd"] is not None
        ]
        print(f"[Aggregator] Building intake pipeline for: {active_cebd_bureaus}")
        intake_pipeline_section = _build_intake_pipeline_section(store, active_cebd_bureaus)

        # ----------------------------------------------------------------
        # 7b. Determine overall quality
        # ----------------------------------------------------------------
        qualities = [row["data_quality"] for row in usage_monitor]
        if all(q == "success" for q in qualities):
            overall_quality = "success"
        elif all(q == "failed" for q in qualities):
            overall_quality = "failed"
        else:
            overall_quality = "incomplete"

        # ----------------------------------------------------------------
        # 8. Write outputs
        # ----------------------------------------------------------------
        output = {
            "agent": self.name,
            "generated_at": generated_at,
            "provider_generated_at": provider_output.get("generated_at"),
            "overall_data_quality": overall_quality,
            "failed_data_sources": failed_sources,
            "usage_monitor": usage_monitor,
            "intake_pipeline": intake_pipeline_section,
            "errors": errors,
        }

        _write_json(AGGREGATOR_OUTPUT_PATH, output)
        print(f"[Aggregator] Output written to {AGGREGATOR_OUTPUT_PATH}")

        if errors:
            _write_json(ERROR_LOG_PATH, errors)
            print(f"[Aggregator] Error log written to {ERROR_LOG_PATH} ({len(errors)} entries)")

        print(f"[Aggregator] Done. Overall data quality: {overall_quality}")
        return output


if __name__ == "__main__":
    agent = AggregatorAgent()
    result = agent.run()
    print(json.dumps(result, indent=2))
