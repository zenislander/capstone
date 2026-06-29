"""
Merges the BFS R-05642 renewal scenario (bfs_scenario/bfs_emails.json)
into the base synthetic corpus.

R-05642 is a renewal of R-04321 for $50,000 (same as original),
currently at Customer Estimate Approval stage. Email thread covers stages
01-Inquiry through 07-CustEstimateApproval (23 emails, CEBD sent to BFS
for signature).

IMPORTANT: data_generator.py's generate_all() overwrites data/*.json from
scratch every time it runs. This script must run AFTER data_generator.py
and BEFORE the vector store is built. main.py's `build` command calls
these in the correct order automatically.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
BFS_SCENARIO_DIR = Path(__file__).parent / "bfs_scenario"

BFS_INTAKE_RECORD = {
    "intake_id": "R-05642",
    "ticket_id": "SNOW-21094",
    "bureau": "BFS",
    "requester": "Alisha Squires",
    "token_type": "Anthropic Claude",
    "vendor": "Anthropic",
    "token_amount": 50000,
    "model_spec": "claude-sonnet-4-6 (via Bedrock)",
    "stage": "CEBD Drafted",
    "created_offset": 1002,
    "renewal_of": "R-04321",
    "intake_source": "scenario",
}


def merge_bfs_scenario() -> None:
    bfs_emails_path = BFS_SCENARIO_DIR / "bfs_emails.json"
    if not bfs_emails_path.exists():
        print("No bfs_scenario/bfs_emails.json found -- skipping BFS merge.")
        return

    bfs_emails = json.load(open(bfs_emails_path))

    emails_path = DATA_DIR / "emails.json"
    existing_emails = json.load(open(emails_path))
    existing_ids = {e["email_id"] for e in existing_emails}
    new_emails = [e for e in bfs_emails if e["email_id"] not in existing_ids]
    merged_emails = existing_emails + new_emails
    with open(emails_path, "w") as f:
        json.dump(merged_emails, f, indent=2)

    intakes_path = DATA_DIR / "intakes.json"
    existing_intakes = json.load(open(intakes_path))
    existing_intake_ids = {i["intake_id"] for i in existing_intakes}
    added_intake = 0
    if BFS_INTAKE_RECORD["intake_id"] not in existing_intake_ids:
        existing_intakes.append(BFS_INTAKE_RECORD)
        added_intake = 1
        with open(intakes_path, "w") as f:
            json.dump(existing_intakes, f, indent=2)

    print(
        f"Merged BFS scenario: +{len(new_emails)} emails, "
        f"+{added_intake} intake "
        f"(R-05642, BFS, $50,000 Anthropic Claude renewal of R-04321, stage: CEBD Drafted)"
    )


if __name__ == "__main__":
    merge_bfs_scenario()
