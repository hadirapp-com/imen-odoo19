#!/usr/bin/env python3
"""Import old assessment-collector submissions into the imen_assessment module.

Stdlib only; talks to Odoo through the JSON-2 API (/json/2/...), so it can run
from any machine that reaches the Odoo URL.

1. Export the collector table to JSON (run where DATABASE_URL is reachable):

    psql "$DATABASE_URL" -Atc "
      select coalesce(json_agg(t), '[]') from (
        select id, assessment, name, contact, area, profession, org,
               primary_dna, secondary_dna, fit_score, scores, answers, user_agent,
               to_char(submitted_at at time zone 'UTC', 'YYYY-MM-DD HH24:MI:SS') as submitted_at
        from imp_assessment_submissions order by submitted_at
      ) t" > collector-export.json

2. Import (API key: Odoo > My Profile > Account Security > New API Key, for a
   user in Settings/Administration group):

    ODOO_API_KEY=... python3 import_collector.py collector-export.json \\
        --url https://erp.imen.co.id --db <database> [--dry-run]

Re-running is safe: rows whose collector UUID is already stored in
imen.assessment.submission.legacy_id are skipped.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

MODEL = "imen.assessment.submission"


class Odoo:
    def __init__(self, url, db, api_key):
        self.url = url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"bearer {api_key}",
        }
        if db:
            self.headers["X-Odoo-Database"] = db

    def call(self, model, method, **kwargs):
        req = urllib.request.Request(
            f"{self.url}/json/2/{model}/{method}",
            data=json.dumps(kwargs).encode(),
            headers=self.headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                body = json.loads(body).get("message", body)
            except ValueError:
                pass
            sys.exit(f"Odoo {model}.{method} failed ({e.code}): {body}")


def to_vals(row):
    answers = row.get("answers") or []
    scores = row.get("scores") or {}
    return {
        "legacy_id": row["id"],
        "assessment": row.get("assessment") or "imp",
        "name": row["name"],
        "contact": row.get("contact") or False,
        "area": row.get("area") or False,
        "profession": row.get("profession") or False,
        "org": row.get("org") or False,
        "primary_dna": row["primary_dna"],
        "secondary_dna": row["secondary_dna"],
        "fit_score": row.get("fit_score") or 0,
        "scores": scores,
        "user_agent": (row.get("user_agent") or "")[:500] or False,
        "submitted_at": row["submitted_at"],
        "answer_ids": [
            [0, 0, {
                "sequence": i,
                "question_id": a["questionId"],
                "dna": a["dna"],
                "choice_index": a.get("choiceIndex", 0),
                "choice_text": a["choiceText"],
                "score": a.get("score", 0),
            }]
            for i, a in enumerate(answers, start=1)
        ],
        "score_ids": [[0, 0, {"dna": dna, "percent": pct}] for dna, pct in scores.items()],
    }


def chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("export", help="JSON file from step 1 ('-' for stdin)")
    parser.add_argument("--url", default=os.environ.get("ODOO_URL"), help="Odoo base URL (or ODOO_URL)")
    parser.add_argument("--db", default=os.environ.get("ODOO_DB"), help="Odoo database (or ODOO_DB)")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true", help="only report what would be imported")
    args = parser.parse_args()

    api_key = os.environ.get("ODOO_API_KEY")
    if not args.url or not api_key:
        parser.error("--url (or ODOO_URL) and the ODOO_API_KEY env var are required")

    with (sys.stdin if args.export == "-" else open(args.export, encoding="utf-8")) as f:
        rows = json.load(f)
    print(f"{len(rows)} submissions in export")

    odoo = Odoo(args.url, args.db, api_key)

    existing = set()
    for batch in chunks([r["id"] for r in rows], 500):
        found = odoo.call(MODEL, "search_read", domain=[["legacy_id", "in", batch]], fields=["legacy_id"])
        existing.update(r["legacy_id"] for r in found)

    todo = [r for r in rows if r["id"] not in existing]
    print(f"{len(existing)} already imported, {len(todo)} to import")
    if args.dry_run or not todo:
        return

    done = 0
    for batch in chunks(todo, args.batch_size):
        odoo.call(MODEL, "create", vals_list=[to_vals(r) for r in batch])
        done += len(batch)
        print(f"  imported {done}/{len(todo)}")
    print("done")


if __name__ == "__main__":
    main()
