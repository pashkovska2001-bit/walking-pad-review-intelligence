"""
Turns the analysed reviews in the database into the numbers the report needs:
theme counts per brand, the customer journey, the Problem Vault top 5,
markets and monthly trends. No AI here, just counting.
"""

import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from math import sqrt

from config import (BRANDS, DB_PATH, EUROPE, JOURNEY, MIN_REVIEWS, PROBLEM_OWNER,
                    STAGE_OF, THEMES, theme_group)

MAX_QUOTE_WORDS = 15
PERIOD_WEEKS = 26      # analysis period: the last 6 months
RECENT_WEEKS = 12      # "recent average": what pushes the TrustScore now
MIN_COUNTRY = 15       # fewer reviews than this from a country: shown, but flagged
COUNTRY_NAME = {"NL": "Netherlands", "DE": "Germany", "BE": "Belgium", "AT": "Austria",
                "GB": "United Kingdom", "FR": "France", "CH": "Switzerland", "IT": "Italy",
                "ES": "Spain", "PL": "Poland", "DK": "Denmark", "SE": "Sweden"}


def week_label(week):
    """'2026-W45' -> 'W45 (2-8 Nov)'"""
    y, w = week.split("-W")
    monday = date.fromisocalendar(int(y), int(w), 1)
    sunday = date.fromisocalendar(int(y), int(w), 7)
    if monday.month == sunday.month:
        span = f"{monday.day}-{sunday.day} {sunday:%b}"
    else:
        span = f"{monday.day} {monday:%b}-{sunday.day} {sunday:%b}"
    return f"W{w} ({span})"


def short_quote(text):
    words = text.split()
    return text if len(words) <= MAX_QUOTE_WORDS else " ".join(words[:MAX_QUOTE_WORDS]) + "…"


def load():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    reviews = [dict(r) for r in conn.execute(
        """SELECT r.*, a.sentiment, a.model FROM reviews r
           JOIN review_analysis a USING (review_id)""")]
    themes = defaultdict(list)
    for t in conn.execute("SELECT * FROM review_themes"):
        themes[t["review_id"]].append(dict(t))
    # Company-side facts kept in the CSV only (invited or organic, reply, reply delay).
    import csv
    from config import REVIEWS_CSV
    extra = {}
    if REVIEWS_CSV.exists():
        for row in csv.DictReader(open(REVIEWS_CSV, encoding="utf-8")):
            extra[row["review_id"]] = row
    for r in reviews:
        r["themes"] = themes.get(r["review_id"], [])
        e = extra.get(r["review_id"], {})
        r["origin"] = e.get("origin") or None
        r["replied"] = e.get("replied") == "1" if e.get("replied") not in (None, "") else None
        r["reply_days"] = int(e["reply_days"]) if e.get("reply_days") not in (None, "") else None
    return reviews


def review_programme(reviews, brand_keys):
    """Invited vs organic reviews, and how the company replies, per brand."""
    out = {}
    for b in brand_keys:
        rs = [r for r in reviews if r["brand"] == b and r["origin"]]
        if not rs:
            continue
        inv = [r for r in rs if r["origin"] == "invited"]
        org = [r for r in rs if r["origin"] == "organic"]
        neg = [r for r in rs if r["rating"] <= 2]
        days = sorted(r["reply_days"] for r in neg if r["reply_days"] is not None)
        out[b] = {
            "n": len(rs),
            "invited_share": round(len(inv) / len(rs), 3),
            "invited_n": len(inv), "organic_n": len(org),
            "invited_rating": round(mean(r["rating"] for r in inv), 2) if len(inv) >= 5 else None,
            "organic_rating": round(mean(r["rating"] for r in org), 2) if len(org) >= 5 else None,
            "invited_low_share": round(sum(r["rating"] <= 2 for r in inv) / len(inv), 3) if len(inv) >= 5 else None,
            "organic_low_share": round(sum(r["rating"] <= 2 for r in org) / len(org), 3) if len(org) >= 5 else None,
            "negative_n": len(neg),
            "negative_replied_share": round(sum(bool(r["replied"]) for r in neg) / len(neg), 3) if neg else None,
            "negative_reply_median_days": days[len(days) // 2] if days else None,
            "negative_replied_within_1_day": round(sum(d <= 1 for d in days) / len(neg), 3) if neg else None,
        }
    return out


def stats_for(reviews):
    """Counts for any group of reviews."""
    n = len(reviews)
    counts = defaultdict(int)
    for r in reviews:
        for t in r["themes"]:
            counts[t["theme"]] += 1
    return {
        "n": n,
        "avg_rating": round(sum(r["rating"] for r in reviews) / n, 2) if n else None,
        "neg_share": round(sum(r["sentiment"] == "negative" for r in reviews) / n, 3) if n else None,
        "theme_counts": dict(counts),
        "theme_shares": {k: round(v / n, 3) for k, v in counts.items()} if n else {},
    }


# ---------------------------------------------------------------------------
# Category ("industry") analytics: across all brands, not only the focus brand
# ---------------------------------------------------------------------------
def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def rating_impact(reviews, brand_keys, theme):
    """How many stars a theme moves a review, compared within the same brand.

    For each brand: average rating of reviews mentioning the theme minus the
    average of reviews that don't. Brands are then combined, weighted by the
    square root of the number of mentions, so one big brand does not decide
    the market alone. Comparing within a brand matters: otherwise a theme
    that is simply common at a low-rated brand would look worse than it is.
    """
    diffs, weights = [], []
    for b in brand_keys:
        rs = [r for r in reviews if r["brand"] == b]
        has = [r["rating"] for r in rs if any(t["theme"] == theme for t in r["themes"])]
        not_ = [r["rating"] for r in rs if not any(t["theme"] == theme for t in r["themes"])]
        if len(has) >= 2 and len(not_) >= 2:
            diffs.append(mean(has) - mean(not_))
            weights.append(sqrt(len(has)))
    if not weights:
        return None
    return round(sum(d * w for d, w in zip(diffs, weights)) / sum(weights), 2)


def category_analytics(reviews, brand_keys, focus, overall):
    competitors = [b for b in brand_keys if b != focus]
    themes = [t for g in THEMES.values() for t in g]
    n_by_brand = {b: overall[b]["n"] for b in brand_keys}

    rows = {}
    for t in themes:
        mentions = sum(overall[b]["theme_counts"].get(t, 0) for b in brand_keys)
        shares = {b: overall[b]["theme_shares"].get(t, 0) for b in brand_keys}
        rows[t] = {
            "theme": t, "group": theme_group(t), "mentions": mentions,
            # Each brand counts equally, so the biggest brand doesn't define "the market".
            "category_share": round(mean(shares.values()), 3),
            "brand_shares": shares,
            "impact": rating_impact(reviews, brand_keys, t) if mentions >= 5 else None,
        }

    # Quadrant label used by the priority matrix and by Claude.
    share_cut = 0.10
    for r in rows.values():
        imp, sh = r["impact"], r["category_share"]
        if imp is None:
            r["quadrant"] = "too few mentions"
        elif imp < 0:
            r["quadrant"] = "deal breaker" if sh >= share_cut else "watch"
        else:
            r["quadrant"] = "core value" if sh >= share_cut else "hidden gem"

    # What each brand is known for: themes where it over-indexes vs the other brands.
    signatures = {}
    for b in brand_keys:
        others = [o for o in brand_keys if o != b]
        diffs = []
        for t in themes:
            cnt = overall[b]["theme_counts"].get(t, 0)
            if cnt < 3 or not others:
                continue
            gap = overall[b]["theme_shares"].get(t, 0) - mean(overall[o]["theme_shares"].get(t, 0) for o in others)
            diffs.append((t, round(gap, 3), cnt))
        pos = sorted([d for d in diffs if theme_group(d[0]) != "pain_point" and d[1] > 0], key=lambda d: -d[1])[:3]
        neg = sorted([d for d in diffs if theme_group(d[0]) == "pain_point" and d[1] > 0], key=lambda d: -d[1])[:3]
        signatures[b] = {"loved_for": [{"theme": t, "gap": g, "count": c} for t, g, c in pos],
                         "criticised_for": [{"theme": t, "gap": g, "count": c} for t, g, c in neg]}

    # Focus brand vs best in class, per theme.
    best = {}
    for t in themes:
        if not competitors:
            break
        pick = min if theme_group(t) == "pain_point" else max
        b = pick(competitors, key=lambda c: overall[c]["theme_shares"].get(t, 0))
        best[t] = {"brand": b, "share": overall[b]["theme_shares"].get(t, 0)}

    # Rough estimate: stars the focus brand could win back if each pain point
    # were only as common as at the average competitor.
    bridge, start = [], overall[focus]["avg_rating"]
    for t in THEMES["pain_point"]:
        r = rows[t]
        f_sh = overall[focus]["theme_shares"].get(t, 0)
        c_sh = mean(overall[c]["theme_shares"].get(t, 0) for c in competitors) or 0
        if r["impact"] is not None and r["impact"] < 0 and f_sh > c_sh:
            bridge.append({"theme": t, "focus_share": f_sh, "comp_share": round(c_sh, 3),
                           "stars": round((f_sh - c_sh) * -r["impact"], 2)})
    bridge.sort(key=lambda x: -x["stars"])

    # The themes overlap (one review often has delivery AND service), so the
    # steps above can't simply be added up. The total is estimated without
    # double counting: keep the focus brand's own ratings for reviews with and
    # without a problem, but use the competitors' share of reviews with a problem.
    def has_pain(r):
        return any(t["theme_group"] == "pain_point" for t in r["themes"])
    f_rs = [r for r in reviews if r["brand"] == focus]
    c_rs = [r for r in reviews if r["brand"] in competitors]
    potential = None
    if f_rs and c_rs:
        with_p = mean(r["rating"] for r in f_rs if has_pain(r))
        without_p = mean(r["rating"] for r in f_rs if not has_pain(r))
        p_focus = sum(has_pain(r) for r in f_rs) / len(f_rs)
        p_comp = mean(sum(has_pain(r) for r in c_rs if r["brand"] == c) /
                      max(1, sum(r["brand"] == c for r in c_rs)) for c in competitors)
        if with_p is not None and without_p is not None:
            potential = round(p_comp * with_p + (1 - p_comp) * without_p, 2)
            # Split the total over the themes in proportion to their raw effect.
            raw = sum(x["stars"] for x in bridge) or 1
            for x in bridge:
                x["stars"] = round((potential - start) * x["stars"] / raw, 2)
            bridge = [x for x in bridge if x["stars"] >= 0.01]
            pain_mix = {"focus_problem_share": round(p_focus, 3), "comp_problem_share": round(p_comp, 3),
                        "focus_rating_with_problem": round(with_p, 2),
                        "focus_rating_without_problem": round(without_p, 2)}

    # What is inside the 1-2 star reviews (focus brand vs competitors).
    def low_star_shares(rs):
        low = [r for r in rs if r["rating"] <= 2]
        cnt = defaultdict(int)
        for r in low:
            for t in {x["theme"] for x in r["themes"]}:
                cnt[t] += 1
        return {"n": len(low), "shares": {t: round(c / len(low), 3) for t, c in cnt.items()} if low else {}}

    return {
        "themes": rows,
        "share_cut": share_cut,
        "signatures": signatures,
        "best_in_class": best,
        "bridge": {"start": start, "steps": bridge, "potential": potential,
                   **(pain_mix if potential is not None else {})},
        "low_star": {"focus": low_star_shares([r for r in reviews if r["brand"] == focus]),
                     "competitors": low_star_shares([r for r in reviews if r["brand"] in competitors])},
        "total_reviews": sum(n_by_brand.values()),
        "avg_rating": round(mean(r["rating"] for r in reviews), 2),
    }


def public_profiles():
    """What a customer sees on each brand's Trustpilot page: TrustScore, number of
    reviews, star distribution (all-time), reply rate. Per brand, the main page
    is the headline; other country pages are listed with it."""
    import json
    from config import DATA_DIR
    f = DATA_DIR / "trustpilot_profiles.json"
    if not f.exists():
        return {}
    snap = json.load(open(f))
    out = {}
    for domain, pg in snap["pages"].items():
        b = out.setdefault(pg["brand"], {"main": None, "pages": [], "captured_on": snap["captured_on"]})
        page = {**pg, "domain": domain}
        b["pages"].append(page)
        if pg.get("main"):
            b["main"] = page
    for b in out.values():
        b["pages"].sort(key=lambda p: -p["total_reviews"])
        b["main"] = b["main"] or b["pages"][0]
    return out


def agent_index(reviews):
    """One compact row per review, for the 'Ask the reviews' agent's counting tool:
    [brand, country, date, stars, origin, themes, Trustpilot id]. No text, no reviewer data."""
    rows = sorted(reviews, key=lambda r: r["review_date"], reverse=True)
    return [[r["brand"], r["country"].upper(), r["review_date"], r["rating"], r["origin"] or "",
             [t["theme"] for t in r["themes"]], r["review_id"].replace("TP-", "")] for r in rows]


def evidence_rows(reviews):
    """Every tagged quote (max 15 words), for the clickable evidence explorer.
    Only short quotes are published, never full review texts or reviewer data.
    'x' points to the review's row in agent_index (same sort order)."""
    out = []
    for x, r in enumerate(sorted(reviews, key=lambda r: r["review_date"], reverse=True)):
        for t in r["themes"]:
            row = {"b": r["brand"], "d": r["review_date"], "w": r["week"], "r": r["rating"], "x": x,
                   "l": r["language"], "t": t["theme"], "q": short_quote(t["quote_en"])}
            if r["language"] != "en":
                row["o"] = short_quote(t["quote_original"])
            out.append(row)
    return out


def has_group(r, group, themes=None):
    return any(t["theme_group"] == group and (themes is None or t["theme"] in themes) for t in r["themes"])


def journey_analytics(reviews, brand_keys, focus):
    """Per stage of the journey: how often it comes up, how often it goes wrong
    (red) or right (green), and how many stars a problem there costs."""
    competitors = [b for b in brand_keys if b != focus]
    out = []
    for st in JOURNEY:
        pains = {t for t in st["themes"] if theme_group(t) == "pain_point"}
        goods = {t for t in st["themes"] if theme_group(t) == "delight"}
        per = {}
        for b in brand_keys:
            rs = [r for r in reviews if r["brand"] == b]
            bad = [r for r in rs if any(t["theme"] in pains for t in r["themes"])]
            good = [r for r in rs if any(t["theme"] in goods for t in r["themes"])]
            ok = [r for r in rs if r not in bad]
            per[b] = {"n": len(rs),
                      "problem_share": round(len(bad) / len(rs), 3) if rs else None,
                      "delight_share": round(len(good) / len(rs), 3) if rs and goods else None,
                      "problem_count": len(bad), "delight_count": len(good),
                      "rating_with_problem": round(mean(r["rating"] for r in bad), 2) if len(bad) >= 3 else None,
                      "rating_without_problem": round(mean(r["rating"] for r in ok), 2) if ok else None}
        # Stars a problem at this stage costs, compared within each brand.
        diffs, w = [], []
        for b in brand_keys:
            p = per[b]
            if p["rating_with_problem"] is not None and p["rating_without_problem"] is not None:
                diffs.append(p["rating_with_problem"] - p["rating_without_problem"])
                w.append(sqrt(p["problem_count"]))
        impact = round(sum(d * x for d, x in zip(diffs, w)) / sum(w), 2) if w else None
        market = {k: round(mean(per[b][k] for b in competitors), 3)
                  if competitors and per[competitors[0]][k] is not None else None
                  for k in ("problem_share", "delight_share")}
        theme_rows = []
        for t in st["themes"]:
            theme_rows.append({"theme": t, "group": theme_group(t),
                               "focus_share": round(sum(any(x["theme"] == t for x in r["themes"])
                                                        for r in reviews if r["brand"] == focus) / max(1, per[focus]["n"]), 3),
                               "market_share": round(mean(
                                   sum(any(x["theme"] == t for x in r["themes"]) for r in reviews if r["brand"] == c)
                                   / max(1, per[c]["n"]) for c in competitors), 3) if competitors else None})
        out.append({"key": st["key"], "name": st["name"], "themes": theme_rows,
                    "brands": per, "market": market, "impact": impact})
    return out


def problem_vault(reviews, focus, cat, today):
    """Prototype of a 'Customer Problem Vault', fed only by public reviews:
    the focus brand's top 5 problems, ranked by the stars they cost."""
    rs = [r for r in reviews if r["brand"] == focus]
    n = len(rs)
    if not n:
        return []
    mid = (today - timedelta(weeks=PERIOD_WEEKS // 2)).isoformat()
    first = [r for r in rs if r["review_date"] < mid]
    second = [r for r in rs if r["review_date"] >= mid]
    low = [r for r in rs if r["rating"] <= 2]
    rows = []
    for t in THEMES["pain_point"]:
        hit = [r for r in rs if any(x["theme"] == t for x in r["themes"])]
        if len(hit) < 3:
            continue
        others = [r for r in rs if r not in hit]
        stars_with, stars_without = mean(r["rating"] for r in hit), mean(r["rating"] for r in others)
        cost = (stars_without - stars_with) if others else 0
        share = len(hit) / n
        def sh(group):
            return round(sum(any(x["theme"] == t for x in r["themes"]) for r in group) / len(group), 3) if group else None
        rows.append({
            "theme": t, "stage": STAGE_OF[t], "owner": PROBLEM_OWNER[t],
            "count": len(hit), "share": round(share, 3),
            "market_share": round(mean(cat["themes"][t]["brand_shares"][c] for c in cat["themes"][t]["brand_shares"]
                                       if c != focus), 3) if len(cat["themes"][t]["brand_shares"]) > 1 else None,
            "rating_with": round(stars_with, 2), "rating_without": round(stars_without, 2),
            # Stars this problem takes off the brand's average: how often x how much.
            "stars_lost": round(share * cost, 2),
            "in_low_star": round(sum(any(x["theme"] == t for x in r["themes"]) for r in low) / len(low), 3) if low else None,
            "share_first_half": sh(first), "share_second_half": sh(second),
            "co_occurs": sorted(
                ({"theme": u, "share": round(sum(any(x["theme"] == u for x in r["themes"]) for r in hit) / len(hit), 2)}
                 for u in THEMES["pain_point"] if u != t),
                key=lambda d: -d["share"])[:2],
        })
    rows.sort(key=lambda r: -r["stars_lost"])
    return rows[:5]


def markets(reviews, brand_keys, focus):
    """Focus brand per country, next to the competitors' reviews from that country."""
    out = []
    rs = [r for r in reviews if r["brand"] == focus]
    counts = defaultdict(int)
    for r in rs:
        counts[r["country"].upper()] += 1
    for c, n in sorted(counts.items(), key=lambda x: -x[1]):
        if n < 5:
            continue
        g = [r for r in rs if r["country"].upper() == c]
        comp = [r for r in reviews if r["brand"] != focus and r["country"].upper() == c]
        st = stats_for(g)
        pains = sorted(((t, v) for t, v in st["theme_shares"].items() if theme_group(t) == "pain_point"),
                       key=lambda x: -x[1])[:3]
        out.append({"country": c, "name": COUNTRY_NAME.get(c, c), "n": n, "few": n < MIN_COUNTRY,
                    "avg_rating": st["avg_rating"],
                    "problem_share": round(sum(has_group(r, "pain_point") for r in g) / n, 3),
                    "top_problems": [{"theme": t, "share": v} for t, v in pains],
                    "stages": {s["key"]: round(sum(any(x["theme"] in s["themes"] and x["theme_group"] == "pain_point"
                                                       for x in r["themes"]) for r in g) / n, 3) for s in JOURNEY},
                    "competitor_n": len(comp),
                    "competitor_rating": round(mean(r["rating"] for r in comp), 2) if comp else None})
    return out


def build():
    reviews = load()
    today = date.today()
    small = {}
    if not any(r["is_fictional"] for r in reviews):
        start = (today - timedelta(weeks=PERIOD_WEEKS)).isoformat()
        reviews = [r for r in reviews if r["country"].upper() in EUROPE and r["review_date"] >= start]
    # Only brands with enough reviews in the period are compared.
    counts = defaultdict(int)
    for r in reviews:
        counts[r["brand"]] += 1
    focus = next(b["key"] for b in BRANDS if b["is_focus"])
    brand_keys = [b["key"] for b in BRANDS if counts[b["key"]] >= MIN_REVIEWS or (b["key"] == focus and counts[b["key"]])]
    small = {b["key"]: counts[b["key"]] for b in BRANDS if 0 < counts[b["key"]] < MIN_REVIEWS and b["key"] != focus}
    reviews = [r for r in reviews if r["brand"] in brand_keys]
    competitors = [k for k in brand_keys if k != focus]

    by_brand = {b: [r for r in reviews if r["brand"] == b] for b in brand_keys}
    overall = {b: stats_for(rs) for b, rs in by_brand.items()}
    recent_from = (today - timedelta(weeks=RECENT_WEEKS)).isoformat()
    recent = {b: stats_for([r for r in rs if r["review_date"] >= recent_from]) for b, rs in by_brand.items()}
    for b, rs in by_brand.items():
        overall[b]["problem_share"] = round(sum(has_group(r, "pain_point") for r in rs) / len(rs), 3)
        rr = [r for r in rs if r["review_date"] >= recent_from]
        recent[b]["problem_share"] = round(sum(has_group(r, "pain_point") for r in rr) / len(rr), 3) if rr else None

    months = sorted({r["review_date"][:7] for r in reviews})
    min_day = {m: min(r["review_date"] for r in reviews if r["review_date"][:7] == m) for m in months}
    def mlabel(m):
        d = date(int(m[:4]), int(m[5:]), 1)
        if m == months[0] and min_day[m][8:] != "01":
            return f"{d:%b} (from {int(min_day[m][8:])})"
        if m == months[-1] and m == today.isoformat()[:7]:
            return f"{d:%b} (to {today.day})"
        return f"{d:%b}"
    monthly = {b: {m: stats_for([r for r in rs if r["review_date"][:7] == m]) for m in months}
               for b, rs in by_brand.items()}
    for b, rs in by_brand.items():
        for m in months:
            g = [r for r in rs if r["review_date"][:7] == m]
            monthly[b][m]["problem_share"] = round(sum(has_group(r, "pain_point") for r in g) / len(g), 3) if g else None

    def comp_avg(getter):
        vals = [v for v in (getter(b) for b in competitors) if v is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    comp_overall_shares = {t: comp_avg(lambda b: overall[b]["theme_shares"].get(t, 0))
                           for g in THEMES.values() for t in g}

    evidence = defaultdict(dict)
    for r in sorted(reviews, key=lambda r: r["review_date"]):
        for t in r["themes"]:
            evidence[r["brand"]][t["theme"]] = {
                "quote_en": short_quote(t["quote_en"]), "quote_original": short_quote(t["quote_original"]),
                "language": r["language"], "date": r["review_date"], "source": r["source"], "rating": r["rating"]}

    cat = category_analytics(reviews, brand_keys, focus, overall)
    return {
        "focus": focus,
        "competitors": competitors,
        "small_brands": small,
        "period_weeks": PERIOD_WEEKS, "recent_weeks": RECENT_WEEKS,
        "months": months,
        "month_labels": [mlabel(m) for m in months],
        "overall": overall,
        "recent": recent,
        "monthly": monthly,
        "comp_overall_shares": comp_overall_shares,
        "comp_monthly_rating": [comp_avg(lambda b: monthly[b][m]["avg_rating"]) for m in months],
        "evidence": evidence,
        "category": cat,
        "journey": journey_analytics(reviews, brand_keys, focus),
        "vault": problem_vault(reviews, focus, cat, today),
        "markets": markets(reviews, brand_keys, focus),
        "programme": review_programme(reviews, brand_keys),
        "evidence_rows": evidence_rows(reviews),
        "agent_index": agent_index(reviews),
        "profiles": public_profiles(),
        "n_reviews": len(reviews),
        "n_by_brand": {b: len(rs) for b, rs in by_brand.items()},
        "is_fictional": any(r["is_fictional"] for r in reviews),
        "sources": sorted({r["source"] for r in reviews}),
        "languages": sorted({r["language"] for r in reviews}),
        "countries": len({r["country"] for r in reviews}),
        "models": sorted({r["model"] for r in reviews}),
        "date_from": min(r["review_date"] for r in reviews),
        "date_to": max(r["review_date"] for r in reviews),
    }
