"""
Generates 30 emails tracing a single intake end-to-end through the real
12-stage TCSC IT Intake Process (per "The Federal Organization and Intake
Process.md"):

  BFS requests $100,000 in Anthropic Claude tokens via AWS Bedrock.
  Final CEBD total: $109,147.50
    = $100,000 base
    + 3.95% SAIC/vendor handling fee  -> $103,950.00
    + 5% TCloud PMO fee (compounding) -> $109,147.50

Roles (invented, styled after the IRS example's "Martin Douglas, POC"):
  - Tony Perry          BFS POC (customer)
  - Renata Cole         Intake Analyst (primary driver, all stages)
  - Marcus Whitfield     Program SME
  - Diane Okafor         Director (QA review, proceed/no-proceed, CEBD review)
  - Howard Liu           Intake Director (CEBD review, sends to OTFFMO)
  - Patricia Nguyen      ACIO / EA Leadership (Executive Approval)
  - Greg Sutherland       B&A (Budget & Acquisitions)
  - Felicia Adams         Intake Coordinator (funding monitoring, IAA initiation)
  - OTFFMO Funding Desk   OTFFMO (generic office address, per real org pattern)
  - Procurement Office    generic office address

Output:
  - bfs_emails.json   -- matches ingestion/loaders.py's expected email schema
                          (email_id, intake_id, bureau, doc_type, kind, date,
                          sender, subject, body)
  - bfs_emails.md     -- readable version for review
"""

import json
from pathlib import Path

INTAKE_ID = "R-04981"  # follows the doc's R-0xxyy ServiceNow Request # pattern
TICKET_ID = "SNOW-21091"
BUREAU = "BFS"

# Roles -> email addresses
TONY = "tony.perry@bfs.treasury.gov"
RENATA = "renata.cole@tcsc.treasury.gov"
MARCUS = "marcus.whitfield@tcsc.treasury.gov"
DIANE = "diane.okafor@tcsc.treasury.gov"
HOWARD = "howard.liu@tcsc.treasury.gov"
PATRICIA = "patricia.nguyen@treasury.gov"
GREG = "greg.sutherland@tcsc.treasury.gov"
FELICIA = "felicia.adams@tcsc.treasury.gov"
OTFFMO = "funding-desk@otffmo.treasury.gov"
PROCUREMENT = "awards@procurement.treasury.gov"

BASE_AMOUNT = 100000
HANDLING_FEE_RATE = 0.0395
AFTER_HANDLING = round(BASE_AMOUNT * (1 + HANDLING_FEE_RATE), 2)  # 103,950.00
PMO_FEE_RATE = 0.05
FINAL_TOTAL = round(AFTER_HANDLING * (1 + PMO_FEE_RATE), 2)  # 109,147.50

DATES = {
    1: "2026-02-02", 2: "2026-02-09", 3: "2026-02-23", 4: "2026-03-09",
    5: "2026-03-16", 6: "2026-03-18", 7: "2026-03-30", 8: "2026-04-02",
    9: "2026-04-28", 10: "2026-05-15", 11: "2026-06-01", 12: "2026-06-10",
}

emails = []


def add(eid, stage, kind, date, sender, recipients, subject, body):
    emails.append({
        "email_id": f"EMAIL-BFS-{eid:03d}",
        "intake_id": INTAKE_ID,
        "bureau": BUREAU,
        "doc_type": "email",
        "kind": kind,
        "stage": stage,
        "date": date,
        "sender": sender,
        "recipients": recipients,
        "subject": subject,
        "body": body,
    })


# ---------------------------------------------------------------------------
# STAGE 01 - Inquiry
# ---------------------------------------------------------------------------
add(1, "01-Inquiry", "intake_submission", DATES[1], TONY, [RENATA],
    f"TCloud Services Request - BFS - Anthropic Claude Tokens via Bedrock",
    f"Hi Renata,\n\nBFS is submitting a TCloud Services Request for Anthropic "
    f"Claude tokens via AWS Bedrock to support our document classification "
    f"pilot. Requested amount: ${BASE_AMOUNT:,.2f} in token spend for FY26. "
    f"POC is myself, Tony Perry. I've attached the completed 7-section "
    f"intake form.\n\nPlease let me know next steps.\n\nThanks,\nTony Perry\nBFS")

add(2, "01-Inquiry", "ticket_logged", DATES[1], RENATA, [TONY, DIANE],
    f"RE: TCloud Services Request - BFS - {INTAKE_ID} Logged",
    f"Tony,\n\nThanks for the submission. I've logged this in ServiceNow as "
    f"{TICKET_ID}, intake ID {INTAKE_ID}. Routing to Diane Okafor for the "
    f"proceed/no-proceed decision. Will follow up once we have a green "
    f"light to move into Discovery.\n\nBest,\nRenata Cole\nIntake Analyst, TCSC")

add(3, "01-Inquiry", "proceed_decision", DATES[1], DIANE, [RENATA],
    f"RE: {INTAKE_ID} - Proceed Decision",
    f"Renata,\n\nReviewed BFS's request ({INTAKE_ID}, ${BASE_AMOUNT:,.2f} "
    f"Anthropic Claude via Bedrock). This is a reasonable scope and aligns "
    f"with existing Bedrock contract vehicle usage. Approved to proceed to "
    f"Discovery.\n\nDiane")

# ---------------------------------------------------------------------------
# STAGE 02 - Discovery
# ---------------------------------------------------------------------------
add(4, "02-Discovery", "discovery_invite", DATES[2], RENATA, [TONY, MARCUS],
    f"Discovery Call - {INTAKE_ID} - BFS Anthropic Tokens",
    f"Hi Tony, Marcus,\n\nPMO has approved {INTAKE_ID} to proceed. Let's get "
    f"a discovery call on the calendar this week to go through business "
    f"requirements, expected usage patterns, and FISMA security level for "
    f"the document classification pilot.\n\nProposing Thursday 2pm ET -- "
    f"does that work?\n\nRenata")

add(5, "02-Discovery", "discovery_followup", DATES[2], TONY, [RENATA, MARCUS],
    f"RE: Discovery Call - {INTAKE_ID} - BFS Anthropic Tokens",
    f"Thursday 2pm works. For context ahead of the call: this is for an "
    f"internal document classification pilot, FISMA Moderate, no PII "
    f"processing planned in phase 1. Estimated 8-10 admin users, no "
    f"external integrations needed at this stage.\n\nTony")

add(6, "02-Discovery", "discovery_notes", DATES[2], MARCUS, [RENATA, TONY],
    f"RE: Discovery Call - {INTAKE_ID} - Notes and FYIdea",
    f"Good call today. I've drafted a short FYIdea summarizing the use "
    f"case and technical approach (Claude via Bedrock, FISMA Moderate, "
    f"Managed hosting model). Attaching now. Renata, this should be enough "
    f"to move into Estimation.\n\nMarcus")

# ---------------------------------------------------------------------------
# STAGE 03 - Estimation
# ---------------------------------------------------------------------------
add(7, "03-Estimation", "rom_kickoff", DATES[3], RENATA, [GREG, MARCUS],
    f"ROM Needed - {INTAKE_ID} - BFS Anthropic Tokens",
    f"Greg,\n\nNeed a ROM for {INTAKE_ID}: BFS, ${BASE_AMOUNT:,.2f} in "
    f"Anthropic Claude tokens via AWS Bedrock, Managed hosting model. "
    f"Marcus can help with technical specifics on the SME side. Targeting "
    f"PPM submission within 2 weeks.\n\nRenata")

add(8, "03-Estimation", "rom_clarification", DATES[3], GREG, [RENATA],
    f"RE: ROM Needed - {INTAKE_ID}",
    f"Renata,\n\nOn it. One question -- should the ROM reflect base token "
    f"cost only, or inclusive of the standard SAIC vendor handling fee? "
    f"Want to make sure the PPM package isn't underestimated.\n\nGreg")

add(9, "03-Estimation", "rom_clarification_reply", DATES[3], RENATA, [GREG],
    f"RE: ROM Needed - {INTAKE_ID}",
    f"Inclusive of the handling fee, please -- same as we did for the IRS "
    f"Anthropic/Bedrock request. That came out to about a 4% markup on "
    f"base cost. Use that as your baseline.\n\nRenata")

add(10, "03-Estimation", "rom_delivered", DATES[3], GREG, [RENATA, DIANE],
    f"ROM Complete - {INTAKE_ID}",
    f"ROM is complete. Base token cost ${BASE_AMOUNT:,.2f}, plus SAIC "
    f"handling fee ({HANDLING_FEE_RATE*100:.2f}%), bringing the estimate to "
    f"${AFTER_HANDLING:,.2f}. PMO fee structure to be applied separately "
    f"at CEBD stage per current policy. Ready for PPM packaging.\n\nGreg")

add(11, "03-Estimation", "ppm_submitted", DATES[3], RENATA, [DIANE],
    f"PPM Package Submitted - {INTAKE_ID}",
    f"Diane,\n\nPPM package for {INTAKE_ID} (BFS, Anthropic Claude via "
    f"Bedrock, ROM ${AFTER_HANDLING:,.2f}) is submitted for QA review. "
    f"Marcus's FYIdea and discovery notes are attached as supporting "
    f"docs.\n\nRenata")

# ---------------------------------------------------------------------------
# STAGE 04 - Quality Assurance
# ---------------------------------------------------------------------------
add(12, "04-QA", "qa_feedback", DATES[4], DIANE, [RENATA],
    f"RE: PPM Package - {INTAKE_ID} - Feedback",
    f"Renata,\n\nReviewed the PPM package. One note: please add a line item "
    f"breaking out the TCloud PMO fee separately from the SAIC handling "
    f"fee in the cost summary -- ACIO's office has been asking for that "
    f"level of transparency on recent packages. Otherwise looks solid.\n\nDiane")

add(13, "04-QA", "qa_feedback_incorporated", DATES[4], RENATA, [DIANE],
    f"RE: PPM Package - {INTAKE_ID} - Feedback Incorporated",
    f"Diane,\n\nUpdated the cost summary to show base cost, SAIC handling "
    f"fee, and TCloud PMO fee (5%) as separate line items. Re-attaching "
    f"the revised package and adding to the next PPM agenda.\n\nRenata")

add(14, "04-QA", "ppm_agenda_confirmed", DATES[4], DIANE, [RENATA, PATRICIA],
    f"RE: PPM Package - {INTAKE_ID} - On Agenda",
    f"Confirmed, {INTAKE_ID} is on next week's PPM agenda for Executive "
    f"Approval. Patricia, flagging this one for your review ahead of the "
    f"meeting -- straightforward Bedrock token request, similar profile "
    f"to the IRS package from last quarter.\n\nDiane")

# ---------------------------------------------------------------------------
# STAGE 05 - Executive Approval
# ---------------------------------------------------------------------------
add(15, "05-ExecApproval", "exec_presentation", DATES[5], MARCUS, [PATRICIA],
    f"PPM Presentation - {INTAKE_ID} - BFS Anthropic Tokens",
    f"Patricia,\n\nPresenting {INTAKE_ID} at today's PPM session. Quick "
    f"summary: BFS, document classification pilot, Anthropic Claude via "
    f"AWS Bedrock, base cost ${BASE_AMOUNT:,.2f}, total estimate with fees "
    f"${AFTER_HANDLING:,.2f} pre-PMO-fee. Happy to answer questions "
    f"beforehand if useful.\n\nMarcus")

add(16, "05-ExecApproval", "exec_approval_granted", DATES[5], PATRICIA, [RENATA, DIANE, MARCUS],
    f"RE: PPM Presentation - {INTAKE_ID} - Approved",
    f"Approved. {INTAKE_ID} is cleared for Customer Estimate Review. Good "
    f"work getting the fee breakdown cleaned up ahead of this one, "
    f"Diane.\n\nPatricia Nguyen\nACIO")

# ---------------------------------------------------------------------------
# STAGE 06 - Customer Estimate Review
# ---------------------------------------------------------------------------
add(17, "06-CustEstimateReview", "review_scheduling", DATES[6], RENATA, [TONY, MARCUS],
    f"Cost Review Scheduling - {INTAKE_ID}",
    f"Tony,\n\nGood news -- Executive Approval came through this morning "
    f"for {INTAKE_ID}. Per process, we need to schedule a cost element "
    f"review within 5 business days. Are you available Thursday or Friday "
    f"this week?\n\nRenata")

add(18, "06-CustEstimateReview", "review_confirmed", DATES[6], TONY, [RENATA, MARCUS],
    f"RE: Cost Review Scheduling - {INTAKE_ID}",
    f"Friday works for me. Quick question ahead of the call -- can you "
    f"walk me through how the final number breaks down? Want to make sure "
    f"finance isn't surprised by anything.\n\nTony")

add(19, "06-CustEstimateReview", "cost_breakdown_explained", DATES[6], RENATA, [TONY],
    f"RE: Cost Review Scheduling - {INTAKE_ID} - Cost Breakdown",
    f"Of course. Breakdown is: base token cost ${BASE_AMOUNT:,.2f}, plus "
    f"SAIC vendor handling fee ({HANDLING_FEE_RATE*100:.2f}%) bringing it "
    f"to ${AFTER_HANDLING:,.2f}, plus the standard 5% TCloud PMO fee on "
    f"top, for a final total of ${FINAL_TOTAL:,.2f}. We'll walk through "
    f"this in detail Friday and you'll have a chance to ask questions "
    f"before the CEBD is drafted.\n\nRenata")

add(20, "06-CustEstimateReview", "verbal_concurrence", DATES[6], TONY, [RENATA, MARCUS],
    f"RE: Cost Review Scheduling - {INTAKE_ID} - Concurrence",
    f"Thanks for walking through that Friday. BFS is good with "
    f"${FINAL_TOTAL:,.2f} as the final number -- you can move forward with "
    f"the CEBD.\n\nTony")

# ---------------------------------------------------------------------------
# STAGE 07 - Customer Estimate Approval
# ---------------------------------------------------------------------------
add(21, "07-CustEstimateApproval", "cebd_drafted", DATES[7], RENATA, [MARCUS, HOWARD],
    f"CEBD Drafted - {INTAKE_ID} - Ready for Review",
    f"Howard, Marcus,\n\nCEBD for {INTAKE_ID} is drafted: final amount "
    f"${FINAL_TOTAL:,.2f}, Anthropic Claude tokens via AWS Bedrock, Managed "
    f"hosting model, FY26. Requesting Program SME + Intake Director review "
    f"before this goes out to Tony for signature.\n\nRenata")

add(22, "07-CustEstimateApproval", "cebd_review_complete", DATES[7], HOWARD, [RENATA],
    f"RE: CEBD Drafted - {INTAKE_ID} - Reviewed",
    f"Reviewed and looks good -- cost agreement section, terms of service, "
    f"and the 75%-consumption notification clause are all standard. "
    f"Cleared to send to Tony for signature.\n\nHoward Liu\nIntake Director")

add(23, "07-CustEstimateApproval", "cebd_sent_to_customer", DATES[7], RENATA, [TONY],
    f"CEBD for Signature - {INTAKE_ID} - BFS Anthropic Tokens",
    f"Tony,\n\nCEBD is attached for {INTAKE_ID}, final amount "
    f"${FINAL_TOTAL:,.2f}. A few things to note before signing: this is a "
    f"non-refundable up-front commitment, cancellation requires 1 year "
    f"written notice, and renewal is automatic unless you notify us "
    f"otherwise. You'll also want to notify us once consumption hits 75% "
    f"of the pre-funded amount so we can add funds before you run out. Let "
    f"me know if you have questions before signing.\n\nRenata")

add(24, "07-CustEstimateApproval", "cebd_signed", DATES[7], TONY, [RENATA],
    f"RE: CEBD for Signature - {INTAKE_ID} - Signed",
    f"Signed and attached. Noted on the 75% threshold and the cancellation "
    f"terms. Looking forward to getting this moving.\n\nTony")

# ---------------------------------------------------------------------------
# STAGE 08 - Funding Preparation
# ---------------------------------------------------------------------------
add(25, "08-FundingPrep", "iaa_mod_summary", DATES[8], RENATA, [FELICIA],
    f"IAA Mod Summary - {INTAKE_ID} - Ready for Submission",
    f"Felicia,\n\nSigned CEBD received for {INTAKE_ID} (BFS, "
    f"${FINAL_TOTAL:,.2f}). IAA Mod summary is attached with the signed "
    f"CEBD. Please initiate IAA funding actions on the last day of this "
    f"month per the usual cadence.\n\nRenata")

add(26, "08-FundingPrep", "cebd_to_otffmo", DATES[8], HOWARD, [OTFFMO],
    f"Signed CEBD - {INTAKE_ID} - BFS",
    f"Forwarding the signed CEBD for {INTAKE_ID} (BFS, "
    f"${FINAL_TOTAL:,.2f}, Anthropic Claude via AWS Bedrock) for your "
    f"records ahead of the IAA Mod package.\n\nHoward Liu\nIntake Director")

# ---------------------------------------------------------------------------
# STAGE 09 - Funding Receipt
# ---------------------------------------------------------------------------
add(27, "09-FundingReceipt", "iaa_package_sent", DATES[9], OTFFMO, [TONY, FELICIA],
    f"IAA Mod Package - {INTAKE_ID} - BFS Finance Action Required",
    f"This is to notify BFS finance that an IAA Mod package for "
    f"{INTAKE_ID} (${FINAL_TOTAL:,.2f}, Anthropic Claude via AWS Bedrock) "
    f"has been submitted for approval. Please coordinate with your finance "
    f"POC to complete the approval on your end.\n\nOTFFMO Funding Desk")

add(28, "09-FundingReceipt", "funding_confirmed", DATES[9], FELICIA, [RENATA, HOWARD],
    f"RE: IAA Mod Package - {INTAKE_ID} - Funding Confirmed",
    f"Funding confirmed received for {INTAKE_ID}. BFS finance approved "
    f"the IAA Mod package this morning. Clearing this for Contracting.\n\n"
    f"Felicia Adams\nIntake Coordinator")

# ---------------------------------------------------------------------------
# STAGE 10 - Contracting
# ---------------------------------------------------------------------------
add(29, "10-Contracting", "contract_awarded", DATES[10], PROCUREMENT, [RENATA, GREG],
    f"Contract Awarded - {INTAKE_ID} - BFS Anthropic Tokens",
    f"Procurement Office confirms the acquisition package for {INTAKE_ID} "
    f"has been awarded. Ownership transfers to the BFS program team "
    f"effective today. B&A to coordinate any remaining security/onboarding "
    f"items.\n\nProcurement Office")

# ---------------------------------------------------------------------------
# STAGE 11 - Execution
# ---------------------------------------------------------------------------
add(30, "11-Execution", "airs_marked_complete", DATES[11], RENATA, [TONY, DIANE],
    f"AIRS Updated - {INTAKE_ID} - Marked Complete",
    f"Tony,\n\nContract is awarded and AIRS has been updated to "
    f"'Complete' for {INTAKE_ID}. Your Anthropic Claude tokens via Bedrock "
    f"should be provisioned and ready for use. Let us know if BFS has any "
    f"issues getting started, and remember to flag us once you hit 75% "
    f"consumption on the pre-funded amount.\n\nRenata")


OUT_DIR = Path(__file__).parent
with open(OUT_DIR / "bfs_emails.json", "w") as f:
    json.dump(emails, f, indent=2)

# Readable Markdown version
md_lines = [
    "# BFS Claude-via-Bedrock Intake — Email Trace",
    "",
    f"**Intake ID:** {INTAKE_ID}  |  **ServiceNow Ticket:** {TICKET_ID}  |  **Bureau:** {BUREAU}",
    "",
    f"**Final CEBD Total:** ${FINAL_TOTAL:,.2f}",
    f"  = ${BASE_AMOUNT:,.2f} base",
    f"  + {HANDLING_FEE_RATE*100:.2f}% SAIC/vendor handling fee → ${AFTER_HANDLING:,.2f}",
    f"  + 5% TCloud PMO fee (compounding) → ${FINAL_TOTAL:,.2f}",
    "",
    "---",
    "",
]
for e in emails:
    md_lines.append(f"### {e['email_id']} — {e['stage']}")
    md_lines.append(f"**Date:** {e['date']}  |  **Kind:** {e['kind']}")
    md_lines.append(f"**From:** {e['sender']}")
    md_lines.append(f"**To:** {', '.join(e['recipients'])}")
    md_lines.append(f"**Subject:** {e['subject']}")
    md_lines.append("")
    md_lines.append(e["body"].replace("\n", "  \n"))
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

with open(OUT_DIR / "bfs_emails.md", "w") as f:
    f.write("\n".join(md_lines))

print(f"Generated {len(emails)} emails")
print(f"Final CEBD total: ${FINAL_TOTAL:,.2f}")
print(f"Written to {OUT_DIR}/bfs_emails.json and bfs_emails.md")
