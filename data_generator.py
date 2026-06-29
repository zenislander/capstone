"""
Synthetic data generator for the Bureau LLM-token-intake RAG prototype.

Generates four corpora matching the capstone design doc's four sources:
  1. Email archive       -> data/emails.json
  2. ServiceNow tickets   -> data/tickets.json
  3. Document library     -> data/documents.json   (CEBDs, vendor quotes, memos)
  4. Policy corpus        -> data/policy.json

Everything is tied together by `intake_id` and `bureau` so retrieval
filtering (by intake ID or Bureau) has something real to filter on.

Includes a deliberate SUPERSEDED-DOCUMENT scenario: one intake gets two
versions of a vendor quote, the older one flagged `superseded: true`, to
exercise the staleness-mitigation logic described in the capstone doc.
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

# Set to True to suppress synthetic email generation.
# Scenario emails (bfs_scenario, irs_scenario, bep_scenario) will be the
# sole email source. Revert to False to restore full synthetic generation.
SYNTHETIC_EMAILS_DISABLED = False

BUREAUS = ["BFS", "IRS", "OCC", "TIGTA", "US Mint", "BEP"]
TOKEN_TYPES = ["Anthropic Claude", "AWS Bedrock", "OpenAI GPT-4o", "Azure OpenAI"]
VENDORS = ["Anthropic", "Amazon Web Services", "OpenAI", "Microsoft Azure"]
REQUESTERS = [
    "Alisha Squires", "Clyde Bennett", "Jena Whitley", "Angela Davis",
    "Tony Marchetti", "Kenneth Brooks", "Kimberly Freed", "Kayur Shah",
]
STAGES = ["Intake Received", "Technical Review", "Cost Estimation", "CEBD Drafted", "Approved", "Provisioned"]

BASE_DATE = datetime(2026, 1, 6)
OUT_DIR = Path(__file__).parent / "data"


def random_date(start_offset_days: int, spread_days: int = 5) -> datetime:
    return BASE_DATE + timedelta(days=start_offset_days + random.randint(0, spread_days))


def make_intakes(n: int = 18) -> list[dict]:
    """Core intake records -- the spine everything else hangs off of."""
    intakes = []
    for i in range(1, n + 1):
        intake_id = f"R-{1000 + i}"
        bureau = random.choice(BUREAUS)
        token_type = random.choice(TOKEN_TYPES)
        vendor = VENDORS[TOKEN_TYPES.index(token_type)]
        intakes.append({
            "intake_id": intake_id,
            "ticket_id": f"SNOW-{20000 + i}",
            "bureau": bureau,
            "requester": random.choice(REQUESTERS),
            "token_type": token_type,
            "vendor": vendor,
            "token_amount": random.choice([10000, 25000, 50000, 100000, 250000, 500000]),
            "model_spec": {
                "Anthropic Claude": "claude-sonnet-4-6",
                "AWS Bedrock": "claude-sonnet-4-6 (via Bedrock)",
                "OpenAI GPT-4o": "gpt-4o",
                "Azure OpenAI": "gpt-4o (Azure-hosted)",
            }[token_type],
            "stage": random.choice(STAGES),
            "created_offset": i * 4,  # stagger creation dates across the corpus
        })
    return intakes


def make_emails(intakes: list[dict]) -> list[dict]:
    emails = []
    eid = 1

    templates = [
        ("intake_notification", "New Token Request Intake - {bureau} - {intake_id}",
         "Team,\n\n{requester} from {bureau} has submitted a new request for "
         "{token_amount} {token_type} tokens. ServiceNow ticket {ticket_id} has been "
         "opened. Model spec requested: {model_spec}. Please begin technical review.\n\n"
         "Thanks,\nIntake Coordinator"),
        ("status_update", "RE: {intake_id} - Status Update",
         "Hi team,\n\nQuick update on {intake_id} ({bureau}). The request is now in "
         "the {stage} stage. {requester} has been notified. No blockers at this time.\n\n"
         "Will follow up once the CEBD is drafted."),
        ("vendor_followup", "Vendor Quote Follow-up - {intake_id}",
         "Hello,\n\nFollowing up on the vendor quote for {intake_id} ({bureau}, "
         "{vendor}). We need confirmation on pricing for {token_amount} tokens before "
         "we can finalize the CEBD. Can we get this by end of week?\n\nThanks."),
        ("approval_request", "Approval Needed - {intake_id} - {bureau}",
         "Hi Christopher,\n\n{intake_id} for {bureau} is ready for your approval. "
         "Requested: {token_amount} {token_type} tokens ({model_spec}). CEBD is "
         "attached. PMO fee structure: 2.5% pass-through.\n\nPlease advise if you "
         "have questions before sign-off."),
        ("issue_raised", "Issue with {intake_id} - need guidance",
         "Hi team,\n\n{requester} from {bureau} raised a concern that the requested "
         "token amount ({token_amount}) may not cover their Q3 workload based on "
         "current usage patterns. Should we revise the CEBD before submitting for "
         "approval, or proceed and request a supplemental later?\n\nLooking for "
         "guidance on how to handle this."),
    ]

    for intake in intakes:
        # every intake gets an intake notification + 2-4 follow-up emails
        n_followups = random.randint(2, 4)
        chosen = [templates[0]] + random.sample(templates[1:], n_followups)
        for offset, (kind, subj_tpl, body_tpl) in enumerate(chosen):
            date = random_date(intake["created_offset"] + offset * 3, spread_days=2)
            ctx = {**intake}
            emails.append({
                "email_id": f"EMAIL-{eid:04d}",
                "intake_id": intake["intake_id"],
                "bureau": intake["bureau"],
                "doc_type": "email",
                "kind": kind,
                "date": date.strftime("%Y-%m-%d"),
                "sender": "intake-coordinator@treasury.gov" if kind == "intake_notification" else f"{intake['requester'].lower().replace(' ', '.')}@treasury.gov",
                "subject": subj_tpl.format(**ctx),
                "body": body_tpl.format(**ctx),
            })
            eid += 1
    return emails


def make_tickets(intakes: list[dict]) -> list[dict]:
    tickets = []
    for intake in intakes:
        # Each ticket has a stage-transition history up to its current stage
        current_stage_idx = STAGES.index(intake["stage"])
        history = []
        for idx in range(current_stage_idx + 1):
            history.append({
                "stage": STAGES[idx],
                "timestamp": random_date(intake["created_offset"] + idx * 3).strftime("%Y-%m-%d"),
                "note": {
                    "Intake Received": f"Initial request logged for {intake['bureau']}.",
                    "Technical Review": "Confirmed token type and model spec are supported under current contract vehicles.",
                    "Cost Estimation": f"ROM estimate prepared based on {intake['token_amount']} token volume.",
                    "CEBD Drafted": "CEBD document drafted and routed for vendor confirmation.",
                    "Approved": "Approved by Associate CIO for Cloud and Network Services.",
                    "Provisioned": "Token allocation provisioned and confirmed with vendor.",
                }[STAGES[idx]],
            })
        tickets.append({
            "ticket_id": intake["ticket_id"],
            "intake_id": intake["intake_id"],
            "bureau": intake["bureau"],
            "doc_type": "ticket",
            "current_stage": intake["stage"],
            "stage_history": history,
        })
    return tickets


def make_documents(intakes: list[dict]) -> list[dict]:
    """CEBDs and vendor quotes, sectioned (scope / pricing / terms), with one
    deliberate superseded-version scenario."""
    documents = []
    did = 1

    for i, intake in enumerate(intakes):
        # Vendor quote sections
        quote_date = random_date(intake["created_offset"] + 5)
        sections = {
            "scope": f"This quote covers provisioning of {intake['token_amount']} "
                     f"{intake['token_type']} tokens for {intake['bureau']}, model "
                     f"specification {intake['model_spec']}, for the FY27 performance period.",
            "pricing": f"Unit pricing for {intake['vendor']} {intake['token_type']} "
                       f"tokens under the current contract vehicle. Total estimated "
                       f"cost based on {intake['token_amount']} token volume, billed "
                       f"monthly against actual consumption.",
            "terms": f"Standard federal terms apply. PMO fee structure: 2.5% "
                     f"pass-through (TCloud-centric rate of 5% does not apply to "
                     f"this engagement type). Net-30 payment terms.",
        }
        for section_name, content in sections.items():
            documents.append({
                "doc_id": f"DOC-{did:04d}",
                "intake_id": intake["intake_id"],
                "bureau": intake["bureau"],
                "doc_type": "vendor_quote",
                "section": section_name,
                "title": f"Vendor Quote - {intake['intake_id']} - {intake['vendor']}",
                "date": quote_date.strftime("%Y-%m-%d"),
                "superseded": False,
                "content": content,
            })
            did += 1

        # CEBD sections (only for intakes far enough along)
        if STAGES.index(intake["stage"]) >= STAGES.index("CEBD Drafted"):
            cebd_date = random_date(intake["created_offset"] + 8)
            cebd_sections = {
                "scope": f"Customer Estimate Baseline Document for {intake['bureau']} "
                         f"{intake['token_type']} token request, intake {intake['intake_id']}.",
                "cost_estimate": f"Baseline cost estimate covering {intake['token_amount']} "
                                 f"tokens at current {intake['vendor']} pricing, inclusive "
                                 f"of PMO fee.",
                "approval_chain": "Routed through Associate CIO for Cloud and Network "
                                  "Services for sign-off prior to PPM submission.",
            }
            for section_name, content in cebd_sections.items():
                documents.append({
                    "doc_id": f"DOC-{did:04d}",
                    "intake_id": intake["intake_id"],
                    "bureau": intake["bureau"],
                    "doc_type": "cebd",
                    "section": section_name,
                    "title": f"CEBD - {intake['intake_id']}",
                    "date": cebd_date.strftime("%Y-%m-%d"),
                    "superseded": False,
                    "content": content,
                })
                did += 1

        # Deliberate superseded-quote scenario on the FIRST intake only
        if i == 0:
            old_quote_date = quote_date - timedelta(days=12)
            old_doc_id = f"DOC-{did:04d}"
            documents.append({
                "doc_id": old_doc_id,
                "intake_id": intake["intake_id"],
                "bureau": intake["bureau"],
                "doc_type": "vendor_quote",
                "section": "pricing",
                "title": f"Vendor Quote - {intake['intake_id']} - {intake['vendor']} (Original)",
                "date": old_quote_date.strftime("%Y-%m-%d"),
                "superseded": True,
                "superseded_by": f"DOC-{did - 2:04d}",  # the pricing section added just above
                "content": f"[ORIGINAL - SUPERSEDED] Original unit pricing quote for "
                           f"{intake['token_amount']} {intake['token_type']} tokens, "
                           f"prior to vendor's revised rate card. This quote was "
                           f"superseded by a lower-cost revision and should not be "
                           f"used for current cost estimates.",
            })
            did += 1

    return documents


def make_policy() -> list[dict]:
    """Numbered-clause policy corpus."""
    clauses = [
        ("1.1", "Definitions",
         "For purposes of this policy, 'Token Request' refers to any Bureau-initiated "
         "request for allocation of LLM API tokens from an approved vendor (Anthropic, "
         "AWS, OpenAI, or Microsoft Azure)."),
        ("1.2", "Definitions",
         "'Intake' refers to the formal submission of a Token Request via ServiceNow "
         "or email to the TCloud PMO, triggering the stages defined in Section 3."),
        ("2.1", "Approval Authority",
         "Token Requests under 100,000 tokens may be approved by the Customer Success "
         "Manager assigned to the requesting Bureau."),
        ("2.2", "Approval Authority",
         "Token Requests of 100,000 tokens or more require sign-off from the Associate "
         "CIO for Cloud and Network Services prior to CEBD finalization."),
        ("2.3", "Approval Authority",
         "Any request exceeding 500,000 tokens requires additional review by the CIO "
         "and must be accompanied by a documented utilization forecast."),
        ("3.1", "Stage Definitions",
         "Intake Received: the initial logging of a Token Request, assignment of an "
         "intake ID, and opening of the corresponding ServiceNow ticket."),
        ("3.2", "Stage Definitions",
         "Technical Review: confirmation that the requested token type and model "
         "specification are supported under an existing contract vehicle."),
        ("3.3", "Stage Definitions",
         "Cost Estimation: preparation of a Rough Order of Magnitude (ROM) estimate "
         "based on requested token volume and current vendor pricing."),
        ("3.4", "Stage Definitions",
         "CEBD Drafted: drafting of the Customer Estimate Baseline Document, which "
         "formalizes cost estimates and routes for approval."),
        ("3.5", "Stage Definitions",
         "Approved: sign-off has been obtained from the appropriate approval authority "
         "per Section 2."),
        ("3.6", "Stage Definitions",
         "Provisioned: token allocation has been confirmed and activated with the vendor."),
        ("4.1", "Contract Vehicles",
         "AWS Bedrock token procurement must route through the existing GovCloud "
         "contract vehicle to maintain FedRAMP High compliance."),
        ("4.2", "Contract Vehicles",
         "Anthropic Claude token procurement may route through either AWS Bedrock or "
         "GCP Vertex AI, subject to Bureau preference and FedRAMP authorization status."),
        ("5.1", "PMO Fee Structure",
         "A 2.5% pass-through fee applies to standard Bureau-managed token requests."),
        ("5.2", "PMO Fee Structure",
         "A 5% TCloud-centric fee applies when the PMO assumes full management "
         "responsibility for the vendor relationship and billing reconciliation."),
        ("6.1", "Document Versioning",
         "When a vendor quote or CEBD is revised, the prior version must be marked "
         "superseded rather than deleted, preserving the full record for audit purposes."),
        ("6.2", "Document Versioning",
         "Active reasoning and dashboard reporting must exclude superseded documents "
         "by default; superseded documents remain accessible only via explicit "
         "historical query."),
    ]
    return [
        {
            "doc_id": f"POLICY-{clause_num.replace('.', '')}",
            "doc_type": "policy",
            "clause_number": clause_num,
            "section_title": title,
            "bureau": None,  # policy is bureau-agnostic
            "intake_id": None,
            "date": "2026-01-01",
            "superseded": False,
            "content": content,
        }
        for clause_num, title, content in clauses
    ]


def generate_all(n_intakes: int = 18) -> dict:
    intakes = make_intakes(n_intakes)
    emails = [] if SYNTHETIC_EMAILS_DISABLED else make_emails(intakes)
    tickets = make_tickets(intakes)
    documents = make_documents(intakes)
    policy = make_policy()

    OUT_DIR.mkdir(exist_ok=True)
    for name, payload in [
        ("intakes", intakes),
        ("emails", emails),
        ("tickets", tickets),
        ("documents", documents),
        ("policy", policy),
    ]:
        with open(OUT_DIR / f"{name}.json", "w") as f:
            json.dump(payload, f, indent=2)

    return {
        "intakes": intakes, "emails": emails, "tickets": tickets,
        "documents": documents, "policy": policy,
    }


if __name__ == "__main__":
    data = generate_all()
    print(f"Generated {len(data['intakes'])} intakes")
    print(f"Generated {len(data['emails'])} emails")
    print(f"Generated {len(data['tickets'])} tickets")
    print(f"Generated {len(data['documents'])} document chunks (incl. 1 superseded)")
    print(f"Generated {len(data['policy'])} policy clauses")
    print(f"Written to {OUT_DIR}/")
