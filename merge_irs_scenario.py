"""
Merges the IRS R-05526 renewal scenario (irs_scenario/irs_emails.json)
into the base synthetic corpus.

R-05526 is a renewal of R-01234 for $10,000 (vs. $100,000 original),
currently at Cost Estimation stage. Email thread covers stages
01-Inquiry through 03-Estimation (9 emails, ROM in progress).

IMPORTANT: data_generator.py's generate_all() overwrites data/*.json from
scratch every time it runs. This script must run AFTER data_generator.py
and BEFORE the vector store is built. main.py's `build` command calls
these in the correct order automatically.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
IRS_SCENARIO_DIR = Path(__file__).parent / "irs_scenario"

IRS_INTAKE_RECORD = {
    "intake_id": "R-05526",
    "ticket_id": "SNOW-21092",
    "bureau": "IRS",
    "requester": "Angela Davis",
    "token_type": "Anthropic Claude",
    "vendor": "Anthropic",
    "token_amount": 10000,
    "model_spec": "claude-sonnet-4-6",
    "stage": "Cost Estimation",
    "created_offset": 1000,
    "renewal_of": "R-01234",
    "intake_source": "scenario",
}


def merge_irs_scenario() -> None:
    irs_emails_path = IRS_SCENARIO_DIR / "irs_emails.json"
    if not irs_emails_path.exists():
        print("No irs_scenario/irs_emails.json found -- skipping IRS merge.")
        return

    irs_emails = json.load(open(irs_emails_path))

    emails_path = DATA_DIR / "emails.json"
    existing_emails = json.load(open(emails_path))
    existing_ids = {e["email_id"] for e in existing_emails}
    new_emails = [e for e in irs_emails if e["email_id"] not in existing_ids]
    merged_emails = existing_emails + new_emails
    with open(emails_path, "w") as f:
        json.dump(merged_emails, f, indent=2)

    intakes_path = DATA_DIR / "intakes.json"
    existing_intakes = json.load(open(intakes_path))
    existing_intake_ids = {i["intake_id"] for i in existing_intakes}
    added_intake = 0
    if IRS_INTAKE_RECORD["intake_id"] not in existing_intake_ids:
        existing_intakes.append(IRS_INTAKE_RECORD)
        added_intake = 1
        with open(intakes_path, "w") as f:
            json.dump(existing_intakes, f, indent=2)

    print(
        f"Merged IRS scenario: +{len(new_emails)} emails, "
        f"+{added_intake} intake "
        f"(R-05526, IRS, $10,000 Anthropic Claude renewal of R-01234, stage: Cost Estimation)"
    )


if __name__ == "__main__":
    merge_irs_scenario()
