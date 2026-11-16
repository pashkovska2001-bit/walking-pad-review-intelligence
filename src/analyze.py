"""
Stage 2: analyse reviews with Claude.

What it does, in plain words:
1. Copies all reviews from data/reviews.csv into the local database.
2. Finds reviews that have NOT been analysed yet (so weekly runs only pay
   for new reviews).
3. Sends them to Claude in small batches. For each review Claude returns:
   - overall sentiment (positive / mixed / negative)
   - which themes from our fixed list it mentions
   - for each theme, a short quote from the review as evidence
     (original language + English translation)
4. Saves the results in data/insights.sqlite.

Run:
    python src/analyze.py              # analyse everything not yet analysed
    python src/analyze.py --limit 20   # small test run
"""

import argparse
import csv
import json
import sqlite3
import sys
from datetime import date, datetime, timezone

import anthropic

from config import DB_PATH, REVIEWS_CSV, THEMES, all_theme_keys, theme_group

# Tagging is a simple, high-volume task, so we use the small, fast model.
# Haiku 5.5 is about 40x cheaper than Opus 5.5; its accuracy is checked
# against the planted labels in the sample data (src/check_accuracy.py).
MODEL = "claude-haiku-5-5"
BATCH_SIZE = 25
PRICE_IN, PRICE_OUT = 0.10, 0.50   # USD per 1M tokens for this model

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY, brand TEXT, source TEXT, country TEXT,
    language TEXT, review_date TEXT, week TEXT, rating INTEGER,
    title TEXT, text TEXT, is_fictional INTEGER
);
CREATE TABLE IF NOT EXISTS review_analysis (
    review_id TEXT PRIMARY KEY, sentiment TEXT, model TEXT, analyzed_at TEXT
);
CREATE TABLE IF NOT EXISTS review_themes (
    review_id TEXT, theme TEXT, theme_group TEXT,
    quote_original TEXT, quote_en TEXT,
    PRIMARY KEY (review_id, theme)
);
"""


def iso_week(day_str):
    y, w, _ = date.fromisoformat(day_str).isocalendar()
    return f"{y}-W{w:02d}"


def load_reviews_into_db(conn):
    with open(REVIEWS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    conn.executemany(
        """INSERT OR REPLACE INTO reviews VALUES
           (:review_id, :brand, :source, :country, :language, :review_date,
            :week, :rating, :title, :text, :is_fictional)""",
        [{**r, "week": iso_week(r["review_date"]),
          "is_fictional": 1 if str(r.get("is_fictional")).lower() == "true" else 0}
         for r in rows],
    )
    conn.commit()
    return len(rows)


def pending_reviews(conn, limit=None):
    sql = """SELECT review_id, language, rating, title, text FROM reviews
             WHERE review_id NOT IN (SELECT review_id FROM review_analysis)
             ORDER BY review_date"""
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [dict(zip(["review_id", "language", "rating", "title", "text"], row))
            for row in conn.execute(sql)]


# ---------------------------------------------------------------------------
# Prompt and output format
# ---------------------------------------------------------------------------
def build_system_prompt():
    lines = []
    for group, themes in THEMES.items():
        lines.append(f"\n[{group}]")
        for key, desc in themes.items():
            lines.append(f"- {key}: {desc}")
    taxonomy = "\n".join(lines)
    return f"""You are a customer experience analyst. You read customer reviews of
walking pads / compact home treadmills (any language, mostly English, Dutch or German) and tag them
with themes from a FIXED list, so a CX team can count themes week by week.

Theme list (use only these keys):
{taxonomy}

Group meaning:
- purchase_driver: why the customer chose this product (stated reason to buy).
- pain_point: a problem the customer experienced after purchase.
- delight: something after purchase that made the customer happy.

Rules:
- Tag a theme only when the review clearly expresses it. Do not guess.
- A review can have zero, one or several themes.
- delivery_delay = the order arrived later than promised.
  preorder_communication = the customer complains about missing information,
  vague or repeatedly changed dates for a pre-order. Tag both when both apply.
- Reviews about a company/shop in general (not walking pads) still count:
  tag delivery, service, returns etc. as usual.
- For each theme give one short evidence quote copied word for word from the
  review (max 15 words, original language), plus an English translation
  (identical if the review is in English).
- Sentiment: "positive", "mixed" or "negative" for the review as a whole.
- Never include names or other personal data in quotes.
- Return exactly one result per review_id you were given."""


def output_schema():
    return {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "review_id": {"type": "string"},
                        "sentiment": {"type": "string", "enum": ["positive", "mixed", "negative"]},
                        "themes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "theme": {"type": "string", "enum": all_theme_keys()},
                                    "quote_original": {"type": "string"},
                                    "quote_en": {"type": "string"},
                                },
                                "required": ["theme", "quote_original", "quote_en"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["review_id", "sentiment", "themes"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["results"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# Claude call
# ---------------------------------------------------------------------------
def analyse_batch(client, system_prompt, batch):
    payload = json.dumps(
        [{"review_id": r["review_id"], "language": r["language"], "rating": r["rating"],
          "title": r["title"], "text": r["text"]} for r in batch],
        ensure_ascii=False,
    )
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        # If Claude declines a request for safety reasons, the API retries on a
        # fallback model automatically instead of failing the batch.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        # Tagging is a simple task, so we ask for low effort: cheaper and faster.
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": output_schema()},
        },
        system=system_prompt,
        messages=[{"role": "user", "content": f"Analyse these reviews:\n{payload}"}],
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"Claude stopped early: {response.stop_reason}")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["results"], response.usage


def save_results(conn, results, valid_ids):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    saved = 0
    for r in results:
        if r["review_id"] not in valid_ids:
            continue   # ignore anything Claude returned that we did not send
        conn.execute("DELETE FROM review_themes WHERE review_id = ?", (r["review_id"],))
        conn.execute("INSERT OR REPLACE INTO review_analysis VALUES (?, ?, ?, ?)",
                     (r["review_id"], r["sentiment"], MODEL, now))
        for t in r["themes"]:
            conn.execute(
                "INSERT OR REPLACE INTO review_themes VALUES (?, ?, ?, ?, ?)",
                (r["review_id"], t["theme"], theme_group(t["theme"]),
                 t["quote_original"], t["quote_en"]),
            )
        saved += 1
    conn.commit()
    return saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="analyse at most N reviews (for testing)")
    parser.add_argument("--max-cost", type=float, default=0.60,
                        help="stop when the estimated spend of this run reaches this many USD")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    total = load_reviews_into_db(conn)
    todo = pending_reviews(conn, args.limit)
    print(f"{total} reviews in file, {len(todo)} to analyse now.")
    if not todo:
        return

    client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from the environment
    system_prompt = build_system_prompt()
    tokens_in = tokens_out = done = 0

    for i in range(0, len(todo), BATCH_SIZE):
        spent = tokens_in / 1e6 * PRICE_IN + tokens_out / 1e6 * PRICE_OUT
        if spent >= args.max_cost:
            print(f"  budget cap ${args.max_cost:.2f} reached; the rest waits for the next run")
            break
        batch = todo[i:i + BATCH_SIZE]
        try:
            results, usage = analyse_batch(client, system_prompt, batch)
        except (anthropic.APIError, RuntimeError, json.JSONDecodeError) as e:
            print(f"  batch {i // BATCH_SIZE + 1}: failed ({e}); these reviews will be retried next run")
            continue
        done += save_results(conn, results, {r["review_id"] for r in batch})
        tokens_in += usage.input_tokens
        tokens_out += usage.output_tokens
        print(f"  batch {i // BATCH_SIZE + 1}: {len(results)}/{len(batch)} reviews analysed")

    cost = tokens_in / 1e6 * PRICE_IN + tokens_out / 1e6 * PRICE_OUT
    print(f"Done: {done} reviews analysed. Tokens in/out: {tokens_in}/{tokens_out}, "
          f"approx. cost ${cost:.2f}")
    if done < len(todo):
        sys.exit(1)


if __name__ == "__main__":
    main()
