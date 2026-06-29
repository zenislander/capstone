"""
Merges two in-flight non-renewal intake records into the base corpus:

  R-05522  IRS   Technical Review   (maps to "Discovery" on the dashboard)
  R-02233  BFS   Approved           (maps to "Executive approval" on the dashboard)

Neither is a renewal. They represent independent new LLM token requests from
IRS and BFS that are currently moving through the TCSC intake pipeline.

IMPORTANT: data_generator.py's generate_all() overwrites data/intakes.json
from scratch every time it runs. This script must run AFTER data_generator.py
and BEFORE the vector store is built. main.py's `build` command calls these
in the correct order automatically.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

PIPELINE_INTAKES = [
    {
        "intake_id": "R-05522",
        "ticket_id": "SNOW-21088",
        "bureau": "IRS",
        "requester": "Marcus Webb",
        "token_type": "Anthropic Claude",
        "vendor": "Anthropic",
        "token_amount": 25000,
        "model_spec": "claude-sonnet-4-6",
        "stage": "Technical Review",
        "created_offset": 998,
        "intake_source": "scenario",
    },
    {
        "intake_id": "R-02233",
        "ticket_id": "SNOW-21087",
        "bureau": "BFS",
        "requester": "David Morales",
        "token_type": "Anthropic Claude",
        "vendor": "Anthropic",
        "token_amount": 75000,
        "model_spec": "claude-sonnet-4-6 (via Bedrock)",
        "stage": "Approved",
        "created_offset": 997,
        "intake_source": "scenario",
    },
]


def merge_pipeline_intakes() -> None:
    intakes_path = DATA_DIR / "intakes.json"
    existing_intakes = json.load(open(intakes_path))
    existing_ids = {i["intake_id"] for i in existing_intakes}

    added = []
    for record in PIPELINE_INTAKES:
        if record["intake_id"] not in existing_ids:
            existing_intakes.append(record)
            added.append(record["intake_id"])

    if added:
        with open(intakes_path, "w") as f:
            json.dump(existing_intakes, f, indent=2)

    summary = ", ".join(
        f"{r['intake_id']} ({r['bureau']}, {r['stage']})"
        for r in PIPELINE_INTAKES
    )
    print(f"Merged pipeline intakes: +{len(added)} records ({summary})")


if __name__ == "__main__":
    merge_pipeline_intakes()
