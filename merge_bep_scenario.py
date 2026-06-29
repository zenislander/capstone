"""
Merges the BEP R-07788 renewal scenario (bep_scenario/bep_emails.json)
into the base synthetic corpus.

R-07788 is a renewal of R-07765 for $5,000 (vs. $50,000 original),
currently at Executive Approval stage. Email thread covers stages
01-Inquiry through 05-ExecApproval (16 emails).

IMPORTANT: data_generator.py's generate_all() overwrites data/*.json from
scratch every time it runs. This script must run AFTER data_generator.py
and BEFORE the vector store is built. main.py's `build` command calls
these in the correct order automatically.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
BEP_SCENARIO_DIR = Path(__file__).parent / "bep_scenario"

BEP_INTAKE_RECORD = {
    "intake_id": "R-07788",
    "ticket_id": "SNOW-21093",
    "bureau": "BEP",
    "requester": "Kimberly Freed",
    "token_type": "Anthropic Claude",
    "vendor": "Anthropic",
    "token_amount": 5000,
    "model_spec": "claude-sonnet-4-6 (via Bedrock)",
    "stage": "Approved",
    "created_offset": 1001,
    "renewal_of": "R-07765",
    "intake_source": "scenario",
}


def merge_bep_scenario() -> None:
    bep_emails_path = BEP_SCENARIO_DIR / "bep_emails.json"
    if not bep_emails_path.exists():
        print("No bep_scenario/bep_emails.json found -- skipping BEP merge.")
        return

    bep_emails = json.load(open(bep_emails_path))

    emails_path = DATA_DIR / "emails.json"
    existing_emails = json.load(open(emails_path))
    existing_ids = {e["email_id"] for e in existing_emails}
    new_emails = [e for e in bep_emails if e["email_id"] not in existing_ids]
    merged_emails = existing_emails + new_emails
    with open(emails_path, "w") as f:
        json.dump(merged_emails, f, indent=2)

    intakes_path = DATA_DIR / "intakes.json"
    existing_intakes = json.load(open(intakes_path))
    existing_intake_ids = {i["intake_id"] for i in existing_intakes}
    added_intake = 0
    if BEP_INTAKE_RECORD["intake_id"] not in existing_intake_ids:
        existing_intakes.append(BEP_INTAKE_RECORD)
        added_intake = 1
        with open(intakes_path, "w") as f:
            json.dump(existing_intakes, f, indent=2)

    print(
        f"Merged BEP scenario: +{len(new_emails)} emails, "
        f"+{added_intake} intake "
        f"(R-07788, BEP, $5,000 Anthropic Claude renewal of R-07765, stage: Approved)"
    )


if __name__ == "__main__":
    merge_bep_scenario()
