"""
Negative-review triage agent.

For each new 1-2 star review of the focus brand, a Claude agent:
  1. reads the review,
  2. checks the Problem Vault and whether the same problem is a pattern
     (how many recent reviews say the same, in which countries) - it decides
     itself which lookups it needs,
  3. names the likely cause, the journey stage, the owner and the urgency,
  4. drafts a public reply in the review's language.

Nothing is posted anywhere. Drafts are examples for a human to edit and send.
Results go to the review_triage table and appear in the report's
"Review triage" tab.

Run:  python src/triage_agent.py                     # up to 8 new reviews, Haiku
      python src/triage_agent.py --model claude-sonnet-5-5 --limit 8
"""

import argparse
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone

import anthropic
from anthropic import beta_tool

import report_data
from config import BRAND_NAMES, DB_PATH, PROBLEM_OWNER, STAGE_OF, THEMES

PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0)}
THEME_LABEL = {k: v for g in THEMES.values() for k, v in g.items()}
PAIN = set(THEMES["pain_point"])

SYSTEM = """You triage negative public reviews for the customer experience lead of a
direct-to-consumer walking pad brand. For the review you are given:
1. Check the Problem Vault and whether this is a pattern (use the tools; look up
   every problem the review raises).
2. Then call submit_triage exactly once.

Rules:
- Base the cause on what the review says ("the review says ..."). You do not know
  the company's internal operations: never claim facts about stock, carriers or staff.
- Urgency: high = safety issue, product broken or damaged, money owed for a long time,
  or the customer says they will escalate (bank, lawyer, consumer authority);
  medium = an open problem the company can still fix; low = venting about something
  already resolved.
- The draft reply: in the review's language, at most 90 words, warm and specific to
  what the customer wrote, apologise for the specific experience, no excuses, no
  blame. Never promise a delivery date, a refund or compensation. Invite them to
  send their order number to [support email] so the team can look at it personally.
  No customer name (you do not have it). Sign off with "[Name], Customer Care".
- Write all other fields in plain English, one sentence each."""


def load_context():
    data = report_data.build()
    focus = data["focus"]
    reviews = [r for r in report_data.load() if r["brand"] == focus and r["review_date"] >= data["date_from"]
               and r["country"].upper() in report_data.EUROPE]
    return data, focus, reviews


def make_tools(data, focus, reviews, today, sink):
    vault = [{"theme": v["theme"], "problem": THEME_LABEL[v["theme"]], "owner": v["owner"], "stage": v["stage"],
              "share_of_reviews": v["share"], "market_share": v["market_share"], "stars_lost_estimate": v["stars_lost"]}
             for v in data["vault"]]

    @beta_tool
    def problem_vault() -> str:
        """The brand's top 5 problems from the last 6 months of reviews, ranked by the stars they cost, with owner and journey stage."""
        return json.dumps(vault)

    @beta_tool
    def pattern_check(theme: str, days: int = 30) -> str:
        """How many of the brand's reviews in the last `days` days mention this theme, by country, versus the 6-month share.

        Args:
            theme: theme key, one of the keys listed in the user message.
            days: look-back window in days (default 30).
        """
        if theme not in THEME_LABEL:
            raise ValueError(f"Unknown theme '{theme}'. Use one of: {', '.join(THEME_LABEL)}")
        since = (today - timedelta(days=int(days))).isoformat()
        recent = [r for r in reviews if r["review_date"] >= since]
        hits = [r for r in recent if any(t["theme"] == theme for t in r["themes"])]
        six = sum(any(t["theme"] == theme for t in r["themes"]) for r in reviews)
        by_c = {}
        for r in hits:
            by_c[r["country"].upper()] = by_c.get(r["country"].upper(), 0) + 1
        return json.dumps({"theme": theme, "label": THEME_LABEL[theme], "window_days": days,
                           "reviews_in_window": len(recent), "mentioning_theme": len(hits),
                           "share_in_window": round(len(hits) / len(recent), 3) if recent else None,
                           "share_6_months": round(six / len(reviews), 3) if reviews else None,
                           "by_country": by_c, "owner": PROBLEM_OWNER.get(theme)})

    @beta_tool
    def submit_triage(cause: str, problems: list[str], stage: str, owner: str, urgency: str,
                      pattern: str, internal_action: str, reply_language: str, draft_reply: str) -> str:
        """Record the triage. Call exactly once, as the last step.

        Args:
            cause: one sentence, what the review says went wrong and why.
            problems: theme keys this review raises (from the list in the user message).
            stage: journey stage key: before, order, delivery, setup, use, service or after.
            owner: team that owns the fix (use the Problem Vault owner where it fits).
            urgency: high, medium or low.
            pattern: one sentence with the numbers from pattern_check: one-off or recurring.
            internal_action: one sentence, what the owner should do about the cause.
            reply_language: ISO code of the reply language, e.g. nl, de, en.
            draft_reply: the public reply draft.
        """
        sink.update(cause=cause, problems=[p for p in problems if p in THEME_LABEL], stage=stage, owner=owner,
                    urgency=urgency.lower(), pattern=pattern, internal_action=internal_action,
                    reply_language=reply_language, draft_reply=draft_reply)
        return "Saved."

    return [problem_vault, pattern_check, submit_triage]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--max-cost", type=float, default=0.30)
    parser.add_argument("--redo", action="store_true", help="triage again even if already done")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS review_triage
                    (review_id TEXT PRIMARY KEY, created_at TEXT, model TEXT, result TEXT)""")
    done = {r[0] for r in conn.execute("SELECT review_id FROM review_triage")}
    data, focus, reviews = load_context()
    today = date.today()
    todo = [r for r in sorted(reviews, key=lambda r: r["review_date"], reverse=True)
            if r["rating"] <= 2 and (args.redo or r["review_id"] not in done)][:args.limit]
    if not todo:
        print("Triage: nothing new.")
        return

    client = anthropic.Anthropic()
    p_in, p_out = PRICES.get(args.model, (4.0, 20.0))
    themes_txt = "; ".join(f"{k} = {v}" for k, v in THEME_LABEL.items() if k in PAIN or STAGE_OF.get(k))
    spent = 0.0
    for r in todo:
        if spent >= args.max_cost:
            print(f"Stopped at the cost cap (${spent:.2f}).")
            break
        sink = {}
        tagged = [t["theme"] for t in r["themes"]]
        msg = (f"Brand: {BRAND_NAMES[focus]}. Theme keys: {themes_txt}.\n\n"
               f"Review ({r['rating']} stars, {r['country'].upper()}, {r['review_date']}, language {r['language']}; "
               f"auto-tagged themes: {', '.join(tagged) or 'none'}):\n"
               f"Title: {r['title'] or ''}\n{r['text']}")
        runner = client.beta.messages.tool_runner(
            model=args.model, max_tokens=4000, system=SYSTEM,
            tools=make_tools(data, focus, reviews, today, sink),
            messages=[{"role": "user", "content": msg}],
            max_iterations=6,
        )
        for message in runner:
            spent += message.usage.input_tokens / 1e6 * p_in + message.usage.output_tokens / 1e6 * p_out
            if message.stop_reason == "refusal":
                break
        if not sink:
            print(f"  {r['review_id']}: no triage returned, skipped")
            continue
        conn.execute("INSERT OR REPLACE INTO review_triage VALUES (?, ?, ?, ?)",
                     (r["review_id"], datetime.now(timezone.utc).isoformat(timespec="seconds"), args.model,
                      json.dumps(sink, ensure_ascii=False)))
        conn.commit()
        print(f"  {r['review_date']} {r['country']} {r['rating']}★ -> {sink['urgency']}, {sink['owner']}")
    print(f"Triage done with {args.model}, approx. ${spent:.3f}")


if __name__ == "__main__":
    main()
