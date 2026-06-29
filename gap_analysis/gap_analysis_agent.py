"""
Gap Analysis Agent

Calls the Claude API (claude-sonnet-4-6) with the aggregator output and
produces a structured per-bureau risk assessment:

  action_required — threshold exceeded, no renewal or renewal too early to land in time
  monitor         — threshold exceeded, renewal close enough to clear before contract runs out
  on_track        — below threshold, no immediate risk
  data_gap        — missing CEBD or failed/incomplete data quality; short-circuits other logic

Output: output/gap_analysis.json
"""

import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

OUTPUT_DIR = ROOT / "output"
AGGREGATOR_OUTPUT_PATH = OUTPUT_DIR / "aggregator_output.json"
GAP_ANALYSIS_OUTPUT_PATH = OUTPUT_DIR / "gap_analysis.json"

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = (
    "You are a contract monitoring agent for the U.S. Treasury Department's "
    "TCloud LLM token intake system. You analyze provider spend data and intake "
    "pipeline status to identify contract consumption risks across bureaus and "
    "recommend actions. Be concise and specific — reference actual request IDs, "
    "dollar amounts, and stage names in your messages."
)

GAP_ANALYSIS_PROMPT = """Analyze the bureau token contract data below and produce a gap analysis.

## Usage Monitor
{usage_monitor}

## Intake Pipeline
{intake_pipeline}

## Status Rules

Assign one status to EVERY bureau in the usage monitor:

- **data_gap**: data_quality is "incomplete" or "failed", OR contract_value_usd is null.
  Short-circuit — do not apply threshold logic. Include these bureaus.

- **on_track**: pct_consumed < 0.75 (below the 75% threshold).

- **monitor**: pct_consumed >= 0.75 AND a renewal request exists in the intake pipeline
  at a late stage (Executive approval or beyond) — close enough to completion that it
  will likely clear before the contract is fully consumed at the current burn rate.

- **action_required**: pct_consumed >= 0.75 AND either:
  (a) No renewal request exists in the intake pipeline for this bureau, OR
  (b) A renewal exists but is at an early stage (Inquiry, Discovery, Estimation,
      or Customer estimate approval) unlikely to complete before the contract runs out.

Note: Customer estimate approval still has multiple stages remaining
(funding prep, funding receipt, contracting, execution) and should be treated
as too early to count as "nearly done" — classify as action_required, not monitor.

## Output

Return ONLY a valid JSON array — no markdown, no explanation, no code fences.
Order: action_required first, then monitor, then on_track, then data_gap.

Each element:
{{
  "bureau": "<bureau name>",
  "request_id": "<signed CEBD request id>",
  "status": "<action_required|monitor|on_track|data_gap>",
  "spend_pct": <integer, e.g. 78>,
  "renewal_request_id": "<renewal request id or null>",
  "renewal_stage": "<display stage name or null>",
  "message": "<2-3 sentence plain English explanation of the situation and recommended action>"
}}"""


def _load_json(path: Path):
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


class GapAnalysisAgent:
    name = "gap_analysis_agent"

    def run(self) -> list[dict] | None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("[Gap Analysis] ANTHROPIC_API_KEY not set — skipping gap analysis.")
            return None

        aggregator_output = _load_json(AGGREGATOR_OUTPUT_PATH)
        if not aggregator_output:
            print("[Gap Analysis] aggregator_output.json not found — run `python main.py run` first.")
            return None

        usage_monitor = aggregator_output.get("usage_monitor", [])
        intake_pipeline = aggregator_output.get("intake_pipeline", [])

        prompt = GAP_ANALYSIS_PROMPT.format(
            usage_monitor=json.dumps(usage_monitor, indent=2),
            intake_pipeline=json.dumps(intake_pipeline, indent=2),
        )

        print(f"[Gap Analysis] Calling {MODEL}...")
        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
        except Exception as e:
            print(f"[Gap Analysis] API call failed: {e}")
            return None

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            # Strip markdown fences if model added them anyway
            import re
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                result = json.loads(match.group())
            else:
                print("[Gap Analysis] Could not parse JSON from response.")
                print(f"  Raw response: {raw[:300]}")
                return None

        _write_json(GAP_ANALYSIS_OUTPUT_PATH, result)
        print(f"[Gap Analysis] Written to {GAP_ANALYSIS_OUTPUT_PATH}")
        return result


if __name__ == "__main__":
    agent = GapAnalysisAgent()
    result = agent.run()
    if result:
        print(json.dumps(result, indent=2))
