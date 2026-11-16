"""
Asks Claude to turn the counted numbers into an insight briefing:
the market (category) first, then the customer journey, each brand, the
focus brand's Problem Vault top 5, and prioritised CX recommendations.

Claude only sees aggregated numbers and short quotes, never full reviews,
and is told not to invent numbers. The result is saved in the database, so
re-building the report for the same data does not cost anything extra.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

import anthropic

from config import BRAND_NAMES, DB_PATH, JOURNEY, THEMES

MODEL = "claude-opus-5-5"
THEME_NAME = {k: v for g in THEMES.values() for k, v in g.items()}


def public_profile(data, b):
    p = data["profiles"].get(b)
    if not p:
        return None
    m = p["main"]
    return {"page": m["domain"], "trustscore_customers_see": m["trust_score"], "label": m["label"],
            "total_reviews_all_time": m["total_reviews"], "star_distribution_pct_all_time": m["stars_pct"],
            "other_country_pages": {x["domain"]: {"trustscore": x["trust_score"], "reviews": x["total_reviews"]}
                                    for x in p["pages"] if x is not m}}


def compact_payload(data):
    """The numbers Claude gets: small, readable, no personal data.
    Theme keys are replaced by plain-English names so they flow into the text."""
    name = lambda t: THEME_NAME[t]
    cat = data["category"]
    focus = data["focus"]
    stage_name = {s["key"]: s["name"] for s in JOURNEY}

    brands = {}
    for b, s in data["overall"].items():
        sig = cat["signatures"][b]
        r = data["recent"][b]
        brands[BRAND_NAMES[b]] = {
            "last_6_months_europe": {"reviews": s["n"], "avg_rating": s["avg_rating"],
                                     "share_mentioning_a_problem": s["problem_share"]},
            "last_12_weeks_europe": {"reviews": r["n"], "avg_rating": r["avg_rating"],
                                     "share_mentioning_a_problem": r["problem_share"]},
            "public_trustpilot_profile": public_profile(data, b),
            "review_programme_and_replies": data["programme"].get(b),
            "theme_share_of_reviews": {name(t): v for t, v in
                                       sorted(s["theme_shares"].items(), key=lambda kv: -kv[1]) if v >= 0.03},
            "over_indexes_on_positive": [f'{name(x["theme"])} (+{x["gap"] * 100:.0f} pts vs other brands)'
                                         for x in sig["loved_for"]],
            "over_indexes_on_problems": [f'{name(x["theme"])} (+{x["gap"] * 100:.0f} pts vs other brands)'
                                         for x in sig["criticised_for"]],
        }
        if b == "sportstech":
            brands[BRAND_NAMES[b]]["note"] = ("broad home-fitness shop (bikes, rowers, walking pads); its Trustpilot "
                                              "page covers all products. Mostly German reviewers.")

    category_themes = [
        {"theme": name(t), "group": r["group"], "category_share": r["category_share"],
         "mentions": r["mentions"], "rating_impact_stars": r["impact"], "quadrant": r["quadrant"]}
        for t, r in sorted(cat["themes"].items(), key=lambda kv: -kv[1]["category_share"])
        if r["mentions"] >= 3]

    journey = [{
        "stage": st["name"],
        "themes": [{"theme": name(t["theme"]), "type": "problem" if t["group"] == "pain_point" else "positive",
                    "focus_share": t["focus_share"], "market_share": t["market_share"]} for t in st["themes"]],
        "focus_problem_share": st["brands"][focus]["problem_share"],
        "focus_positive_share": st["brands"][focus]["delight_share"],
        "market_problem_share": st["market"]["problem_share"],
        "market_positive_share": st["market"]["delight_share"],
        "stars_a_problem_here_costs": st["impact"],
        "focus_rating_with_problem_here": st["brands"][focus]["rating_with_problem"],
    } for st in data["journey"]]

    vault = [{
        "rank": i + 1, "problem": name(v["theme"]), "stage": stage_name[v["stage"]], "suggested_owner": v["owner"],
        "reviews": v["count"], "share_of_focus_reviews": v["share"], "market_share": v["market_share"],
        "stars_lost_from_average": v["stars_lost"], "rating_with": v["rating_with"], "rating_without": v["rating_without"],
        "share_of_1_2_star_reviews": v["in_low_star"],
        "share_first_3_months": v["share_first_half"], "share_last_3_months": v["share_second_half"],
        "often_together_with": [f'{name(c["theme"])} ({c["share"] * 100:.0f}%)' for c in v["co_occurs"]],
        "example_quote": (data["evidence"][focus].get(v["theme"]) or {}).get("quote_en"),
    } for i, v in enumerate(data["vault"])]

    br = cat["bridge"]
    return {
        "data_is_fictional": data["is_fictional"],
        "period": f'{data["date_from"]} to {data["date_to"]} (6 months), reviewers in Europe incl. UK',
        "sources": data["sources"],
        "focus_brand": BRAND_NAMES[focus],
        "brands_left_out_too_few_reviews": {BRAND_NAMES[b]: n for b, n in data["small_brands"].items()},
        "definitions": {
            "trustscore_customers_see": "the official Trustpilot score on the brand's page; this is the headline "
                                        "rating customers see. Trustpilot weights recent reviews more",
            "last_12_weeks_europe": "plain average of recent reviews; a leading indicator of where the public "
                                    "score is heading, not the public score",
            "category_share": "share of reviews mentioning the theme, averaged over brands (each brand counts equally)",
            "rating_impact_stars": "average star difference between reviews that mention the theme and those that "
                                   "don't, compared within the same brand",
            "stars_lost_from_average": "share of reviews with the problem x star gap; how much the problem pulls "
                                       "the focus brand's 6-month average down",
            "invited_vs_organic": "invited = review written after a company invitation (e.g. Shopify, review "
                                  "link); organic = written on the customer's own initiative",
            "suggested_owner": "a role in a typical small DTC team, not a person",
        },
        "category": {"brands": len(data["overall"]), "reviews": cat["total_reviews"],
                     "avg_rating": cat["avg_rating"], "themes": category_themes},
        "brands": brands,
        "customer_journey": journey,
        "problem_vault_top5_focus_brand": vault,
        "focus_brand_by_country": [
            {**{k: v for k, v in m.items() if k not in ("stages", "top_problems")},
             "top_problems": [f'{name(t["theme"])} {t["share"] * 100:.0f}%' for t in m["top_problems"]]}
            for m in data["markets"]],
        "focus_rating_potential": {
            "avg_rating_6_months": br["start"],
            "estimated_avg_if_problem_share_matched_competitors": br["potential"],
            "share_of_focus_reviews_with_a_problem": br.get("focus_problem_share"),
            "share_of_competitor_reviews_with_a_problem": br.get("comp_problem_share"),
            "focus_rating_when_review_mentions_a_problem": br.get("focus_rating_with_problem"),
            "focus_rating_when_review_mentions_no_problem": br.get("focus_rating_without_problem"),
            "note": "rough estimate, not a forecast",
        },
        "monthly_focus_brand": [
            {"month": ml, "reviews": data["monthly"][focus][m]["n"], "avg_rating": data["monthly"][focus][m]["avg_rating"],
             "share_mentioning_a_problem": data["monthly"][focus][m]["problem_share"]}
            for m, ml in zip(data["months"], data["month_labels"])],
        "monthly_competitor_avg_rating": dict(zip(data["month_labels"], data["comp_monthly_rating"])),
        "example_quotes": {BRAND_NAMES[b]: {name(t): e["quote_en"] for t, e in ev.items()}
                           for b, ev in data["evidence"].items()},
    }


SYSTEM = """You are a senior customer experience and market insights analyst.
Your reader is the CEO and the CX lead of a direct-to-consumer walking pad
brand (markets NL, DE, BE, AT; UK next). The CX lead owns everything after the
order button: delivery, the first weeks at home, customer service, reviews,
returns. You get 6 months of aggregated public review statistics for the
category (several brands) and for the focus brand.

Write a briefing that follows good insight practice:
- Lead with the "so what". Each insight = what is happening, why it matters,
  what to do. Pyramid style: conclusion first, evidence after.
- Think in causes, not symptoms: a problem is solved when its cause is gone,
  not when the ticket is closed. Where you name a likely cause, base it on what
  the reviews say and word it as what reviews suggest, not as fact.
- You do not know the brand's internal operations (stock, carriers, staffing,
  ticket volumes). Never predict operational events or claim facts about them.
- Do not advise on market entry or launch timing (for example the UK): a new
  market has its own supply chain, which reviews of current markets cannot show.
- Where it fits the data, think in post-purchase touchpoints: what the customer
  hears at order, during the wait, at dispatch, after delivery, and when the
  review invitation is sent.
- Organise by the customer journey after the order: what goes wrong or right
  at each stage, for walking pad buyers in general and for the focus brand.
- The headline rating of a brand is its public TrustScore. Call the plain
  averages "6-month average" or "12-week average", never "the rating". Do not
  comment on changes in the TrustScore itself.
- Use reply data and invited/organic data where it matters, e.g. do not
  recommend replying more if a brand already replies to almost all reviews.
- Use rating impact, not only frequency, to say what matters most.
- Use only numbers that appear in the data, rounded sensibly ("53%", "2.6 stars").
  Never invent figures. Call estimates estimates. Say "signal" where samples are small.
- Concrete and specific to this data; no generic CX advice. Plain, confident
  English. Keep each field to one or two short sentences."""


def output_schema():
    s = {"type": "string"}
    lvl = {"type": "string", "enum": ["high", "medium", "low"]}
    finding = {"type": "object", "properties": {"title": s, "detail": s},
               "required": ["title", "detail"], "additionalProperties": False}
    return {
        "type": "object",
        "properties": {
            "headline": s,
            "executive_insights": {"type": "array", "items": {
                "type": "object",
                "properties": {"title": s, "evidence": s, "so_what": s, "action": s},
                "required": ["title", "evidence", "so_what", "action"], "additionalProperties": False}},
            "market": {"type": "object", "properties": {
                "summary": s,
                "findings": {"type": "array", "items": finding},
                "table_stakes": {"type": "array", "items": s},
                "differentiators": {"type": "array", "items": s}},
                "required": ["summary", "findings", "table_stakes", "differentiators"],
                "additionalProperties": False},
            "brand_profiles": {"type": "array", "items": {
                "type": "object",
                "properties": {"brand": s, "positioning": s, "loved_for": s, "criticised_for": s,
                               "lesson_for_focus_brand": s},
                "required": ["brand", "positioning", "loved_for", "criticised_for", "lesson_for_focus_brand"],
                "additionalProperties": False}},
            "focus_brand": {"type": "object", "properties": {
                "summary": s,
                "findings": {"type": "array", "items": finding},
                "strengths_vs_market": {"type": "array", "items": s},
                "weaknesses_vs_market": {"type": "array", "items": s}},
                "required": ["summary", "findings", "strengths_vs_market", "weaknesses_vs_market"],
                "additionalProperties": False},
            "journey": {"type": "array", "items": {
                "type": "object",
                "properties": {"stage": s, "market": s, "focus_brand": s, "so_what": s},
                "required": ["stage", "market", "focus_brand", "so_what"], "additionalProperties": False}},
            "vault": {"type": "array", "items": {
                "type": "object",
                "properties": {"problem": s, "what_reviews_suggest_is_the_cause": s, "fix_the_cause": s, "kpi": s},
                "required": ["problem", "what_reviews_suggest_is_the_cause", "fix_the_cause", "kpi"],
                "additionalProperties": False}},
            "markets": {"type": "object", "properties": {"summary": s, "findings": {"type": "array", "items": finding}},
                        "required": ["summary", "findings"], "additionalProperties": False},
            "review_programme": {"type": "object", "properties": {"finding": s, "so_what": s},
                                 "required": ["finding", "so_what"], "additionalProperties": False},
            "recommendations": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "action": s, "why": s, "owner": s, "kpi": s, "impact": lvl, "effort": lvl,
                    "horizon": {"type": "string", "enum": ["0-30 days", "30-90 days", "90+ days"]},
                },
                "required": ["action", "why", "owner", "kpi", "impact", "effort", "horizon"],
                "additionalProperties": False}},
            "watch_next": {"type": "array", "items": s},
        },
        "required": ["headline", "executive_insights", "market", "brand_profiles", "focus_brand",
                     "journey", "vault", "markets", "review_programme", "recommendations", "watch_next"],
        "additionalProperties": False,
    }


INSTRUCTIONS = """Return:
- headline: one sentence a CEO remembers.
- executive_insights: exactly 3, most important first.
- market: 3-4 findings about the category as a whole, plus table stakes and differentiators.
- brand_profiles: one per brand in the data (including the focus brand).
- focus_brand: 3-5 findings, plus strengths and weaknesses vs the market.
- journey: one entry per stage in customer_journey, same order and stage names:
  what happens for buyers in general, how the focus brand compares, so what.
- vault: one entry per problem in problem_vault_top5_focus_brand, same order and
  problem names: the likely cause as the reviews suggest it, how to remove the
  cause (not just handle the contact), and the KPI that shows it is gone.
- markets: how the focus brand's countries compare (flag small samples).
- review_programme: what invited vs organic reviews and reply data show.
- recommendations: 4-6, ordered by priority.
- watch_next: 2-4 signals to check in the coming weeks."""


def get_insights(data, force=False, max_age_days=7):
    """Returns the insight texts. To keep the API bill small, Claude rewrites them
    at most once every `max_age_days` days (numbers and charts still update on
    every run); `force=True` always asks for new texts."""
    payload = compact_payload(data)
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    key = hashlib.sha256((MODEL + SYSTEM + INSTRUCTIONS + json.dumps(output_schema(), sort_keys=True)
                          + payload_json).encode()).hexdigest()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS insight_summaries
                    (data_hash TEXT PRIMARY KEY, week TEXT, created_at TEXT, model TEXT, summary TEXT)""")
    if not force:
        row = conn.execute("SELECT summary, created_at FROM insight_summaries WHERE data_hash = ?", (key,)).fetchone()
        if row:
            print("Insight summary: reused (data unchanged, no API cost).")
            return {**json.loads(row[0]), "_written_on": row[1][:10]}
        # Newest texts with the current structure, if recent enough.
        for summary_json, created in conn.execute(
                "SELECT summary, created_at FROM insight_summaries ORDER BY created_at DESC LIMIT 5"):
            old = json.loads(summary_json)
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(created)).days
            if set(output_schema()["required"]) <= set(old) and age < max_age_days:
                print(f"Insight summary: reused texts from {created[:10]} (refreshed weekly to save cost).")
                return {**old, "_written_on": created[:10]}

    client = anthropic.Anthropic()
    full = output_schema()
    # The full answer format is too big for one structured request, so Claude
    # answers in two parts: the briefing first, then journey/vault/markets
    # (which also sees part one, so the two parts tell the same story).
    parts = [["headline", "executive_insights", "market", "brand_profiles", "focus_brand",
              "recommendations", "watch_next"],
             ["journey", "vault", "markets", "review_programme"]]
    summary, cost = {}, 0.0
    for keys in parts:
        schema = {**full, "properties": {k: full["properties"][k] for k in keys}, "required": keys}
        context = (f"\n\nYour briefing so far (stay consistent with it):\n{json.dumps(summary, ensure_ascii=False)}"
                   if summary else "")
        # Streaming avoids request timeouts on a long answer; we only need the final message.
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=32000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": schema}},
            system=SYSTEM,
            messages=[{"role": "user", "content":
                       f"{INSTRUCTIONS}\n\nIn this answer return only: {', '.join(keys)}.{context}"
                       f"\n\nReview statistics:\n{payload_json}"}],
        ) as stream:
            response = stream.get_final_message()
        if response.stop_reason in ("refusal", "max_tokens"):
            raise RuntimeError(f"Claude stopped early: {response.stop_reason}")
        summary.update(json.loads(next(b.text for b in response.content if b.type == "text")))
        cost += response.usage.input_tokens / 1e6 * 4 + response.usage.output_tokens / 1e6 * 20

    print(f"Insight summary: written by Claude (approx. ${cost:.2f}).")
    conn.execute("INSERT OR REPLACE INTO insight_summaries VALUES (?, ?, ?, ?, ?)",
                 (key, data["date_to"], datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  MODEL, json.dumps(summary, ensure_ascii=False)))
    conn.commit()
    return {**summary, "_written_on": datetime.now(timezone.utc).date().isoformat()}
