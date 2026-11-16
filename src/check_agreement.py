"""
Quality check on REAL reviews: a second, stronger model re-tags a random
sample of reviews independently, and we measure how often the everyday
tagging model (Haiku) agrees with it.

Real reviews have no answer key, so this is "agreement with a stronger
reader", not accuracy against the truth. Where they disagree, the report's
Evidence tab lets anyone read the quote and judge.

Writes data/real/agreement.json (used by the Method tab).

Run:  python src/check_agreement.py            # 40 reviews, about $0.15
      python src/check_agreement.py --n 60
"""

import argparse
import json
import random
import sqlite3
from collections import defaultdict
from datetime import date, timedelta

import anthropic

import analyze
from config import DATA_DIR, DB_PATH, EUROPE, THEMES

REFERENCE_MODEL = "claude-opus-5-5"
PRICE_IN, PRICE_OUT = 4.0, 20.0     # USD per 1M tokens, reference model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=40)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    since = (date.today() - timedelta(weeks=26)).isoformat()
    rows = [dict(r) for r in conn.execute(
        """SELECT r.* FROM reviews r JOIN review_analysis a USING (review_id)
           WHERE r.review_date >= ? AND r.is_fictional = 0""", (since,))
            if r["country"].upper() in EUROPE]
    random.seed(7)                       # same sample every time
    sample = random.sample(rows, min(args.n, len(rows)))
    ids = {r["review_id"] for r in sample}

    everyday = defaultdict(set)
    for rid, t in conn.execute("SELECT review_id, theme FROM review_themes"):
        if rid in ids:
            everyday[rid].add(t)

    analyze.MODEL = REFERENCE_MODEL      # same prompt and theme list, stronger model
    client = anthropic.Anthropic()
    results, usage = analyze.analyse_batch(client, analyze.build_system_prompt(), sample)
    reference = {r["review_id"]: {t["theme"] for t in r["themes"]} for r in results if r["review_id"] in ids}

    groups = {g: set(ts) for g, ts in THEMES.items()}
    def score(keep):
        both = only_e = only_r = 0
        for rid in reference:
            e, r = everyday[rid] & keep, reference[rid] & keep
            both, only_e, only_r = both + len(e & r), only_e + len(e - r), only_r + len(r - e)
        return {"agreed": both, "only_everyday": only_e, "only_reference": only_r,
                "precision": round(both / (both + only_e), 3) if both + only_e else None,
                "recall": round(both / (both + only_r), 3) if both + only_r else None}

    all_themes = set().union(*groups.values())
    out = {
        "checked_on": date.today().isoformat(),
        "reviews": len(reference),
        "everyday_model": analyze.__dict__.get("EVERYDAY_MODEL", "claude-haiku-5-5"),
        "reference_model": REFERENCE_MODEL,
        "all_themes": score(all_themes),
        "by_group": {g: score(ts) for g, ts in groups.items()},
        "same_themes_exactly": round(sum(everyday[r] == reference[r] for r in reference) / len(reference), 3),
    }
    with open(DATA_DIR / "agreement.json", "w") as f:
        json.dump(out, f, indent=1)
    cost = usage.input_tokens / 1e6 * PRICE_IN + usage.output_tokens / 1e6 * PRICE_OUT
    print(json.dumps(out, indent=1))
    print(f"approx. cost ${cost:.2f}")


if __name__ == "__main__":
    main()
