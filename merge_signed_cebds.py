"""
Merges signed CEBD entries into data/documents.json after data_generator.py runs.

Must run AFTER data_generator.py and BEFORE the vector store is built.
main.py's `build` command calls these in the correct order automatically.

Idempotent: safe to run multiple times -- entries are matched by intake_id
and doc_type="signed CEBD" so they won't be double-appended.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

SIGNED_CEBDS = [
    {
        "intake_id": "R-01234",
        "bureau": "IRS",
        "doc_type": "signed CEBD",
        "section": "signed",
        "title": "Signed CEBD - R-01234",
        "date": "2026-02-14",
        "superseded": False,
        "content": "Signed CEBD is active until 9/30/2026 or until the purchased token allocation is fully consumed, whichever occurs firstuntil contract is fully consumed.",
        "contract_value_usd": 100000,
    },
    {
        "intake_id": "R-04321",
        "bureau": "BFS",
        "doc_type": "signed CEBD",
        "section": "signed",
        "title": "Signed CEBD - R-04321",
        "date": "2026-03-28",
        "superseded": False,
        "content": "Signed CEBD is active until 9/30/2026 or until the purchased token allocation is fully consumed, whichever occurs firstuntil contract is fully consumed.",
        "contract_value_usd": 50000,
    },
    {
        "intake_id": "R-07765",
        "bureau": "BEP",
        "doc_type": "signed CEBD",
        "section": "signed",
        "title": "Signed CEBD - R-07765",
        "date": "2026-04-11",
        "superseded": False,
        "content": "Signed CEBD is active until 9/30/2026 or until the purchased token allocation is fully consumed, whichever occurs firstuntil contract is fully consumed.",
        "contract_value_usd": 50000,
    },
    {
        "intake_id": "R-09988",
        "bureau": "OCC",
        "doc_type": "signed CEBD",
        "section": "signed",
        "title": "Signed CEBD - R-09988",
        "date": "2026-01-22",
        "superseded": False,
        "content": "Signed CEBD is active until 9/30/2026 or until the purchased token allocation is fully consumed, whichever occurs firstuntil contract is fully consumed.",
        "contract_value_usd": 50000,
    },
]


def merge_signed_cebds() -> None:
    docs_path = DATA_DIR / "documents.json"
    existing_docs = json.load(open(docs_path))

    # Idempotency check: match on intake_id + doc_type
    existing_keys = {
        (d["intake_id"], d["doc_type"]) for d in existing_docs
    }

    # Assign doc_ids starting after the current max
    existing_ids = [
        int(d["doc_id"].replace("DOC-", ""))
        for d in existing_docs
        if d.get("doc_id", "").startswith("DOC-")
    ]
    next_id = max(existing_ids) + 1 if existing_ids else 1

    new_docs = []
    for entry in SIGNED_CEBDS:
        key = (entry["intake_id"], entry["doc_type"])
        if key in existing_keys:
            continue
        doc = {"doc_id": f"DOC-{next_id:04d}", **entry}
        new_docs.append(doc)
        next_id += 1

    if not new_docs:
        print("Signed CEBDs already merged -- skipping.")
        return

    merged = existing_docs + new_docs
    with open(docs_path, "w") as f:
        json.dump(merged, f, indent=2)

    print(f"Merged {len(new_docs)} signed CEBD(s): "
          + ", ".join(f"{d['intake_id']} ({d['bureau']})" for d in new_docs))


if __name__ == "__main__":
    merge_signed_cebds()
