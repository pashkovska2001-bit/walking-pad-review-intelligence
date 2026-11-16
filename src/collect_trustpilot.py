"""
Stage 4: collect real Trustpilot reviews through Apify.

What it does, in plain words:
1. Asks Apify (a paid data-collection service, your own account) to fetch
   recent Trustpilot reviews for each brand in config.TRUSTPILOT_DOMAINS.
2. Keeps only reviewers from Europe incl. UK, and only what the analysis needs: text, title, stars, date, language,
   country. Reviewer names, profile ids and photos are dropped right here,
   before anything is written to disk.
3. Adds new reviews to data/real/reviews.csv (reviews already there are skipped,
   so weekly runs only add what is new).

Limitation / risk (written down on purpose): Trustpilot's terms do not allow
automated collection. Apify does the collection, but that does not change the
terms. This is fine for a one-off portfolio prototype; a production version
should use Trustpilot's official API or a licensed data provider.

The Apify token is read from the APIFY_TOKEN environment variable, never from code.

Run:
    python src/collect_trustpilot.py                 # last 12 weeks, up to 300 per page
    python src/collect_trustpilot.py --weeks 2       # regular update
    python src/collect_trustpilot.py --weeks 26 --max 700 --max-charge 1.30   # 6-month backfill
"""

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import date, timedelta

from config import DATA_DIR, EUROPE, REVIEWS_CSV, TRUSTPILOT_DOMAINS

ACTOR = "automation-lab~trustpilot"      # community Apify actor, ~$0.6 per 1,000 reviews
API = "https://api.apify.com/v2"
FIELDS = ["review_id", "brand", "source", "country", "language", "review_date",
          "rating", "title", "text", "is_fictional",
          "origin", "replied", "reply_days"]   # company-side facts, no reviewer data


def apify(method, path, body=None):
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        sys.exit("APIFY_TOKEN is not set. Run: source ~/.zshrc")
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def run_actor(domains, since, max_per_company, max_charge):
    run_input = {
        "companyUrls": domains,
        "languages": ["all"],             # NL, DE, EN, ... not just English
        "sort": "recency",
        "publishedAfter": since,
        "maxReviewsPerCompany": max_per_company,
        "includeCompanyInfo": True,
    }
    # maxTotalChargeUsd is a hard spending cap: Apify stops the run when it is reached.
    run = apify("POST", f"/acts/{ACTOR}/runs?maxTotalChargeUsd={max_charge}", run_input)["data"]
    print(f"Apify run started ({run['id']}), waiting for it to finish...")
    while run["status"] in ("READY", "RUNNING"):
        time.sleep(10)
        run = apify("GET", f"/actor-runs/{run['id']}")["data"]
    if run["status"] != "SUCCEEDED":
        sys.exit(f"Apify run ended with status {run['status']}")
    cost = run.get("usageTotalUsd")
    print(f"Apify run finished" + (f" (cost ${cost:.2f})" if cost else ""))
    return apify("GET", f"/datasets/{run['defaultDatasetId']}/items?clean=true&format=json")


def reply_days(published, replied_at):
    if not replied_at:
        return ""
    try:
        return max(0, (date.fromisoformat(replied_at[:10]) - date.fromisoformat(published)).days)
    except ValueError:
        return ""


def to_row(item, brand_by_domain):
    """Keep only non-personal fields. Author name/id/image are never copied."""
    domain = (item.get("companyDomain") or "").lower().removeprefix("www.")
    brand = brand_by_domain.get(domain)
    text = (item.get("text") or "").strip()
    published = (item.get("publishedDate") or "")[:10]
    if not brand or not text or not published:
        return None
    if (item.get("country") or "").upper() not in EUROPE:
        return None     # outside Europe/UK: different market, not compared
    raw_id = item.get("reviewId") or item.get("id") or hashlib.sha1(
        f"{domain}|{published}|{text}".encode()).hexdigest()[:16]
    return {
        "review_id": f"TP-{raw_id}",
        "brand": brand,
        "source": "trustpilot",
        "country": item.get("country") or "",
        "language": item.get("language") or "",
        "review_date": published,
        "rating": item.get("rating"),
        "title": (item.get("title") or "").strip(),
        "text": text,
        "is_fictional": False,
        # Written on the reviewer's own initiative ("Organic" on Trustpilot) or
        # after a company invitation (Shopify, review link, automatic invites...).
        "origin": "" if not item.get("source") else
                  ("organic" if item["source"].lower() == "organic" else "invited"),
        # Did the company reply publicly, and after how many days.
        "replied": int(bool(item.get("replyMessage"))),
        "reply_days": reply_days(published, item.get("replyPublishedDate")),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weeks", type=int, default=12, help="how far back to collect")
    parser.add_argument("--max", type=int, default=300, help="max reviews per Trustpilot page")
    parser.add_argument("--max-charge", type=float, default=0.30,
                        help="hard Apify spending cap for this run, in USD")
    args = parser.parse_args()

    since = (date.today() - timedelta(weeks=args.weeks)).isoformat()
    brand_by_domain = {d: b for b, ds in TRUSTPILOT_DOMAINS.items() for d in ds}
    items = run_actor(list(brand_by_domain), since, args.max, args.max_charge)

    # Company-level facts (overall TrustScore) for context in the report; no personal data.
    companies = {}
    for it in items:
        d = (it.get("companyDomain") or "").lower().removeprefix("www.")
        if d in brand_by_domain and d not in companies:
            companies[d] = {"brand": brand_by_domain[d], "trust_score": it.get("companyTrustScore"),
                            "total_reviews": it.get("companyTotalReviews")}
    with open(DATA_DIR / "trustpilot_companies.json", "w") as f:
        json.dump({"collected_on": date.today().isoformat(), "companies": companies}, f, indent=1)
    # Keep the public profile's TrustScore and review count current (the star
    # distribution in that file is a dated snapshot read from the public page).
    prof_file = DATA_DIR / "trustpilot_profiles.json"
    if prof_file.exists():
        prof = json.load(open(prof_file))
        for d, c in companies.items():
            if d in prof["pages"] and c.get("trust_score"):
                prof["pages"][d]["trust_score"] = c["trust_score"]
                prof["pages"][d]["total_reviews"] = c["total_reviews"] or prof["pages"][d]["total_reviews"]
        prof["score_updated_on"] = date.today().isoformat()
        with open(prof_file, "w") as f:
            json.dump(prof, f, indent=1)

    existing = []
    if REVIEWS_CSV.exists():
        existing = list(csv.DictReader(open(REVIEWS_CSV, encoding="utf-8")))
    existing = [r for r in existing if r["country"].upper() in EUROPE]
    known = {r["review_id"] for r in existing}

    rows = [row for row in (to_row(it, brand_by_domain) for it in items) if row]
    fresh = {row["review_id"]: row for row in rows}
    for r in existing:   # replies often arrive days later: refresh those fields
        if r["review_id"] in fresh:
            for k in ("origin", "replied", "reply_days"):
                r[k] = fresh[r["review_id"]][k]
    new = [row for row in rows if row["review_id"] not in known]
    with open(REVIEWS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, restval="")
        w.writeheader()
        w.writerows(existing + new)

    print(f"{len(items)} reviews received, {len(new)} new, {len(existing) + len(new)} in {REVIEWS_CSV.name}")
    per_brand = {}
    for r in new:
        per_brand[r["brand"]] = per_brand.get(r["brand"], 0) + 1
    for b, n in sorted(per_brand.items()):
        print(f"  {b:12} +{n}")


if __name__ == "__main__":
    main()
