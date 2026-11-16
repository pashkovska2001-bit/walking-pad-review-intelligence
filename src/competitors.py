"""
What competitors' customers say, and what the focus brand could learn from it.

Numbers come from the tagged reviews. Claude writes one short lesson per
competitor from those numbers and a handful of short quotes (one call, cached
for 7 days like the other insight texts).
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from html import escape

import anthropic

from config import BRAND_NAMES, DB_PATH, THEMES

MODEL = "claude-opus-5-5"
THEME_LABEL = {k: v for g in THEMES.values() for k, v in g.items()}
POSITIVE = list(THEMES["delight"]) + list(THEMES["purchase_driver"])
PAIN = list(THEMES["pain_point"])


def brand_view(data, b):
    sh = data["overall"][b]["theme_shares"]
    f = data["overall"][data["focus"]]["theme_shares"]
    praise = sorted(POSITIVE, key=lambda t: -sh.get(t, 0))[:4]
    pains = sorted(PAIN, key=lambda t: -sh.get(t, 0))[:3]
    return {
        "brand": BRAND_NAMES[b],
        "reviews": data["overall"][b]["n"],
        "avg_stars_6m": data["overall"][b]["avg_rating"],
        "share_mentioning_a_problem": data["overall"][b]["problem_share"],
        "most_praised": [{"theme": THEME_LABEL[t], "share": round(sh.get(t, 0), 3),
                          "focus_brand_share": round(f.get(t, 0), 3)} for t in praise if sh.get(t, 0)],
        "top_complaints": [{"theme": THEME_LABEL[t], "share": round(sh.get(t, 0), 3),
                            "focus_brand_share": round(f.get(t, 0), 3)} for t in pains if sh.get(t, 0)],
    }


def quotes_for(data, b, themes, n=3, positive=True):
    out = []
    for t in themes:
        k = 0
        for e in data["evidence_rows"]:
            if e["b"] == b and e["t"] == t and ((e["r"] >= 4) if positive else (e["r"] <= 2)):
                out.append({"theme": THEME_LABEL[t], "stars": e["r"], "quote": e["q"]})
                k += 1
                if k >= n:
                    break
    return out


def payload(data):
    comps = []
    for b in data["competitors"]:
        v = brand_view(data, b)
        sh = data["overall"][b]["theme_shares"]
        top = sorted(POSITIVE, key=lambda t: -sh.get(t, 0))[:3]
        v["praise_quotes"] = quotes_for(data, b, top, 2)
        v["complaint_quotes"] = quotes_for(data, b, sorted(PAIN, key=lambda t: -sh.get(t, 0))[:2], 2, positive=False)
        comps.append(v)
    return {"focus_brand": brand_view(data, data["focus"]), "competitors": comps}


SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["summary", "lessons"],
    "properties": {
        "summary": {"type": "string"},
        "lessons": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["brand", "what_customers_value", "evidence", "idea_for_focus_brand"],
            "properties": {"brand": {"type": "string"}, "what_customers_value": {"type": "string"},
                           "evidence": {"type": "string"}, "idea_for_focus_brand": {"type": "string"}}}},
    },
}

PROMPT = """You help the customer experience lead of a walking pad brand learn from competitors'
public reviews. Below: the focus brand and each competitor, with the themes their reviewers
praise and complain about most (share of reviews), the focus brand's share for the same theme,
and a few short quotes.

Return JSON:
- summary: two sentences on what competitors' customers value that the focus brand's customers
  rarely mention, and where a competitor shares the focus brand's problems.
- lessons: one per competitor. what_customers_value: a short phrase. evidence: one sentence with
  numbers from the data (competitor share vs focus brand share). idea_for_focus_brand: one concrete,
  practical idea a CX lead could try, grounded in what those reviews describe.
Rules: use only the numbers and quotes given; no outside knowledge about any brand; no claims about
anyone's internal operations; plain English, one sentence per field; no market-entry advice.

Data:
"""


def get_lessons(data, force=False, max_age_days=7):
    p = json.dumps(payload(data), ensure_ascii=False, sort_keys=True)
    key = "competitors:" + hashlib.sha256((MODEL + PROMPT + p).encode()).hexdigest()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS competitor_lessons (key TEXT PRIMARY KEY, created_at TEXT, result TEXT)""")
    if not force:
        row = conn.execute("SELECT result, created_at FROM competitor_lessons ORDER BY created_at DESC LIMIT 1").fetchone()
        if row and (datetime.now(timezone.utc) - datetime.fromisoformat(row[1])).days < max_age_days:
            return json.loads(row[0])
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL, max_tokens=4000,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": PROMPT + p}],
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"Claude stopped early: {response.stop_reason}")
    result = json.loads(next(b.text for b in response.content if b.type == "text"))
    cost = response.usage.input_tokens / 1e6 * 4 + response.usage.output_tokens / 1e6 * 20
    print(f"Competitor lessons: written by Claude (approx. ${cost:.3f}).")
    conn.execute("INSERT OR REPLACE INTO competitor_lessons VALUES (?, ?, ?)",
                 (key, datetime.now(timezone.utc).isoformat(timespec="seconds"), json.dumps(result, ensure_ascii=False)))
    conn.commit()
    return result


def section(data, lessons, brand_color, short_brand, ev_attrs, pct):
    """HTML: one card per competitor with praise vs focus brand, complaints, quotes and Claude's idea."""
    f = data["focus"]
    by_name = {l["brand"]: l for l in (lessons or {}).get("lessons", [])}
    cards = []
    for i, b in enumerate(data["competitors"], 1):
        v = brand_view(data, b)
        sh = data["overall"][b]["theme_shares"]
        rows = "".join(
            f"""<li{ev_attrs(brand=b, theme=next(k for k, lbl in THEME_LABEL.items() if lbl == x['theme']))}>
              <span class="cl-t">{escape(x['theme'])}</span>
              <span class="cl-v good">▲ {pct(x['share'])}</span><span class="cl-f">{escape(short_brand(f))} {pct(x['focus_brand_share'])}</span></li>"""
            for x in v["most_praised"][:3])
        bad = "".join(
            f"""<li><span class="cl-t">{escape(x['theme'])}</span>
              <span class="cl-v bad">▼ {pct(x['share'])}</span><span class="cl-f">{escape(short_brand(f))} {pct(x['focus_brand_share'])}</span></li>"""
            for x in v["top_complaints"][:2])
        top = sorted(POSITIVE, key=lambda t: -sh.get(t, 0))[:2]
        qs = "".join(f'<blockquote>“{escape(q["quote"])}” <span class="muted">{q["stars"]}★</span></blockquote>'
                     for q in quotes_for(data, b, top, 1))
        l = by_name.get(BRAND_NAMES[b]) or next((x for x in by_name.values() if short_brand(b).lower() in x["brand"].lower()), None)
        idea = (f'<p class="cl-val"><b>{escape(l["what_customers_value"])}</b></p>'
                f'<p class="cl-ev">{escape(l["evidence"])}</p>'
                f'<p class="cl-idea"><span class="lbl">Idea for {escape(short_brand(f))}</span>{escape(l["idea_for_focus_brand"])}</p>') if l else ""
        cards.append(f"""<article class="card cl">
          <h3><i class="swatch" style="background:var({brand_color[i]})"></i>{escape(short_brand(b))}
            <span class="muted small">{v['reviews']} reviews · {v['avg_stars_6m']:.1f}★ · {pct(v['share_mentioning_a_problem'])} mention a problem</span></h3>
          {idea}
          <p class="cl-h">Most praised</p><ul class="cl-list">{rows}</ul>
          <p class="cl-h">Top complaints</p><ul class="cl-list">{bad}</ul>
          {qs}
        </article>""")
    summary = escape((lessons or {}).get("summary", ""))
    return f"""
    <h2>What competitors' customers say</h2>
    <p class="sub">{summary or "What reviewers of each competitor praise and complain about, next to the same theme for " + escape(short_brand(f)) + "."}</p>
    <div class="clgrid">{''.join(cards)}</div>
    <p class="muted small">Shares = share of that brand's reviews in the last 6 months that mention the theme. Ideas are written by Claude from these
    numbers and quotes only. Click a praised theme to see its quotes.</p>"""


CSS = """
.clgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;margin:8px 0}
.cl h3{display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px;margin:0 0 8px}
.cl h3 .muted{font-family:inherit;font-weight:400;width:100%}
.cl .swatch{width:12px;height:12px;border-radius:3px;display:inline-block}
.cl-val{margin:4px 0}.cl-ev{margin:4px 0;color:var(--text-secondary);font-size:14px}
.cl-idea{margin:8px 0 10px;background:var(--pos-soft);border-radius:10px;padding:8px 10px;font-size:14px}
.cl-h{margin:10px 0 4px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.cl-list{list-style:none;margin:0;padding:0;font-size:14px}
.cl-list li{display:grid;grid-template-columns:1fr auto auto;gap:10px;padding:4px 0;border-bottom:1px solid var(--border)}
.cl-list li[data-ev]{cursor:pointer}.cl-list li[data-ev]:hover .cl-t{text-decoration:underline}
.cl-v{font-weight:700;font-variant-numeric:tabular-nums}.cl-v.good{color:var(--good)}.cl-v.bad{color:var(--bad)}
.cl-f{color:var(--muted);font-variant-numeric:tabular-nums;min-width:74px;text-align:right}
.cl blockquote{margin:8px 0 0;padding:6px 10px;border-left:3px solid var(--pos);background:var(--surface-2);border-radius:0 8px 8px 0;font-size:14px}
"""
