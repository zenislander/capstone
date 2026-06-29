"""
Dashboard push simulation.

Implements the data flow described in the capstone doc's "How Retrieval
Influences Agent Output" section:

  "This new information triggers an API push to the dashboard monitor.
   The agent does not reconstruct Bureau token data from scratch -- it
   queries the vector store with a retrieval call scoped to the relevant
   chunks. It then formats this structured data and pushes it to the
   dashboard via API, populating the correct Bureau rows with the correct
   token types and amounts."

There's no real dashboard to push to in this prototype, so `push_to_dashboard`
is a stub that prints/logs the payload it WOULD send via API -- the function
signature and payload shape are what matters, not the transport. Swapping in
a real `requests.post(DASHBOARD_API_URL, json=payload)` later is trivial.

The key behavior being demonstrated: when a NEW intake arrives, the agent
doesn't reprocess every email/document. It queries the vector store
(scoped by intake_id, doc_type="structured_intake") for just that intake's
structured chunk, formats it, and pushes only the delta -- then separately
recomputes the full Bureau aggregation for the dashboard's summary view.
"""

from retrieval.store import retrieve


def push_to_dashboard(payload: dict) -> dict:
    """
    STUB -- simulates an API push to a dashboard monitor.
    In production this would be something like:
        requests.post(DASHBOARD_API_URL, json=payload, headers=auth_headers)
    Here we just log what would be sent and return a fake ack, so the
    surrounding logic (retrieval -> format -> push) can be fully exercised
    and tested without a real dashboard backend.
    """
    print(f"[DASHBOARD PUSH] -> {payload}")
    return {"status": "ack", "payload": payload}


def handle_new_intake_event(vector_store, intake_id: str) -> dict:
    """
    Simulates the agent's reaction to a new intake arriving, per the doc:
    retrieve the relevant structured chunk from the vector store (NOT
    re-parsing source emails/documents), format it, push the delta to the
    dashboard.
    """
    results = retrieve(
        vector_store,
        query=f"intake {intake_id} token request",
        intake_id=intake_id,
        doc_type="structured_intake",
        k=1,
    )
    if not results:
        return {"status": "error", "reason": f"No structured intake chunk found for {intake_id}"}

    chunk = results[0]
    payload = {
        "intake_id": chunk.metadata["intake_id"],
        "bureau": chunk.metadata["bureau"],
        "token_type": chunk.metadata["token_type"],
        "token_amount": chunk.metadata["token_amount"],
        "vendor": chunk.metadata["vendor"],
        "stage": chunk.metadata["stage"],
    }
    return push_to_dashboard(payload)


def refresh_bureau_summary(vector_store, bureaus: list[str]) -> dict:
    """
    Simulates the dashboard's periodic full-refresh: for each Bureau,
    retrieve all of its structured_intake chunks and sum token_amount by
    token_type. This is the AGGREGATE view -- distinct from the per-event
    delta push above, and the reason a structured table (see
    extraction/structured.py's aggregate_tokens_by_bureau) exists alongside
    the vector store rather than relying on retrieval to do summation.

    CAVEAT -- read before trusting this in production: this function is
    only correct if k >= the true number of structured_intake chunks for
    that Bureau. It happens to match the precise table in this prototype
    because k=20 exceeds every synthetic Bureau's intake count, but that's
    a property of the demo data, not a property of retrieval. Top-k
    similarity search has no way to know it has "found everything" --
    there's no completeness guarantee the way there is with a SQL
    `WHERE bureau = X` scan. At real scale (hundreds of intakes per
    Bureau), this function would silently undercount. Treat this as a
    demonstration of the data flow shape only; aggregate_tokens_by_bureau()
    in extraction/structured.py is the function that should actually back
    a dashboard.
    """
    summary = {}
    for bureau in bureaus:
        chunks = retrieve(
            vector_store,
            query=f"{bureau} token requests",
            bureau=bureau,
            doc_type="structured_intake",
            k=20,  # generous k to capture all of this bureau's intakes
        )
        totals: dict[str, int] = {}
        for c in chunks:
            tt = c.metadata["token_type"]
            totals[tt] = totals.get(tt, 0) + c.metadata["token_amount"]
        summary[bureau] = totals

    push_to_dashboard({"event": "bureau_summary_refresh", "summary": summary})
    return summary
