"""
Build the interactive HTML report.

One self-contained HTML file, organised as tabs that go from the big picture
to the detail:

    Overview          headline, public ratings, 3 insights, action roadmap
    Customer journey  what goes wrong (red) and right (green) at each stage
                      after the order, for walking pad buyers and the focus brand
    Problem Vault     the focus brand's top 5 problems: cost, owner, cause, fix
    Focus brand       countries, review programme, monthly trend, rating potential
    Category          what moves ratings in the category, brand profiles, matrix
    Evidence          every tagged quote, filterable (click anything to land here)
    Method            how the numbers are made, and the limitations

Files written:
    reports/report-<date>.html   (kept for history)
    reports/latest.html          (always the newest)
    reports/publish/walking-pad-insights.html  (page content for the private link)

Run:
    python src/build_report.py            # reuse the insight summary if data unchanged
    python src/build_report.py --refresh  # ask Claude for a fresh summary
"""

import argparse
import json
import shutil
from datetime import datetime
from html import escape

import competitors
from triage_tab import CSS as TRI_CSS, TRIAGE_JS, tab_triage
from ask_tab import ASK_CSS, ASK_JS, ask_json, tab_ask
from config import BRAND_NAMES, JOURNEY, REPORTS_DIR, SOURCES, STAGE_OF, THEME_GROUP_LABELS, THEMES
from insights import get_insights
from report_data import build

THEME_LABEL = {k: v for g in THEMES.values() for k, v in g.items()}
# Short names for charts, where space is tight.
THEME_SHORT = {
    "compact_size": "Compact", "quiet_motor": "Quiet motor", "price_value": "Price / value",
    "design_look": "Design", "work_from_home": "Work from home", "brand_trust": "Brand trust",
    "app_features": "App features", "delivery_delay": "Late delivery",
    "preorder_communication": "Pre-order dates", "damaged_in_transit": "Damaged on arrival",
    "assembly_setup": "Setup", "noise": "Noise", "durability": "Breakdowns",
    "app_connectivity": "App connection", "returns_refunds": "Returns / refunds",
    "warranty_claims": "Warranty", "customer_service": "Slow service",
    "daily_habit": "Daily habit", "quiet_while_working": "Quiet at work", "easy_to_store": "Easy to store",
    "helpful_support": "Helpful support", "fast_delivery": "Fast delivery", "build_quality": "Solid build",
}
GROUP_SHORT = {"purchase_driver": "Why they buy", "pain_point": "Problem", "delight": "Going well"}
LANG_NAME = {"en": "English", "nl": "Dutch", "de": "German", "fr": "French", "it": "Italian",
             "es": "Spanish", "pt": "Portuguese", "pl": "Polish", "sv": "Swedish", "da": "Danish"}
STAGE_NAME = {s["key"]: s["name"] for s in JOURNEY}
# Brand identity colours: fixed order, the focus brand always first.
BRAND_COLOR_SLOTS = ["--series-1", "--series-2", "--series-3", "--series-4", "--series-5"]


def pct(x, digits=0):
    return "–" if x is None else f"{x * 100:.{digits}f}%"


def stars(x, digits=1):
    return "–" if x is None else f"{x:.{digits}f}"


def signed(x, digits=1):
    return "–" if x is None else f"{x:+.{digits}f}".replace("-", "−")


def tip(*lines):
    """Tooltip content, stored in a data attribute (escaped)."""
    return escape("<br>".join(lines), quote=True)


def ev_attrs(brand=None, theme=None, stage=None, low=False):
    """Makes an element clickable: opens the Evidence tab with these filters."""
    a = ' role="button" tabindex="0" data-ev="1"'
    if brand:
        a += f' data-ev-brand="{brand}"'
    if theme:
        a += f' data-ev-theme="{theme}"'
    if stage:
        a += f' data-ev-stage="{stage}"'
    if low:
        a += ' data-ev-stars="low"'
    return a


def legend(items):
    return '<div class="legend">' + "".join(
        f'<span><i style="background:var({c})"></i>{escape(name)}</span>' for name, c in items) + "</div>"


def chips(items, cls=""):
    return "".join(f'<span class="tag {cls}">{escape(x)}</span>' for x in items)


def bullet_list(items, cls=""):
    return f'<ul class="{cls}">' + "".join(f"<li>{escape(x)}</li>" for x in items) + "</ul>"


def findings_list(items):
    return '<ul class="findings">' + "".join(
        f'<li><b>{escape(f["title"])}.</b> {escape(f["detail"])}</li>' for f in items) + "</ul>"


def tile(label, value, note="", cls=""):
    return (f'<div class="tile {cls}"><div class="tlabel">{label}</div><div class="tval">{value}</div>'
            f'<div class="tnote">{note}</div></div>')


def short_brand(b):
    return BRAND_NAMES[b].split(" (")[0]


# ---------------------------------------------------------------------------
# Illustrations (drawn here, simple line style; no third-party images)
# ---------------------------------------------------------------------------
ICON = {
    "before": '<path d="M5 9h4l3.5 15h15L31 13H11"/><circle cx="15" cy="30" r="2.2"/><circle cx="26" cy="30" r="2.2"/><path d="M19 6l1.6 3.2 3.4.5-2.5 2.4.6 3.4-3.1-1.6-3.1 1.6.6-3.4-2.5-2.4 3.4-.5z" class="fill"/>',
    "order": '<rect x="4" y="15" width="20" height="17" rx="2"/><path d="M4 21h20M14 15v6"/><circle cx="28" cy="12" r="7.5" class="fill-soft"/><path d="M28 8v4.5l3 2"/>',
    "delivery": '<rect x="3" y="11" width="20" height="15" rx="2"/><path d="M23 15h6.5l4.5 6v5h-11z"/><circle cx="10" cy="28" r="3" class="fill-soft"/><circle cx="28" cy="28" r="3" class="fill-soft"/>',
    "setup": '<path d="M5 15l13-6 13 6-13 6z" class="fill-soft"/><path d="M5 15v12l13 6 13-6V15M18 21v12"/><path d="M10 6l4 4M28 4l-3 5"/>',
    "use": '<circle cx="19" cy="6" r="3"/><path d="M19 9.5l-1.5 9 4 5-1 6M17.5 18.5l-4.5 4.5-1 5M18.5 12l5 3.5 4-1.5M18.5 12l-4.5 3"/><rect x="5" y="31" width="27" height="3.5" rx="1.75" class="fill-soft"/>',
    "service": '<path d="M8 21v-3a10 10 0 0 1 20 0v3"/><rect x="5" y="19" width="6" height="9" rx="2.5" class="fill-soft"/><rect x="25" y="19" width="6" height="9" rx="2.5" class="fill-soft"/><path d="M28 28c0 3-3 5-7 5h-2"/>',
    "after": '<path d="M29 13H13a7 7 0 0 0 0 14h13"/><path d="M17 8l-5 5 5 5"/><path d="M27 21l2 2 4-4" class="ok"/>',
}


def icon(key, size=40):
    return (f'<svg class="icon" viewBox="0 0 36 36" width="{size}" height="{size}" aria-hidden="true">'
            f'{ICON[key]}</svg>')


HERO = """<svg class="hero-art" viewBox="0 0 300 210" role="img" aria-label="Illustration: a person walking on a walking pad at a standing desk, with a happy and an unhappy review bubble">
  <ellipse cx="150" cy="196" rx="135" ry="9" class="shadow"/>
  <rect x="58" y="178" width="150" height="14" rx="7" class="pad"/>
  <path d="M74 185h118" class="belt"/>
  <rect x="150" y="104" width="118" height="9" rx="3" class="desk"/>
  <path d="M252 113v78M166 113v78" class="line"/>
  <path d="M190 104l8-30h40l-6 30z" class="screen"/>
  <circle cx="122" cy="52" r="15" class="skin"/>
  <path d="M110 47c3-11 21-14 27-3-6 1-12-2-15-5-2 4-6 7-12 8z" class="hair"/>
  <path d="M119 68c-6 16-8 34-7 50" class="body"/>
  <path d="M117 82c12 8 26 13 44 18M116 84c-8 12-12 20-11 30" class="limb"/>
  <path d="M112 118c-8 18-13 34-18 58M113 118c10 16 18 32 30 56" class="limb"/>
  <path d="M86 178h16M136 176h16" class="shoe"/>
  <g class="bubble good"><rect x="12" y="20" width="76" height="34" rx="12"/><path d="M60 54l8 10 2-10z"/>
    <text x="50" y="42" text-anchor="middle">★★★★★</text></g>
  <g class="bubble bad"><rect x="196" y="16" width="92" height="34" rx="12"/><path d="M214 50l-6 10 14-10z"/>
    <text x="242" y="38" text-anchor="middle">Where is my order?</text></g>
</svg>"""


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def line_chart(series, labels, y_min, y_max, y_ticks, fmt, aria, ref=None):
    """series: [{name, color (css var), values, counts?}] -> inline SVG with hover.
    ref: optional (value, label) dashed reference line."""
    W, H, L, R, T, B = 520, 230, 34, 122, 12, 30
    pw, ph = W - L - R, H - T - B
    n = len(labels)
    x = lambda i: L + (pw * i / (n - 1) if n > 1 else pw / 2)
    y = lambda v: T + ph * (1 - (v - y_min) / (y_max - y_min))

    out = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(aria)}">']
    for t in y_ticks:
        out.append(f'<line class="grid" x1="{L}" x2="{L + pw}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>')
        out.append(f'<text class="tick" x="{L - 8}" y="{y(t) + 4:.1f}" text-anchor="end">{fmt(t)}</text>')
    out.append(f'<line class="axis" x1="{L}" x2="{L + pw}" y1="{T + ph}" y2="{T + ph}"/>')
    for i, lab in enumerate(labels):
        out.append(f'<text class="tick" x="{x(i):.1f}" y="{H - 12}" text-anchor="middle">{escape(lab.split(" ")[0])}</text>')
    if ref:
        out.append(f'<line class="refline" x1="{L}" x2="{L + pw}" y1="{y(ref[0]):.1f}" y2="{y(ref[0]):.1f}"/>'
                   f'<text class="reflabel" x="{L + pw - 4}" y="{y(ref[0]) + 15:.1f}" text-anchor="end">{escape(ref[1])}</text>')

    for i, lab in enumerate(labels):
        x0 = (x(i - 1) + x(i)) / 2 if i else L
        x1 = (x(i) + x(i + 1)) / 2 if i < n - 1 else L + pw
        lines = [f"<b>{escape(lab)}</b>"] + [
            f'{escape(s["name"])}: {fmt(s["values"][i]) if s["values"][i] is not None else "no data"}'
            + (f' ({s["counts"][i]} reviews)' if s.get("counts") else "")
            for s in series]
        out.append(f'<g class="hit" tabindex="0" data-tip="{tip(*lines)}">'
                   f'<rect x="{x0:.1f}" y="{T}" width="{x1 - x0:.1f}" height="{ph}" fill="transparent"/>'
                   f'<line class="xh" x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{T}" y2="{T + ph}"/></g>')

    end_labels = []
    for s in series:
        pts = [(x(i), y(v)) for i, v in enumerate(s["values"]) if v is not None]
        if not pts:
            continue
        d = " ".join(("M" if j == 0 else "L") + f"{px:.1f},{py:.1f}" for j, (px, py) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="var({s["color"]})" stroke-width="2" '
                   f'stroke-linejoin="round" stroke-linecap="round" pointer-events="none"/>')
        for px, py in pts:
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="var({s["color"]})" '
                       f'stroke="var(--surface-1)" stroke-width="2" pointer-events="none"/>')
        last = [v for v in s["values"] if v is not None][-1]
        end_labels.append([pts[-1][1], s, last])

    end_labels.sort(key=lambda e: e[0])
    for j in range(1, len(end_labels)):
        if end_labels[j][0] - end_labels[j - 1][0] < 16:
            end_labels[j][0] = end_labels[j - 1][0] + 16
    for ly, s, last in end_labels:
        lx = L + pw + 10
        out.append(f'<line x1="{lx}" x2="{lx + 12}" y1="{ly:.1f}" y2="{ly:.1f}" stroke="var({s["color"]})" stroke-width="2"/>')
        out.append(f'<text class="endlabel" x="{lx + 17}" y="{ly + 4:.1f}">{escape(s["name"])} '
                   f'<tspan class="endval">{fmt(last)}</tspan></text>')
    out.append("</svg>")
    return "".join(out)


def priority_matrix(cat):
    """Key-driver matrix: how common a theme is (x) vs how much it moves the rating (y)."""
    rows = [r for r in cat["themes"].values() if r["impact"] is not None]
    W, H, L, R, T, B = 640, 400, 46, 20, 18, 46
    pw, ph = W - L - R, H - T - B
    x_max = max(0.1, max(r["category_share"] for r in rows))
    x_max = min(1.0, (int(x_max * 10) + 1) / 10)
    y_lo = min(-1, int(min(r["impact"] for r in rows)) - 1)
    y_hi = max(1, int(max(r["impact"] for r in rows)) + 1)
    x = lambda v: L + pw * v / x_max
    y = lambda v: T + ph * (1 - (v - y_lo) / (y_hi - y_lo))
    cut = cat["share_cut"]

    out = [f'<svg class="chart matrix" viewBox="0 0 {W} {H}" role="img" '
           f'aria-label="Priority matrix: share of reviews mentioning each theme against its effect on the star rating">']
    out.append(f'<rect x="{x(cut):.1f}" y="{y(0):.1f}" width="{x(x_max) - x(cut):.1f}" height="{y(y_lo) - y(0):.1f}" class="q-bad"/>')
    for yv in range(y_lo, y_hi + 1):
        out.append(f'<line class="grid" x1="{L}" x2="{L + pw}" y1="{y(yv):.1f}" y2="{y(yv):.1f}"/>')
        out.append(f'<text class="tick" x="{L - 8}" y="{y(yv) + 4:.1f}" text-anchor="end">{signed(yv, 0) if yv else "0"}</text>')
    for k in range(0, int(round(x_max * 10)) + 1):
        xv = k / 10
        out.append(f'<text class="tick" x="{x(xv):.1f}" y="{T + ph + 18}" text-anchor="middle">{xv * 100:.0f}%</text>')
    out.append(f'<line class="axis strong" x1="{L}" x2="{L + pw}" y1="{y(0):.1f}" y2="{y(0):.1f}"/>')
    out.append(f'<line class="axis dashed" x1="{x(cut):.1f}" x2="{x(cut):.1f}" y1="{T}" y2="{T + ph}"/>')
    out.append(f'<text class="axislabel" x="{L + pw / 2}" y="{H - 4}" text-anchor="middle">Share of reviews mentioning the theme (average of brands) →</text>')
    out.append(f'<text class="axislabel" transform="translate(12 {T + ph / 2}) rotate(-90)" text-anchor="middle">Effect on star rating</text>')
    ql = [(x(x_max) - 6, T + 14, "end", "CORE VALUE · protect"),
          (x(x_max) - 6, T + ph - 8, "end", "DEAL BREAKERS · fix first"),
          (x(0) + 8, T + 14, "start", "HIDDEN GEMS · amplify"),
          (x(0) + 8, T + ph - 8, "start", "WATCH")]
    for qx, qy, anchor, text in ql:
        out.append(f'<text class="qlabel" x="{qx:.1f}" y="{qy:.1f}" text-anchor="{anchor}">{text}</text>')

    placed = []
    for r in sorted(rows, key=lambda r: -r["category_share"]):
        cx, cy = x(r["category_share"]), y(r["impact"])
        neg = r["impact"] < 0
        color = "--neg" if neg else "--pos"
        lines = [f'<b>{escape(THEME_LABEL[r["theme"]])}</b>',
                 f'{pct(r["category_share"])} of reviews (average of brands), {r["mentions"]} mentions',
                 f'Effect on rating: {signed(r["impact"])} stars',
                 "Click to read the quotes"]
        shape = (f'<path d="M{cx:.1f},{cy + 7:.1f} l7,-12 h-14z" fill="var({color})" stroke="var(--surface-1)" stroke-width="1.5"/>'
                 if neg else
                 f'<path d="M{cx:.1f},{cy - 7:.1f} l7,12 h-14z" fill="var({color})" stroke="var(--surface-1)" stroke-width="1.5"/>')
        out.append(f'<g class="dot"{ev_attrs(theme=r["theme"])} data-tip="{tip(*lines)}">'
                   f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="15" fill="transparent"/>{shape}</g>')
        big = r["category_share"] >= 0.045 or abs(r["impact"]) >= 2
        if big:
            label = THEME_SHORT[r["theme"]]
            w = len(label) * 7 + 4
            sides = [("start", cx + 11, cx + 11, cx + 11 + w), ("end", cx - 11, cx - 11 - w, cx - 11)]
            if cx > L + pw * 0.75:
                sides.reverse()
            for anchor, lx, x0, x1 in sides:
                if x0 < L or x1 > L + pw:
                    continue
                if all(abs(cy - py) > 14 or x1 < px0 or x0 > px1 for px0, px1, py in placed):
                    out.append(f'<text class="dotlabel" x="{lx:.1f}" y="{cy + 4:.1f}" text-anchor="{anchor}">{escape(label)}</text>')
                    placed.append((x0, x1, cy))
                    break
    out.append("</svg>")
    return "".join(out)


def pair_bars(rows, a, b, fmt=pct):
    """rows: [(label, a_value, b_value, tooltip_lines, ev_kwargs)]; a/b: (name, css colour var)."""
    vmax = max([r[1] or 0 for r in rows] + [r[2] or 0 for r in rows] + [0.01])
    out = []
    for label, va, vb, lines, ev in rows:
        out.append(
            f'<div class="brow"{ev_attrs(**ev)} data-tip="{tip(*lines)}">'
            f'<div class="blabel">{escape(label)}</div><div class="btrack">'
            f'<div class="bar"><span style="width:{(va or 0) / vmax * 100:.1f}%;background:var({a[1]})"></span><em>{fmt(va)}</em></div>'
            f'<div class="bar"><span style="width:{(vb or 0) / vmax * 100:.1f}%;background:var({b[1]})"></span><em class="muted">{fmt(vb)}</em></div>'
            f'</div></div>')
    return legend([a, b]) + '<div class="bars">' + "".join(out) + "</div>"


def compare_bars(data, group, top=6):
    focus = data["focus"]
    fs, cs = data["overall"][focus]["theme_shares"], data["comp_overall_shares"]
    themes = sorted(THEMES[group], key=lambda t: -max(fs.get(t, 0), cs.get(t, 0) or 0))[:top]
    color = "--neg" if group == "pain_point" else "--pos"
    rows = []
    for t in themes:
        lines = [f"<b>{escape(THEME_LABEL[t])}</b>",
                 f"{BRAND_NAMES[focus]}: {pct(fs.get(t, 0))} of reviews ({data['overall'][focus]['theme_counts'].get(t, 0)})",
                 f"Competitor average: {pct(cs.get(t, 0))}"]
        ev = data["evidence"][focus].get(t)
        if ev:
            lines.append(f"“{escape(ev['quote_en'])}”")
        rows.append((THEME_LABEL[t], fs.get(t, 0), cs.get(t, 0) or 0, lines, {"brand": focus, "theme": t}))
    return pair_bars(rows, (short_brand(focus), color), ("Competitor average", "--series-comp"))


def rating_bridge(data):
    """Waterfall on the 1-5 star scale: 6-month average -> each problem fixed -> estimated potential."""
    br = data["category"]["bridge"]
    if br["potential"] is None:
        return ""
    lo, hi = 1.0, 5.0
    pos = lambda v: (v - lo) / (hi - lo) * 100
    rows = [f'<div class="wrow"><div class="wlabel"><b>6-month average</b></div><div class="wtrack">'
            f'<span class="wbar base" style="left:0;width:{pos(br["start"]):.1f}%"></span></div>'
            f'<div class="wval">{stars(br["start"], 2)}★</div></div>']
    cum = br["start"]
    steps = [x for x in br["steps"] if x["stars"] >= 0.05]
    rest = [x for x in br["steps"] if x["stars"] < 0.05]
    if rest:
        steps.append({"theme": None, "stars": round(sum(x["stars"] for x in rest), 2),
                      "names": [THEME_SHORT[x["theme"]] for x in rest]})
    for s in steps:
        width = max(0.6, pos(cum + s["stars"]) - pos(cum))
        if s["theme"] is None:
            rows.append(f'<div class="wrow" data-tip="{tip("<b>Other problems</b>", escape(", ".join(s["names"])))}">'
                        f'<div class="wlabel">Other problems</div><div class="wtrack">'
                        f'<span class="wbar step" style="left:{pos(cum):.1f}%;width:{width:.1f}%"></span></div>'
                        f'<div class="wval">{signed(s["stars"], 2)}</div></div>')
        else:
            lines = [f'<b>{escape(THEME_LABEL[s["theme"]])}</b>',
                     f'{BRAND_NAMES[data["focus"]]}: {pct(s["focus_share"])} of reviews, competitors {pct(s["comp_share"])}',
                     f'Estimated gain if it matched competitors: {signed(s["stars"], 2)} stars']
            rows.append(f'<div class="wrow"{ev_attrs(brand=data["focus"], theme=s["theme"])} data-tip="{tip(*lines)}">'
                        f'<div class="wlabel">{escape(THEME_SHORT[s["theme"]])}</div><div class="wtrack">'
                        f'<span class="wbar step" style="left:{pos(cum):.1f}%;width:{width:.1f}%"></span></div>'
                        f'<div class="wval">{signed(s["stars"], 2)}</div></div>')
        cum += s["stars"]
    rows.append(f'<div class="wrow"><div class="wlabel"><b>Estimated potential</b></div><div class="wtrack">'
                f'<span class="wbar pot" style="left:0;width:{pos(br["potential"]):.1f}%"></span></div>'
                f'<div class="wval"><b>{stars(br["potential"], 2)}★</b></div></div>')
    axis = "".join(f'<span style="left:{pos(v):.1f}%">{v}★</span>' for v in (1, 2, 3, 4, 5))
    return (f'<div class="waterfall">{"".join(rows)}'
            f'<div class="wrow"><div></div><div class="waxis">{axis}</div><div></div></div></div>')


HEAT_STEPS = [(0.05, "--seq-100", False), (0.10, "--seq-200", False), (0.20, "--seq-300", False),
              (0.30, "--seq-400", True), (0.45, "--seq-500", True), (9.99, "--seq-600", True)]


def heat_matrix(data):
    brands = [data["focus"]] + data["competitors"]
    head = "".join(f'<th class="{"focus" if b == data["focus"] else ""}">{escape(short_brand(b))}'
                   f'<small>{data["overall"][b]["n"]} reviews</small></th>' for b in brands)
    head += '<th>Market<small>avg of brands</small></th>'
    body = []
    for group, themes in THEMES.items():
        body.append(f'<tr class="grouprow"><th colspan="{len(brands) + 2}">{escape(THEME_GROUP_LABELS[group])}</th></tr>')
        for t in themes:
            cat = data["category"]["themes"][t]
            if not cat["mentions"]:
                continue
            cells = []
            for b in brands:
                s = data["overall"][b]
                share, count = s["theme_shares"].get(t, 0), s["theme_counts"].get(t, 0)
                if not count:
                    cells.append('<td class="hc empty">–</td>')
                    continue
                lines = [f"<b>{escape(BRAND_NAMES[b])} · {escape(THEME_LABEL[t])}</b>",
                         f"{count} of {s['n']} reviews ({pct(share)})"]
                ev = data["evidence"][b].get(t)
                if ev:
                    lines.append(f"“{escape(ev['quote_en'])}”")
                lines.append("Click to read all quotes")
                var, light = next((v, lt) for limit, v, lt in HEAT_STEPS if share <= limit)
                cells.append(f'<td class="hc{" on-dark" if light else ""}" style="background:var({var})"'
                             f'{ev_attrs(b, t)} data-tip="{tip(*lines)}">{pct(share)}<small>{count}</small></td>')
            imp = cat["impact"]
            cells.append(f'<td class="mk">{pct(cat["category_share"])}<small>{signed(imp) + "★" if imp is not None else ""}</small></td>')
            body.append(f'<tr><th scope="row">{escape(THEME_LABEL[t])}</th>{"".join(cells)}</tr>')
    scale = '<div class="scale"><span>Share of reviews:</span>' + "".join(
        f'<i style="background:var({v})"></i>' for _, v, _ in HEAT_STEPS) + '<span>more</span></div>'
    return (f'<div class="tablewrap"><table class="heat"><thead><tr><th></th>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>{scale}')


STAR_VARS = {"5": "--s5", "4": "--s4", "3": "--s3", "2": "--s2", "1": "--s1"}


def star_bar(dist):
    """100% stacked bar of the star distribution, 5 stars on the left."""
    if not dist:
        return '<div class="muted small">Star distribution not captured</div>'
    segs = "".join(f'<span style="width:{dist[k]:.1f}%;background:var({STAR_VARS[k]})"></span>'
                   for k in "54321" if dist.get(k))
    return f'<div class="stackbar" aria-hidden="true">{segs}</div>'


def meter(share, market, kind, vmax=1.0):
    """One horizontal bar (problem = red, going well = green) with a tick for the market average."""
    color = "--neg" if kind == "bad" else "--pos"
    w = min(100, (share or 0) / vmax * 100)
    m = "" if market is None else f'<i class="mtick" style="left:{min(100, market / vmax * 100):.1f}%"></i>'
    return f'<div class="meter"><span style="width:{w:.1f}%;background:var({color})"></span>{m}</div>'


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
def public_ratings(data):
    """What customers see on Trustpilot, next to the plain averages from this analysis."""
    if not data["profiles"]:
        return ""
    rows = []
    for i, b in enumerate([data["focus"]] + data["competitors"]):
        p = data["profiles"].get(b)
        if not p:
            continue
        m, o, r = p["main"], data["overall"][b], data["recent"][b]
        d = m["stars_pct"]
        gap = (r["avg_rating"] - m["trust_score"]) if r["avg_rating"] is not None else None
        trend = ""
        if gap is not None:
            cls = "bad" if gap <= -0.5 else ("good" if gap >= 0.3 else "flat")
            arrow = "▼ " if gap <= -0.5 else ("▲ " if gap >= 0.3 else "")
            gap_txt = "on par" if abs(gap) < 0.05 else signed(gap)
            trend = f'<span class="delta {cls}">{arrow}{stars(r["avg_rating"])}★ last 12 weeks ({gap_txt})</span>'
        others = ", ".join(f'{escape(x["domain"])} {stars(x["trust_score"])} ({x["total_reviews"]})'
                           for x in p["pages"] if x is not m)
        lines = [f'<b>{escape(BRAND_NAMES[b])} · {escape(m["domain"])}</b>']
        if d:
            lines.append(" · ".join(f"{k}★ {d[k]:.0f}%" for k in "54321"))
        lines.append(f'6-month average of European reviews: {stars(o["avg_rating"])}★ ({o["n"]} reviews)')
        if others:
            lines.append(f"Other pages: {escape(others)}")
        dist = (f'{star_bar(d)}<div class="pdl"><span>5★ {d["5"]:.0f}%</span><span>1★ {d["1"]:.0f}%</span></div>'
                if d else star_bar(None))
        rows.append(f"""<div class="prow{' focusrow' if b == data['focus'] else ''}" tabindex="0" data-tip="{tip(*lines)}">
          <div class="pname"><i class="swatch" style="background:var({BRAND_COLOR_SLOTS[i]})"></i><div><b>{escape(short_brand(b))}</b><span class="muted small">{escape(m["domain"])}</span></div></div>
          <div class="pscore"><b>{stars(m["trust_score"])}</b><span class="muted small">{escape(m["label"])} · {m["total_reviews"]:,} reviews</span></div>
          <div class="pdist">{dist}</div>
          <div class="ptrend">{trend}</div>
        </div>""")
    cap = next(iter(data["profiles"].values()))["captured_on"]
    legend_items = "".join(f'<span><i style="background:var({STAR_VARS[k]})"></i>{k}★</span>' for k in "54321")
    return f"""<h2>Public rating: what customers see</h2>
    <p class="sub">TrustScore and all-time star distribution from each brand's main Trustpilot page (distribution snapshot {escape(cap)}),
    next to the plain average of the last 12 weeks of European reviews. Trustpilot weights recent reviews more, so a recent average
    well below the TrustScore means the public score is under pressure.</p>
    <div class="card"><div class="legend">{legend_items}</div><div class="plist">{"".join(rows)}</div></div>"""


def journey_strip(data):
    """Compact journey on the overview: one chip per stage, red/green bars for the focus brand."""
    f = data["focus"]
    items = []
    for st in data["journey"]:
        b = st["brands"][f]
        lines = [f"<b>{escape(st['name'])}</b>",
                 f"{short_brand(f)}: {pct(b['problem_share'])} of reviews report a problem here (market {pct(st['market']['problem_share'])})",
                 (f"{pct(b['delight_share'])} praise it (market {pct(st['market']['delight_share'])})"
                  if b['delight_share'] is not None else "No positive theme at this stage"),
                 "Click to open the journey"]
        items.append(f"""<a class="jstep" href="#journey" data-stage-link="{st['key']}" data-tip="{tip(*lines)}">
          {icon(st['key'], 34)}<b>{escape(st['name'])}</b>
          <span class="jm bad">▼ {pct(b['problem_share'])}</span>{f'<span class="jm good">▲ {pct(b["delight_share"])}</span>' if b['delight_share'] is not None else '<span class="jm muted">no praise theme</span>'}</a>""")
    return f"""<div class="jstrip">{''.join(items)}</div>
    <p class="muted small">▼ share of {escape(short_brand(f))} reviews reporting a problem at this stage · ▲ share praising it. Last 6 months.</p>"""


def tab_overview(data, s):
    f = data["focus"]
    name = short_brand(f)
    o, r, br = data["overall"][f], data["recent"][f], data["category"]["bridge"]
    comp_rating = sum(data["overall"][b]["avg_rating"] for b in data["competitors"]) / len(data["competitors"])
    prof = data["profiles"].get(f, {}).get("main")
    prog = data["programme"].get(f, {})
    comp_inv = [data["programme"][b]["invited_share"] for b in data["competitors"] if b in data["programme"]]
    comp_ts = ", ".join(f'{short_brand(b)} {stars(data["profiles"][b]["main"]["trust_score"])}'
                        for b in data["competitors"] if b in data["profiles"])
    tiles = []
    if prof:
        tiles.append(tile(f"{name} TrustScore, what customers see", f'{stars(prof["trust_score"])}<small>/5</small>',
                          f'“{escape(prof["label"])}” · {prof["total_reviews"]:,} reviews · {comp_ts}', "accent"))
    tiles += [
        tile("Average of new reviews, last 6 months", f'{stars(o["avg_rating"])}<small>★</small>',
             f'{o["n"]} European reviews · last 12 weeks {stars(r["avg_rating"])}★ · competitors {stars(comp_rating)}★', "bad"),
        tile("Reviews that report a problem", pct(o["problem_share"]),
             f'Competitors {pct(br.get("comp_problem_share"))}', "bad"),
        tile(f"{name} reviews when nothing went wrong", f'{stars(br.get("focus_rating_without_problem"))}<small>★</small>',
             "Customers like the product itself", "good"),
    ]
    if prog:
        tiles.append(tile("Reviews written after an invitation", pct(prog["invited_share"]),
                          f'Invited reviews average {stars(prog["invited_rating"])}★, self-started {stars(prog["organic_rating"])}★'
                          + (f' · competitors up to {pct(max(comp_inv))}' if comp_inv else "")))
    cards = []
    for i, ins in enumerate(s["executive_insights"], 1):
        cards.append(f"""<article class="insight">
          <div class="num">{i}</div>
          <h3>{escape(ins["title"])}</h3>
          <p class="evidence">{escape(ins["evidence"])}</p>
          <p><span class="lbl">So what</span>{escape(ins["so_what"])}</p>
          <p class="action"><span class="lbl">Do</span>{escape(ins["action"])}</p>
        </article>""")
    lanes = []
    for h, title in [("0-30 days", "Now · 0–30 days"), ("30-90 days", "Next · 30–90 days"), ("90+ days", "Later · 90+ days")]:
        recs = [x for x in s["recommendations"] if x["horizon"] == h]
        if not recs:
            continue
        items = "".join(f"""<div class="rec">
            <b>{escape(x["action"])}</b>
            <div class="rmeta"><span class="tag imp-{x["impact"]}">Impact {x["impact"]}</span><span class="tag">Effort {x["effort"]}</span></div>
            <p>{escape(x["why"])}</p>
            <p class="muted small"><b>Owner</b> {escape(x["owner"])} · <b>KPI</b> {escape(x["kpi"])}</p>
          </div>""" for x in recs)
        lanes.append(f'<div class="lane"><h3>{title}</h3>{items}</div>')
    return f"""
    <section class="hero">
      <div class="hero-text">
        <p class="kicker">Walking pad review intelligence · Europe incl. UK</p>
        <p class="headline">{escape(s["headline"])}</p>
        <p class="sub">An AI agent reads every public Trustpilot review of {escape(name)} and its competitors, tags what each customer
        talks about, and turns it into the numbers below. Refreshed every two days.</p>
      </div>
      {HERO}
    </section>
    <div class="tiles">{"".join(tiles)}</div>
    <h2>The customer journey at a glance</h2>
    {journey_strip(data)}
    <h2>Three things to know</h2>
    <div class="insights">{"".join(cards)}</div>
    {message_plan(data)}
    {public_ratings(data)}
    <h2>Action roadmap</h2>
    <p class="sub">Ordered by priority within each horizon. Each action is tied to a finding and a KPI this report can track.</p>
    <div class="lanes">{"".join(lanes)}</div>
    <div class="card watch"><h3>Watch in the coming weeks</h3>{bullet_list(s["watch_next"])}</div>"""


def message_plan(data):
    """The post-purchase message plan: one touchpoint per journey moment, each tied to what reviews say."""
    f = data["focus"]
    name = short_brand(f)
    th = {t["theme"]: t for st in data["journey"] for t in st["themes"]}
    v = {x["theme"]: x for x in data["vault"]}
    p = data["programme"].get(f, {})
    def sh(t, k="focus_share"):
        return pct(th[t][k]) if t in th else "n/a"
    chase = next((c["share"] for c in v.get("customer_service", {}).get("co_occurs", []) if c["theme"] == "delivery_delay"), None)
    steps = [
        ("order", "Order placed", "Honest delivery date, and a clear note when it is a pre-order",
         f"{sh('preorder_communication')} of {name} reviews mention unclear pre-order dates (market {sh('preorder_communication','market_share')})", "bad"),
        ("order", "While waiting", "A short status update on a fixed rhythm, also when nothing has changed",
         f"{sh('delivery_delay')} mention a late delivery; {pct(chase)} of service complaints come with one" if chase else
         f"{sh('delivery_delay')} mention a late delivery", "bad"),
        ("delivery", "Dispatched", "Tracking link and delivery window",
         f"{sh('damaged_in_transit')} mention damage in transit (market {sh('damaged_in_transit','market_share')})", "neutral"),
        ("setup", "Delivered", "Set-up video and first-walk tips",
         f"Only {sh('assembly_setup')} mention set-up trouble: the product side works", "good"),
        ("use", "After 1–2 weeks of use", "Review invitation, sent to every customer",
         f"Invited reviews average {stars(p.get('invited_rating'))}★ vs {stars(p.get('organic_rating'))}★ self-started, "
         f"but only {pct(p.get('invited_share'))} are invited", "key"),
        ("after", "If something goes wrong", "Choice to wait or cancel, and a stated refund timeline",
         f"{sh('returns_refunds')} mention refunds (market {sh('returns_refunds','market_share')})", "bad"),
    ]
    cells = "".join(f"""<li class="mp-step mp-{kind}">
        <div class="mp-icon">{icon(ic, 30)}</div>
        <p class="mp-when">{escape(when)}</p>
        <p class="mp-msg">{escape(msg)}</p>
        <p class="mp-sig">{'▲ ' if kind == 'good' else ('★ ' if kind == 'key' else ('▼ ' if kind == 'bad' else ''))}{escape(sig)}</p>
      </li>""" for ic, when, msg, sig, kind in steps)
    return f"""
    <h2>Where to step in: a post-purchase message plan</h2>
    <p class="sub">Most of {escape(name)}'s low reviews are written while the customer is waiting, and only a few are invited.
    The two fixes belong together: keep people informed during the wait, and ask for the review once they have used the walking pad.</p>
    <ol class="mplan">{cells}</ol>
    <p class="muted small">Each signal is from the last 6 months of public reviews. Invited reviewers may differ from self-started ones, so the
    gap between them is a signal, not a promise; the timing of the invitation (for example day 7 vs day 14 after delivery) is worth testing.
    Trustpilot rules require invitations to go to all customers, not only happy ones.</p>"""


def stage_quotes(data, st, b):
    """One red and one green quote for a stage, when there is one."""
    out = []
    pains = [t["theme"] for t in st["themes"] if t["group"] == "pain_point"]
    goods = [t["theme"] for t in st["themes"] if t["group"] == "delight"]
    for themes, cls in ((pains, "bad"), (goods, "good")):
        best = None
        for t in themes:
            e = data["evidence"][b].get(t)
            if e and (best is None or e["date"] > best[1]["date"]):
                best = (t, e)
        if best:
            t, e = best
            out.append(f'<blockquote class="sq {cls}"{ev_attrs(brand=b, theme=t)}>“{escape(e["quote_en"])}”'
                       f'<span>{e["rating"]}★ · {escape(THEME_SHORT[t])}</span></blockquote>')
    return "".join(out)


def tab_journey(data, s):
    f = data["focus"]
    name = short_brand(f)
    texts = {j["stage"]: j for j in s["journey"]}
    # One scale for every bar on the page, so stages can be compared.
    top = max([t["focus_share"] or 0 for st in data["journey"] for t in st["themes"]] +
              [t["market_share"] or 0 for st in data["journey"] for t in st["themes"]] + [0.1])
    vmax = min(1.0, (int(top * 10) + 1) / 10)
    stages = []
    for i, st in enumerate(data["journey"], 1):
        b = st["brands"][f]
        tx = texts.get(st["name"], {})
        rows = []
        for t in st["themes"]:
            bad = t["group"] == "pain_point"
            lines = [f"<b>{escape(THEME_LABEL[t['theme']])}</b>",
                     f"{name}: {pct(t['focus_share'])} of reviews · competitor average {pct(t['market_share'])}",
                     "Click to read the quotes"]
            rows.append(f"""<div class="trow"{ev_attrs(brand=f, theme=t['theme'])} data-tip="{tip(*lines)}">
              <span class="tname"><i class="{'bad' if bad else 'good'}">{'▼' if bad else '▲'}</i>{escape(THEME_LABEL[t['theme']])}</span>
              {meter(t['focus_share'], t['market_share'], 'bad' if bad else 'good', vmax)}
              <span class="tval2">{pct(t['focus_share'])}<small>vs {pct(t['market_share'])}</small></span></div>""")
        praise = ("" if b["delight_share"] is None else
                  f'<span class="pill good" title="Share of {escape(name)} reviews that praise this stage">▲ {pct(b["delight_share"])} praise'
                  f'<small>market {pct(st["market"]["delight_share"])}</small></span>')
        impact = (f'<span class="cost">A problem here costs <b>{signed(st["impact"])}★</b> on average</span>'
                  if st["impact"] is not None else "")
        stages.append(f"""<article class="stage" id="stage-{st['key']}">
          <div class="stage-head">
            <div class="stage-num">{i}</div>{icon(st['key'], 44)}
            <div><h3>{escape(st['name'])}</h3>{impact}</div>
            <div class="stage-kpis">
              <span class="pill bad" title="Share of {escape(name)} reviews that report a problem at this stage">▼ {pct(b['problem_share'])} problem<small>market {pct(st['market']['problem_share'])}</small></span>
              {praise}
            </div>
          </div>
          <div class="stage-body">
            <div class="stage-text">
              <p><span class="lbl">All brands</span>{escape(tx.get('market', ''))}</p>
              <p><span class="lbl">{escape(name)}</span>{escape(tx.get('focus_brand', ''))}</p>
              <p class="sowhat"><span class="lbl">So what</span>{escape(tx.get('so_what', ''))}</p>
            </div>
            <div class="stage-data">
              <div class="trows">{''.join(rows)}</div>
              <div class="squotes">{stage_quotes(data, st, f)}</div>
              <button class="linkbtn"{ev_attrs(brand=f, stage=st['key'])}>All {escape(name)} quotes for this stage →</button>
            </div>
          </div>
        </article>""")
    # Before the order: why people buy (all brands).
    drivers = sorted(THEMES["purchase_driver"], key=lambda t: -data["category"]["themes"][t]["category_share"])
    drv = "".join(f'<span class="tag"{ev_attrs(theme=t)}>{escape(THEME_SHORT[t])} '
                  f'<b>{pct(data["category"]["themes"][t]["category_share"])}</b></span>'
                  for t in drivers if data["category"]["themes"][t]["mentions"])
    return f"""
    <p class="lede">What walking pad buyers experience after they click order, stage by stage. Red is what goes wrong, green what
    goes right; the thin mark on each bar is the competitor average (bars run from 0 to {vmax * 100:.0f}% of reviews). Built from {data['n_reviews']:,} reviews over 6 months.</p>
    <div class="card before">{icon('before', 40)}<div><h3>Before the order: why people buy</h3>
      <p class="muted small">Share of all reviews (average of brands) that mention the reason. Click for quotes.</p><div>{drv}</div></div></div>
    <div class="path">{''.join(stages)}</div>
    <p class="muted small">Shares are of all of the brand's reviews in the period. A review can mention several stages.
    “Costs” compares the average stars of reviews with a problem at this stage to reviews without one, within each brand.</p>"""


def tab_vault(data, s):
    f = data["focus"]
    name = short_brand(f)
    texts = {v["problem"]: v for v in s["vault"]}
    cards = []
    for i, v in enumerate(data["vault"], 1):
        tx = texts.get(THEME_LABEL[v["theme"]]) or (s["vault"][i - 1] if i - 1 < len(s["vault"]) else {})
        a, b = v["share_first_half"], v["share_second_half"]
        if a is None or b is None or abs(b - a) < 0.03:
            trend = '<span class="delta flat">● stable</span>'
        elif b > a:
            trend = f'<span class="delta bad">▲ rising {pct(a)} → {pct(b)}</span>'
        else:
            trend = f'<span class="delta good">▼ falling {pct(a)} → {pct(b)}</span>'
        e = data["evidence"][f].get(v["theme"])
        quote = (f'<blockquote class="sq bad"{ev_attrs(brand=f, theme=v["theme"])}>“{escape(e["quote_en"])}”'
                 f'<span>{e["rating"]}★ · {escape(e["date"])}</span></blockquote>') if e else ""
        co = ", ".join(f'{THEME_SHORT[c["theme"]]} {pct(c["share"])}' for c in v["co_occurs"] if c["share"] >= 0.1)
        cards.append(f"""<article class="vcard">
          <div class="vrank">#{i}</div>
          <div class="vmain">
            <h3>{escape(THEME_LABEL[v['theme']])}</h3>
            <div class="vtags"><span class="tag">{icon(v['stage'], 16)} {escape(STAGE_NAME[v['stage']])}</span>
              <span class="tag owner">Owner: {escape(v['owner'])}</span>{trend}</div>
            <div class="vnums">
              <div><b>{signed(-v['stars_lost'], 2)}★</b><span>pulls the 6-month average down by</span></div>
              <div><b>{pct(v['share'])}</b><span>of {escape(name)} reviews ({v['count']}) · market {pct(v['market_share'])}</span></div>
              <div><b>{pct(v['in_low_star'])}</b><span>of {escape(name)}'s 1–2★ reviews mention it</span></div>
              <div><b>{stars(v['rating_with'])}★</b><span>average when it comes up, vs {stars(v['rating_without'])}★ when not</span></div>
            </div>
            <div class="vtext">
              <p><span class="lbl">Reviews suggest the cause</span>{escape(tx.get('what_reviews_suggest_is_the_cause', ''))}</p>
              <p><span class="lbl">Remove the cause</span>{escape(tx.get('fix_the_cause', ''))}</p>
              <p><span class="lbl">Solved when</span>{escape(tx.get('kpi', ''))}</p>
            </div>
            {f'<p class="muted small">Often together with: {escape(co)}</p>' if co else ''}
            {quote}
          </div>
        </article>""")
    br = data["category"]["bridge"]
    bridge_note = ""
    if br["potential"] is not None:
        bridge_note = (f'{pct(br["focus_problem_share"])} of {name} reviews report a problem (competitors '
                       f'{pct(br["comp_problem_share"])}). Those reviews average {stars(br["focus_rating_with_problem"])}★, '
                       f'the others {stars(br["focus_rating_without_problem"])}★. With the competitors\' problem rate, the '
                       f'6-month average would be about {stars(br["potential"])}★. An estimate to size the opportunity, not a forecast.')
    return f"""
    <p class="lede">A prototype of a <b>Customer Problem Vault</b>, fed only by public reviews: {escape(name)}'s five problems that cost
    the most stars, each with its stage, a suggested owner, and the cause to remove. Solved means the cause is gone, not that the
    ticket is closed. In daily use the same vault would also take tickets, returns, defects and surveys.</p>
    <div class="vault">{''.join(cards)}</div>
    <h2>What fixing the causes is worth</h2>
    <div class="card"><p class="sub">{escape(bridge_note)}</p>{rating_bridge(data)}</div>
    <p class="muted small">Ranking: share of reviews with the problem × the star gap between reviews with and without it.
    Owners are roles in a small DTC team, a suggestion only. Rising/falling compares the first and last 3 months.</p>"""


def countries(data):
    f = data["focus"]
    rows = []
    for m in data["markets"]:
        tops = ", ".join(f'{THEME_SHORT[t["theme"]]} {pct(t["share"])}' for t in m["top_problems"])
        cells = []
        for st in JOURNEY:
            v = m["stages"][st["key"]]
            a = min(0.85, v * 1.6) if v else 0
            t = tip("<b>" + escape(m["name"]) + " · " + escape(st["name"]) + "</b>",
                    pct(v) + " of reviews report a problem here")
            cells.append(f'<td class="sc" style="background:color-mix(in srgb, var(--neg) {a * 100:.0f}%, transparent)" '
                         f'data-tip="{t}">{pct(v)}</td>')
        rows.append(f"""<tr class="{'few' if m['few'] else ''}"><th scope="row">{escape(m['name'])}
            {'<small class="muted">few reviews</small>' if m['few'] else ''}</th>
          <td class="num">{m['n']}</td><td class="num"><b>{stars(m['avg_rating'], 2)}★</b></td>
          <td class="num">{pct(m['problem_share'])}</td>{''.join(cells)}
          <td class="num muted">{stars(m['competitor_rating'], 2) + '★' if m['competitor_rating'] else '–'}<small> ({m['competitor_n']})</small></td></tr>""")
    heads = "".join(f'<th class="sc" title="{escape(s["name"])}">{icon(s["key"], 22)}<span>{escape(s["name"])}</span></th>' for s in JOURNEY)
    return f"""<div class="tablewrap"><table class="plain countries">
      <thead><tr><th>Country</th><th class="num">Reviews</th><th class="num">Average</th><th class="num">Problem</th>{heads}
      <th class="num">Competitors there</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
      <p class="muted small">Country = what the reviewer set on Trustpilot. Stage columns: share of {escape(short_brand(f))}'s reviews from that country
      reporting a problem at that stage (darker = more). Last column: average of competitor reviews from the same country, with their count.</p>"""


def programme(data, s):
    brands = [data["focus"]] + data["competitors"]
    rows = []
    for i, b in enumerate(brands):
        p = data["programme"].get(b)
        if not p:
            continue
        lines = [f"<b>{escape(BRAND_NAMES[b])}</b>",
                 f"{p['invited_n']} invited, {p['organic_n']} self-started reviews",
                 f"Invited average {stars(p['invited_rating'])}★, self-started {stars(p['organic_rating'])}★",
                 f"1–2★ share: invited {pct(p['invited_low_share'])}, self-started {pct(p['organic_low_share'])}",
                 f"Replied publicly to {pct(p['negative_replied_share'])} of {p['negative_n']} 1–2★ reviews"
                 + (f", median {p['negative_reply_median_days']} day(s)" if p['negative_reply_median_days'] is not None else "")]
        rows.append(f"""<div class="prog" tabindex="0" data-tip="{tip(*lines)}">
          <div class="pname"><i class="swatch" style="background:var({BRAND_COLOR_SLOTS[i]})"></i><b>{escape(short_brand(b))}</b></div>
          <div class="ptrack"><span class="inv" style="width:{p['invited_share'] * 100:.1f}%"></span><span class="org" style="width:{(1 - p['invited_share']) * 100:.1f}%"></span></div>
          <div class="pnums"><span>{pct(p['invited_share'])} invited</span>
            <span>{stars(p['invited_rating'])}★ vs {stars(p['organic_rating'])}★</span>
            <span>{pct(p['negative_replied_share'])} of 1–2★ answered{f", ~{p['negative_reply_median_days']}d" if p['negative_reply_median_days'] is not None else ""}</span></div>
        </div>""")
    rp = s["review_programme"]
    return f"""<div class="two">
      <div class="card"><h3>Invited vs self-started reviews</h3>
        {legend([("Invited by the company", "--inv"), ("Written on own initiative", "--org")])}
        <div class="progs">{''.join(rows)}</div>
        <p class="muted small">Columns: invited share · average stars invited vs self-started · share of 1–2★ reviews with a public reply, median days to reply.
        “Invited” = Trustpilot source other than organic (e.g. Shopify, review link). Hover for detail.</p></div>
      <div class="card"><h3>What it means</h3><p>{escape(rp['finding'])}</p>
        <p><span class="lbl">So what</span>{escape(rp['so_what'])}</p>
        <p class="muted small">Trustpilot requires invitations to go to all customers, not only happy ones. The aim is a fair picture, which
        today is skewed to those who had a problem.</p></div>
    </div>"""


def trends(data):
    f = data["focus"]
    months, labels = data["months"], data["month_labels"]
    counts = [data["monthly"][f][m]["n"] for m in months]
    ts = (data["profiles"].get(f) or {}).get("main")
    rating = line_chart(
        [{"name": short_brand(f), "color": "--series-1", "counts": counts,
          "values": [data["monthly"][f][m]["avg_rating"] for m in months]},
         {"name": "Competitors", "color": "--series-comp", "values": data["comp_monthly_rating"]}],
        labels, 1, 5, [1, 2, 3, 4, 5], lambda v: f"{v:.1f}",
        f"Average star rating of new reviews per month, {BRAND_NAMES[f]} vs competitor average",
        ref=(ts["trust_score"], f"TrustScore {stars(ts['trust_score'])}") if ts else None)
    prob = line_chart(
        [{"name": short_brand(f), "color": "--series-1", "counts": counts,
          "values": [data["monthly"][f][m]["problem_share"] for m in months]},
         {"name": "Competitors", "color": "--series-comp",
          "values": [(lambda v: round(sum(v) / len(v), 3) if v else None)(
              [data["monthly"][b][m]["problem_share"] for b in data["competitors"] if data["monthly"][b][m]["problem_share"] is not None])
              for m in months]}],
        labels, 0, 1, [0, 0.25, 0.5, 0.75, 1], lambda v: f"{v * 100:.0f}%",
        f"Share of reviews reporting a problem per month, {BRAND_NAMES[f]} vs competitor average")
    rows = "".join(
        f"<tr><td>{escape(ml)}</td><td class='num'>{data['monthly'][f][m]['n']}</td>"
        f"<td class='num'>{stars(data['monthly'][f][m]['avg_rating'], 2)}</td><td class='num'>{stars(data['comp_monthly_rating'][i], 2)}</td>"
        f"<td class='num'>{pct(data['monthly'][f][m]['problem_share'])}</td></tr>"
        for i, (m, ml) in enumerate(zip(months, labels)))
    return f"""<h2>Month by month</h2>
      <p class="sub">{short_brand(f)} gets {min(counts)}–{max(counts)} European reviews a month: read the direction, not single points. Hover for counts.</p>
      <div class="two">
        <div class="card"><h3>Average stars of the month's new reviews</h3>{legend([(short_brand(f), "--series-1"), ("Competitor average", "--series-comp")])}{rating}
          <p class="muted small">Not the TrustScore (dashed line): this is the plain average of each month's new reviews.</p></div>
        <div class="card"><h3>Share of reviews reporting a problem</h3>{legend([(short_brand(f), "--series-1"), ("Competitor average", "--series-comp")])}{prob}</div>
      </div>
      <details><summary>Show as table</summary><div class="tablewrap"><table class="plain">
        <thead><tr><th>Month</th><th class="num">Reviews</th><th class="num">{escape(short_brand(f))}</th><th class="num">Competitors</th><th class="num">Problem share</th></tr></thead>
        <tbody>{rows}</tbody></table></div></details>"""


def tab_focus(data, s):
    fb = s["focus_brand"]
    f = data["focus"]
    mk = s["markets"]
    return f"""
    <p class="lede">{escape(fb["summary"])}</p>
    <div class="two">
      <div class="card"><h3>Findings</h3>{findings_list(fb["findings"])}</div>
      <div class="card">
        <h3>Stronger than the market</h3>{bullet_list(fb["strengths_vs_market"], "good-list")}
        <h3>Weaker than the market</h3>{bullet_list(fb["weaknesses_vs_market"], "bad-list")}
      </div>
    </div>
    <h2>By country</h2>
    <p class="sub">{escape(mk["summary"])}</p>
    <div class="card">{countries(data)}{findings_list(mk["findings"])}</div>
    <h2>Review programme and replies</h2>
    {programme(data, s)}
    {trends(data)}
    <h2>{escape(short_brand(f))} vs competitors, whole period</h2>
    <p class="sub">Share of reviews mentioning each theme. Click a row for the quotes.</p>
    <div class="two">
      <div class="card"><h3>▼ Problems</h3>{compare_bars(data, "pain_point")}</div>
      <div class="card"><h3>▲ Going well</h3>{compare_bars(data, "delight")}</div>
    </div>"""


def tab_category(data, s):
    cat = data["category"]
    m = s["market"]
    ls = cat["low_star"]
    f = data["focus"]
    low_rows = []
    themes = sorted(set(ls["focus"]["shares"]) | set(ls["competitors"]["shares"]),
                    key=lambda t: -max(ls["focus"]["shares"].get(t, 0), ls["competitors"]["shares"].get(t, 0)))[:6]
    for t in themes:
        a, b = ls["focus"]["shares"].get(t, 0), ls["competitors"]["shares"].get(t, 0)
        low_rows.append((THEME_LABEL[t], a, b, [f"<b>{escape(THEME_LABEL[t])}</b>",
                                                f"In {pct(a)} of {BRAND_NAMES[f]}'s 1–2★ reviews ({ls['focus']['n']} reviews)",
                                                f"In {pct(b)} of competitors' 1–2★ reviews ({ls['competitors']['n']} reviews)"],
                         {"theme": t, "low": True}))
    table = "".join(
        f'<tr{ev_attrs(theme=r["theme"])}><td>{escape(THEME_LABEL[r["theme"]])}</td><td>{GROUP_SHORT[r["group"]]}</td>'
        f'<td class="num">{pct(r["category_share"])}</td><td class="num">{r["mentions"]}</td>'
        f'<td class="num">{signed(r["impact"])}</td><td>{r["quadrant"]}</td></tr>'
        for r in sorted(cat["themes"].values(), key=lambda r: -r["category_share"]) if r["mentions"])
    profiles = {p["brand"]: p for p in s["brand_profiles"]}
    cards = []
    for i, b in enumerate([data["focus"]] + data["competitors"]):
        o = data["overall"][b]
        p = profiles.get(BRAND_NAMES[b]) or profiles.get(short_brand(b)) or {}
        cs = (data["profiles"].get(b) or {}).get("main")
        sig = cat["signatures"][b]
        loved = chips((THEME_SHORT[x["theme"]] for x in sig["loved_for"]), "good") or '<span class="muted small">nothing stands out</span>'
        crit = chips((THEME_SHORT[x["theme"]] for x in sig["criticised_for"]), "bad") or '<span class="muted small">no problem stands out</span>'
        note = ('<p class="muted small">Broad home-fitness shop; its page covers all products.</p>' if b == "sportstech" else "")
        cards.append(f"""<article class="brand" style="--brand:var({BRAND_COLOR_SLOTS[i]})">
          <h3>{escape(BRAND_NAMES[b])}</h3>{note}
          <div class="kpis"><div><b>{stars(cs["trust_score"]) if cs else "–"}</b><span>TrustScore (public)</span></div>
            <div><b>{f'{cs["total_reviews"]:,}' if cs else "–"}</b><span>reviews, all-time</span></div>
            <div><b>{stars(o["avg_rating"])}★</b><span>6-month average</span></div>
            <div><b>{pct(o["problem_share"])}</b><span>report a problem</span></div></div>
          {star_bar(cs["stars_pct"]) if cs else ""}
          <p class="pos">{escape(p.get("positioning", ""))}</p>
          <p><span class="lbl">Loved for</span>{loved}</p>
          <p><span class="lbl">Criticised for</span>{crit}</p>
          <p class="lesson"><span class="lbl">Lesson for {escape(short_brand(f))}</span>{escape(p.get("lesson_for_focus_brand", ""))}</p>
          <button class="linkbtn"{ev_attrs(brand=b)}>Read {escape(short_brand(b))} quotes →</button>
        </article>""")
    small = ", ".join(f"{BRAND_NAMES[b]} ({n})" for b, n in data["small_brands"].items())
    return f"""
    {competitors.section(data, s.get("_competitors"), BRAND_COLOR_SLOTS, short_brand, ev_attrs, pct)}
    <h2>The category as a whole</h2>
    <p class="lede">{escape(m["summary"])}</p>
    <div class="two">
      <div class="card"><h3>Category findings</h3>{findings_list(m["findings"])}</div>
      <div class="card">
        <h3>Table stakes <span class="muted small">· expected; missing them is punished</span></h3>{bullet_list(m["table_stakes"])}
        <h3>Differentiators <span class="muted small">· win stars when present</span></h3>{bullet_list(m["differentiators"])}
      </div>
    </div>
    <h2>What actually moves the star rating</h2>
    <p class="sub">Each mark is a theme. Right = more common across brands, down = lowers the rating. The shaded corner is what
    to fix first. Effect on rating compares reviews with and without the theme within the same brand. Click a mark to read the quotes.</p>
    <div class="card">
      {legend([("▲ Raises the rating", "--pos"), ("▼ Lowers the rating", "--neg")])}
      <div class="scrollx">{priority_matrix(cat)}</div>
      <details><summary>Show as table</summary><div class="tablewrap"><table class="plain clickable">
        <thead><tr><th>Theme</th><th>Type</th><th class="num">Share (brands avg)</th><th class="num">Mentions</th><th class="num">Effect, stars</th><th>Quadrant</th></tr></thead>
        <tbody>{table}</tbody></table></div></details>
    </div>
    <h2>What is inside the 1–2 star reviews</h2>
    <p class="sub">Share of low-star reviews that mention each theme: what turns a customer into a detractor.</p>
    <div class="card">{pair_bars(low_rows, (short_brand(f), "--series-1"), ("Competitors", "--series-comp"))}</div>
    <h2>Brands</h2>
    <p class="sub">“Loved for” and “criticised for” are the themes where a brand stands out against the other brands (share of reviews, at least 3 mentions).</p>
    <div class="brands">{"".join(cards)}</div>
    {f'<p class="muted small">Too few European reviews in the period to compare: {escape(small)}.</p>' if small else ''}
    <h2>Brand × theme matrix</h2>
    <p class="sub">Share of each brand's reviews mentioning the theme (count below). Market column: average of brands, with the theme's effect on rating. Click a cell for the quotes.</p>
    <div class="card">{heat_matrix(data)}</div>"""


def tab_evidence(data):
    brands = [data["focus"]] + data["competitors"]
    b_opts = "".join(f'<option value="{b}">{escape(BRAND_NAMES[b])}</option>' for b in brands)
    s_opts = '<option value="before">Before the order</option>' + "".join(
        f'<option value="{st["key"]}">{escape(st["name"])}</option>' for st in JOURNEY)
    t_opts = "".join(
        f'<optgroup label="{escape(THEME_GROUP_LABELS[g])}">' +
        "".join(f'<option value="{t}">{escape(THEME_LABEL[t])}</option>' for t in ts
                if data["category"]["themes"][t]["mentions"]) + "</optgroup>"
        for g, ts in THEMES.items())
    langs = sorted({r["l"] for r in data["evidence_rows"]})
    l_opts = "".join(f'<option value="{l}">{escape(LANG_NAME.get(l, l))}</option>' for l in langs)
    return f"""
    <p class="sub">Every theme the AI tagged, with its evidence quote (max 15 words, translated to English; the original is shown for other
    languages). Use it to check any number in this report.</p>
    <div class="filters" role="search">
      <label>Brand<select id="f-brand"><option value="">All brands</option>{b_opts}</select></label>
      <label>Stage<select id="f-stage"><option value="">All stages</option>{s_opts}</select></label>
      <label>Theme<select id="f-theme"><option value="">All themes</option>{t_opts}</select></label>
      <label>Stars<select id="f-stars"><option value="">All</option><option value="low">1–2★</option><option value="mid">3★</option><option value="high">4–5★</option></select></label>
      <label>Language<select id="f-lang"><option value="">All</option>{l_opts}</select></label>
      <label class="grow">Search<input id="f-q" type="search" placeholder="e.g. refund, weeks, motor"></label>
      <button id="f-reset" class="linkbtn">Reset</button>
    </div>
    <p id="ev-count" class="muted" aria-live="polite"></p>
    <div id="ev-list" class="evlist"></div>
    <button id="ev-more" class="morebtn" hidden>Show more</button>"""


def agreement_note():
    """Quality check on real reviews (src/check_agreement.py)."""
    from config import DATA_DIR
    f = DATA_DIR / "agreement.json"
    if not f.exists():
        return ""
    a = json.load(open(f))
    pp = a["by_group"]["pain_point"]
    return (f"<li><b>Checking the AI on real reviews:</b> a stronger model ({escape(a['reference_model'])}) re-tagged "
            f"{a['reviews']} random reviews independently ({escape(a['checked_on'])}). The everyday model agreed on "
            f"{a['all_themes']['precision']:.0%} of its tags and found {a['all_themes']['recall']:.0%} of the stronger model's; "
            f"for problems, {pp['recall']:.0%}. Agreement with a stronger reader, not proof of truth: every number also "
            f"links to its quotes in the Evidence tab.</li>")


def tab_method(data):
    srcs = ", ".join(SOURCES.get(x, x) for x in data["sources"])
    langs = ", ".join(LANG_NAME.get(l, l) for l in data["languages"])
    small = ", ".join(f"{BRAND_NAMES[b]} ({n} reviews)" for b, n in data["small_brands"].items())
    monthly_n = [data["monthly"][data["focus"]][m]["n"] for m in data["months"]]
    return f"""
    <div class="card"><ul class="method">
      <li><b>Data:</b> {data["n_reviews"]:,} real public reviews, {data["date_from"]} to {data["date_to"]} (6 months). Sources: {escape(srcs)}.
        Languages: {langs}. Only reviewers who list a European country (incl. UK) are counted, so brands are compared on the same market.
        Competitor pages include their UK, French and German shops. No fictional data is used anywhere in this report.</li>
      <li><b>Brands:</b> {", ".join(escape(BRAND_NAMES[b]) for b in [data["focus"]] + data["competitors"])}. Sportstech is a broad home-fitness
        shop (its page covers bikes, rowers and walking pads); it is included as a delivery and service benchmark for Germany.
        {f"Left out, too few reviews to compare: {escape(small)}." if small else ""}</li>
      <li><b>Tagging:</b> {escape(", ".join(data["models"]))} tags each review with themes from a fixed list of
        {sum(len(g) for g in THEMES.values())} themes (why they buy, problems, what goes well), with a quote as evidence.
        A fixed list keeps months and brands comparable.</li>
      <li><b>Customer journey:</b> every problem and positive theme belongs to one stage after the order: {", ".join(escape(s["name"]) for s in JOURNEY)}.
        Stage problem share = reviews reporting at least one problem at that stage ÷ all of the brand's reviews.</li>
      <li><b>Problem Vault:</b> the focus brand's problems ranked by stars lost = share of reviews with the problem × the star gap between
        reviews with and without it. Causes and fixes are written by Claude from what the reviews say; they are hypotheses to check
        with internal data (tickets, returns, carrier data), not facts.</li>
      <li><b>Public rating:</b> the TrustScore, review count and all-time star distribution on each brand's main Trustpilot page; the rating
        customers see and the headline number. TrustScore and count refresh with every run; the star distribution is a dated snapshot.
        Trustpilot's TrustScore is not a plain average: it gives recent reviews more weight.</li>
      <li><b>Plain averages:</b> 6-month and 12-week averages of the reviews analysed here. They show where the public score is heading,
        not the score itself. {escape(BRAND_NAMES[data["focus"]])} gets {min(monthly_n)}–{max(monthly_n)} European reviews a month.</li>
      <li><b>Invited vs self-started:</b> from Trustpilot's review source. “Organic” = the customer came on their own; anything else
        (Shopify, review link, automatic invitations) = invited.</li>
      <li><b>Effect on rating:</b> average stars of reviews with the theme minus those without, compared within each brand and then
        averaged across brands. It shows association, not proven cause.</li>
      <li><b>Insights:</b> written by Claude Opus 5.5 from the aggregated numbers only (never full reviews), told to use only numbers in
        the data and not to guess about internal operations.</li>
      {agreement_note()}
      <li><b>Source coverage:</b> Trustpilot only, so this is mainly the company experience (delivery, service, refunds), less the product.
        Next sources: Amazon, Bol, Google and Reviews.io reviews, plus the brand's own tickets, returns and surveys.</li>
      <li><b>Data access:</b> reviews are collected through Apify. Trustpilot's terms do not allow automated collection; a production
        version should use Trustpilot's official API or a licensed data provider.</li>
      <li><b>Privacy:</b> only public review text is used; reviewer names and profiles are dropped at collection and never stored or shown.
        Only short quotes (max 15 words) are displayed.</li>
    </ul></div>"""


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
LIGHT = """
  --page:#faf4ee; --surface-1:#fffdfb; --surface-2:#f4ece4; --text-primary:#261e1b; --text-secondary:#5a4e48; --muted:#837569;
  --grid:#eadfd5; --axis:#cfc1b5; --border:rgba(38,30,27,0.11); --accent:#e0601f; --accent-soft:#fce3d5; --accent-ink:#a8410e;
  --series-1:#e0601f; --series-2:#2f6db5; --series-3:#b03f86; --series-4:#4a4a4a; --series-5:#8c7b6b; --series-comp:#a69c94;
  --pos:#3fb27f; --neg:#d2453b; --good:#1a7350; --bad:#b83228; --pos-soft:#dcf2e7; --neg-soft:#fbe3df; --q-bad:rgba(210,69,59,0.07);
  --s5:#2e9c6c; --s4:#a7dcc2; --s3:#ddd3ca; --s2:#f2b3ac; --s1:#d2453b;
  --seq-100:#e3ecf7; --seq-200:#c3d6ee; --seq-300:#91b4df; --seq-400:#5b8dcb; --seq-500:#2f6db5; --seq-600:#1d4f8c;
  --inv:#2e9c6c; --org:#d9cfc6; --skin:#f2c9a8; --hair:#3a2a24;"""
DARK = """
  --page:#171211; --surface-1:#211a18; --surface-2:#2b2321; --text-primary:#f5ece6; --text-secondary:#cdbfb6; --muted:#a29387;
  --grid:#342b28; --axis:#4a3f3b; --border:rgba(255,240,230,0.11); --accent:#f0773a; --accent-soft:#3d2418; --accent-ink:#f7a777;
  --series-1:#f0773a; --series-2:#5b93db; --series-3:#d46aae; --series-4:#bfb4a8; --series-5:#a8967f; --series-comp:#6e625c;
  --pos:#46c08e; --neg:#ee6a5c; --good:#6fd3a8; --bad:#f59a8f; --pos-soft:#173527; --neg-soft:#3e1c18; --q-bad:rgba(238,106,92,0.10);
  --s5:#46c08e; --s4:#1f6b4b; --s3:#4a403c; --s2:#8f3a32; --s1:#ee6a5c;
  --seq-100:#1a2a40; --seq-200:#1d3c63; --seq-300:#234f84; --seq-400:#2f6db5; --seq-500:#5b93db; --seq-600:#9cc0ec;
  --inv:#46c08e; --org:#4a403c; --skin:#d9a987; --hair:#1a1210;"""

CSS = """
:root{color-scheme:light;""" + LIGHT + """}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;""" + DARK + """}}
:root[data-theme="dark"]{color-scheme:dark;""" + DARK + """}
*{box-sizing:border-box}
html{scroll-padding-top:70px}
body{margin:0;background:var(--page);color:var(--text-primary);
  font:15.5px/1.55 "Source Sans 3",system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-text-size-adjust:100%}
h1,h2,.headline,.tval,.kpis b,.pscore b,.vnums b,.vrank,.stage h3{font-family:"Archivo",system-ui,sans-serif;font-weight:650;letter-spacing:-0.01em;text-wrap:balance}
h3{font-family:"Archivo",system-ui,sans-serif;font-weight:600}
.wrap{max-width:1160px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--page)}
header.top{padding:22px 0 0}
.brandline{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.logo{display:inline-flex;align-items:center;gap:8px;font-weight:700;letter-spacing:-.01em}
.logo i{width:26px;height:26px;border-radius:50%;background:var(--accent);display:inline-block;position:relative}
.logo i::after{content:"";position:absolute;left:6px;right:6px;bottom:7px;height:3px;border-radius:2px;background:var(--surface-1)}
header.top h1{font-size:30px;line-height:1.15;margin:10px 0 6px;letter-spacing:-0.015em}
.meta{display:flex;flex-wrap:wrap;gap:4px 14px;color:var(--text-secondary);font-size:13px;margin:0}
.meta b{color:var(--text-primary);font-weight:600}
.tabs{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--page);border-bottom:1px solid var(--border);margin-top:16px}
.tabs .wrap{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;padding-block:8px}
.tabs .wrap::-webkit-scrollbar{display:none}
.tabs button{appearance:none;background:none;border:1px solid transparent;border-radius:999px;color:var(--text-secondary);
  font:inherit;font-size:14px;font-weight:550;padding:7px 14px;cursor:pointer;white-space:nowrap}
.tabs button:hover{color:var(--text-primary);background:var(--surface-2)}
.tabs button[aria-selected="true"]{color:var(--surface-1);background:var(--text-primary)}
.tabs button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
main{padding-block:24px 64px}
[role="tabpanel"][hidden]{display:none}
h2{font-size:24px;margin:40px 0 8px;letter-spacing:-0.01em}
h3{font-size:15.5px;margin:0 0 10px}
.headline{font-size:27px;line-height:1.25;margin:6px 0 12px;letter-spacing:-0.01em}
.kicker{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--accent-ink);margin:0}
.lede{font-size:17px;line-height:1.55;margin:0 0 18px;max-width:880px}
.sub{color:var(--text-secondary);margin:0 0 14px;font-size:14px;max-width:880px}
.muted{color:var(--muted)} .small{font-size:13px}
.card{background:var(--surface-1);border:1px solid var(--border);border-radius:18px;padding:18px 20px;min-width:0}
.card h3+h3,.card ul+h3{margin-top:16px}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px;margin-bottom:16px}
.hero{display:grid;grid-template-columns:1.35fr 1fr;gap:20px;align-items:center;background:var(--surface-1);border:1px solid var(--border);
  border-radius:24px;padding:22px 26px;margin-bottom:16px;overflow:hidden}
.hero .sub{margin:0}
.hero-art{width:100%;max-width:360px;justify-self:end;height:auto}
.hero-art .shadow{fill:var(--surface-2)} .hero-art .pad{fill:var(--text-primary)} .hero-art .belt{stroke:var(--muted);stroke-width:2;stroke-dasharray:6 6}
.hero-art .desk{fill:var(--accent)} .hero-art .line{stroke:var(--text-primary);stroke-width:4;stroke-linecap:round}
.hero-art .screen{fill:var(--surface-2);stroke:var(--text-primary);stroke-width:3;stroke-linejoin:round}
.hero-art .skin{fill:var(--skin)} .hero-art .hair{fill:var(--hair)}
.hero-art .body{stroke:var(--accent);stroke-width:16;stroke-linecap:round;fill:none}
.hero-art .limb{stroke:var(--text-primary);stroke-width:6;stroke-linecap:round;fill:none}
.hero-art .shoe{stroke:var(--text-primary);stroke-width:7;stroke-linecap:round}
.hero-art .bubble rect,.hero-art .bubble path{stroke-width:0}
.hero-art .bubble.good rect,.hero-art .bubble.good path{fill:var(--pos-soft)} .hero-art .bubble.good text{fill:var(--good);font-size:14px;letter-spacing:1px}
.hero-art .bubble.bad rect,.hero-art .bubble.bad path{fill:var(--neg-soft)} .hero-art .bubble.bad text{fill:var(--bad);font-size:11.5px;font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:12px}
.tile{background:var(--surface-1);border:1px solid var(--border);border-radius:18px;padding:14px 16px;position:relative}
.tile::before{content:"";position:absolute;left:16px;top:0;width:28px;height:4px;border-radius:0 0 4px 4px;background:var(--axis)}
.tile.bad::before{background:var(--neg)} .tile.good::before{background:var(--pos)} .tile.accent::before{background:var(--accent)}
.tlabel{font-size:13px;color:var(--text-secondary);min-height:2.6em;padding-top:4px}
.tval{font-size:36px;line-height:1.1;margin:4px 0;font-variant-numeric:tabular-nums}
.tval small{font-size:18px;color:var(--muted);margin-left:2px}
.tnote{font-size:12.5px;color:var(--muted)}
.delta{font-size:12.5px;color:var(--text-secondary);font-weight:600}
.delta.good{color:var(--good)} .delta.bad{color:var(--bad)}
.jstrip{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;position:relative}
.jstep{display:flex;flex-direction:column;align-items:flex-start;gap:4px;background:var(--surface-1);border:1px solid var(--border);border-radius:16px;
  padding:12px;color:inherit;text-decoration:none;font-size:13px;position:relative}
.jstep:hover,.jstep:focus-visible{border-color:var(--text-primary);outline:none}
.jstep b{font-size:13.5px;line-height:1.25;min-height:2.5em}
.jm{font-size:13px;font-weight:650;font-variant-numeric:tabular-nums}
.jm.bad,.pill.bad,.tname i.bad{color:var(--bad)} .jm.good,.pill.good,.tname i.good{color:var(--good)}
.icon{fill:none;stroke:var(--text-primary);stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round;flex:none}
.icon .fill{fill:var(--accent);stroke:none} .icon .fill-soft{fill:var(--accent-soft)} .icon .ok{stroke:var(--pos);stroke-width:2.2}
.insights{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.insight{position:relative;background:var(--surface-1);border:1px solid var(--border);border-radius:18px;padding:18px 18px 16px 60px}
.insight .num{position:absolute;left:16px;top:16px;width:30px;height:30px;border-radius:50%;background:var(--accent);
  color:#fff;display:grid;place-items:center;font-weight:700;font-size:14px}
.insight h3{font-size:16px;line-height:1.35}
.insight p{margin:8px 0 0;font-size:14px}
.insight .evidence{color:var(--text-secondary)}
.insight .action{padding-top:8px;border-top:1px solid var(--border)}
.lbl{display:inline-block;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-right:8px}
.mplan{list-style:none;margin:8px 0 6px;padding:0;display:grid;grid-template-columns:repeat(6,1fr);gap:10px;counter-reset:mp}
.mp-step{background:var(--surface-1);border:1px solid var(--border);border-top:4px solid var(--axis);border-radius:14px;padding:12px;font-size:14px}
.mp-bad{border-top-color:var(--neg)}.mp-good{border-top-color:var(--pos)}
.mp-key{border-top-color:var(--pos);background:var(--pos-soft)}
.mp-icon svg{display:block}
.mp-when{margin:8px 0 2px;font-weight:700;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.mp-msg{margin:0 0 8px;font-weight:600}
.mp-sig{margin:0;color:var(--text-secondary);font-size:13px}
.mp-bad .mp-sig{color:var(--bad)}.mp-good .mp-sig,.mp-key .mp-sig{color:var(--good)}
@media (max-width:980px){.mplan{grid-template-columns:repeat(3,1fr)}}
@media (max-width:560px){.mplan{grid-template-columns:1fr}}
.lanes{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.lane{background:var(--surface-2);border-radius:18px;padding:14px}
.rec{background:var(--surface-1);border:1px solid var(--border);border-radius:14px;padding:12px 14px;margin-top:10px;font-size:14px}
.rec p{margin:6px 0 0;color:var(--text-secondary)}
.rmeta{margin-top:6px;display:flex;gap:6px;flex-wrap:wrap}
.tag{display:inline-flex;align-items:center;gap:4px;font-size:12px;padding:2px 9px;border-radius:999px;border:1px solid var(--border);
  color:var(--text-secondary);margin:2px 4px 2px 0;background:var(--surface-1)}
.tag.good{background:var(--pos-soft);border-color:transparent;color:var(--good)} .tag.bad{background:var(--neg-soft);border-color:transparent;color:var(--bad)}
.tag.imp-high{border-color:var(--accent);color:var(--accent-ink);font-weight:650}
.tag .icon{stroke-width:2}
.watch{margin-top:16px}
.findings{padding-left:18px;margin:0} .findings li{margin-bottom:8px}
.good-list,.bad-list{padding-left:0;margin:0;list-style:none} .good-list li,.bad-list li{margin-bottom:6px;padding-left:22px;position:relative}
.good-list li::before{content:"▲";position:absolute;left:0;color:var(--good);font-size:12px;top:2px}
.bad-list li::before{content:"▼";position:absolute;left:0;color:var(--bad);font-size:12px;top:2px}
.before{display:flex;gap:14px;align-items:flex-start;margin-bottom:16px}
.before h3{margin-bottom:2px}
.path{display:grid;gap:14px;position:relative}
.path::before{content:"";position:absolute;left:37px;top:20px;bottom:20px;width:3px;background:repeating-linear-gradient(var(--axis) 0 8px,transparent 8px 14px)}
.stage{position:relative;background:var(--surface-1);border:1px solid var(--border);border-radius:20px;padding:16px 18px}
.stage-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.stage-num{width:30px;height:30px;border-radius:50%;background:var(--text-primary);color:var(--surface-1);display:grid;place-items:center;font-weight:700;font-size:14px;flex:none}
.stage h3{font-size:21px;margin:0}
.cost{font-size:13px;color:var(--text-secondary)} .cost b{color:var(--bad)}
.stage-kpis{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap}
.pill{display:flex;flex-direction:column;font-weight:700;font-size:15px;padding:6px 12px;border-radius:12px;line-height:1.2;font-variant-numeric:tabular-nums}
.pill small{font-weight:500;font-size:11.5px;color:var(--muted)}
.pill.bad{background:var(--neg-soft)} .pill.good{background:var(--pos-soft)}
.stage-body{display:grid;grid-template-columns:1fr 1.1fr;gap:20px;margin-top:12px}
.stage-text p{margin:0 0 8px;font-size:14px}
.sowhat{padding-top:8px;border-top:1px solid var(--border)}
.trows{display:grid;gap:6px}
.trow{display:grid;grid-template-columns:minmax(150px,1.2fr) 1fr 74px;gap:10px;align-items:center;font-size:13px;border-radius:8px;padding:2px 4px;margin:0 -4px}
.tname{display:flex;gap:6px;align-items:baseline} .tname i{font-style:normal;font-size:11px}
.meter{position:relative;height:10px;background:var(--surface-2);border-radius:5px}
.meter span{display:block;height:100%;border-radius:5px;min-width:2px}
.mtick{position:absolute;top:-3px;width:2px;height:16px;background:var(--text-primary);border-radius:1px;transform:translateX(-1px)}
.tval2{text-align:right;font-variant-numeric:tabular-nums;font-weight:650} .tval2 small{display:block;font-weight:400;color:var(--muted);font-size:11px}
.squotes{display:grid;gap:6px;margin-top:10px}
.sq{margin:0;font-size:13.5px;padding:8px 12px;border-radius:12px;border-left:3px solid}
.sq span{display:block;font-size:11.5px;color:var(--muted);margin-top:2px}
.sq.bad{background:var(--neg-soft);border-color:var(--neg)} .sq.good{background:var(--pos-soft);border-color:var(--pos)}
.vault{display:grid;gap:14px}
.vcard{display:grid;grid-template-columns:64px 1fr;gap:6px;background:var(--surface-1);border:1px solid var(--border);border-radius:20px;padding:18px 20px 16px 12px}
.vrank{font-size:34px;color:var(--accent);text-align:center;line-height:1}
.vmain h3{font-size:19px;margin:0 0 6px}
.vtags{display:flex;flex-wrap:wrap;align-items:center;gap:4px 6px;margin-bottom:10px}
.tag.owner{background:var(--surface-2);border-color:transparent;color:var(--text-primary)}
.vnums{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px}
.vnums div{background:var(--surface-2);border-radius:12px;padding:8px 10px}
.vnums b{display:block;font-size:22px;font-variant-numeric:tabular-nums}
.vnums div:first-child{background:var(--neg-soft)} .vnums div:first-child b{color:var(--bad)}
.vnums span{font-size:12px;color:var(--text-secondary);line-height:1.3;display:block}
.vtext p{margin:0 0 6px;font-size:14px}
.vcard .sq{margin-top:8px}
.chart{width:100%;height:auto;display:block;overflow:visible}
.chart .grid{stroke:var(--grid);stroke-width:1}
.chart .axis{stroke:var(--axis);stroke-width:1} .chart .axis.strong{stroke:var(--muted)}
.chart .axis.dashed{stroke-dasharray:4 4}
.chart .refline{stroke:var(--text-secondary);stroke-width:1.2;stroke-dasharray:5 4}
.chart .reflabel{fill:var(--text-secondary);font-size:11px}
.chart .tick{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.chart .axislabel{fill:var(--text-secondary);font-size:12px}
.chart .qlabel{fill:var(--muted);font-size:11px;font-weight:700;letter-spacing:.05em}
.chart .dotlabel{fill:var(--text-primary);font-size:12px;pointer-events:none;paint-order:stroke;stroke:var(--surface-1);stroke-width:3px}
.chart .q-bad{fill:var(--q-bad)}
.chart .dot{cursor:pointer;outline:none}
.chart .dot:hover path,.chart .dot:focus path{stroke:var(--text-primary)}
.chart .endlabel{fill:var(--text-secondary);font-size:12px}
.chart .endval{fill:var(--text-primary);font-weight:600}
.chart .xh{stroke:var(--axis);stroke-width:1;opacity:0}
.chart .hit:hover .xh,.chart .hit:focus .xh{opacity:1}
.chart .hit{outline:none}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;color:var(--text-secondary);margin-bottom:8px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.bars{display:grid;gap:10px}
.brow{display:grid;grid-template-columns:minmax(120px,38%) 1fr;gap:10px;align-items:center;font-size:13px;border-radius:8px;padding:2px 4px;margin:0 -4px}
.blabel{color:var(--text-secondary)}
.btrack{display:grid;gap:2px}
.bar{display:flex;align-items:center;gap:6px;height:12px}
.bar span{display:block;height:10px;border-radius:0 4px 4px 0;min-width:2px}
.bar em{font-style:normal;font-size:12px;font-variant-numeric:tabular-nums;color:var(--text-primary)}
.bar em.muted{color:var(--muted)}
[data-ev]{cursor:pointer}
[data-ev]:hover,[data-ev]:focus-visible{background:var(--surface-2);outline:none}
.sq[data-ev]:hover,.sq[data-ev]:focus-visible{box-shadow:0 0 0 2px var(--text-primary)}
.sq.bad[data-ev]:hover{background:var(--neg-soft)} .sq.good[data-ev]:hover{background:var(--pos-soft)}
.heat [data-ev]:hover,.heat [data-ev]:focus-visible{background:inherit;box-shadow:0 0 0 2px var(--text-primary)}
.chart [data-ev]:hover,.chart [data-ev]:focus-visible{background:none}
.waterfall{display:grid;gap:6px;margin-top:6px}
.wrow{display:grid;grid-template-columns:150px 1fr 56px;gap:10px;align-items:center;font-size:13px;border-radius:8px;padding:2px 4px;margin:0 -4px}
.wlabel{color:var(--text-secondary)}
.wtrack{position:relative;height:16px;background:linear-gradient(90deg,var(--grid) 1px,transparent 1px) 0 0/25% 100%}
.wbar{position:absolute;top:2px;height:12px;border-radius:4px}
.wbar.base{background:var(--series-comp)} .wbar.step{background:var(--pos)}
.wbar.pot{background:transparent;border:2px solid var(--pos)}
.wval{text-align:right;font-variant-numeric:tabular-nums}
.waxis{position:relative;height:14px;font-size:11px;color:var(--muted)}
.waxis span{position:absolute;transform:translateX(-50%)}
.waxis span:first-child{transform:none} .waxis span:last-child{transform:translateX(-100%)}
.plist{display:grid;gap:4px}
.prow{display:grid;grid-template-columns:minmax(140px,1.1fr) 130px minmax(160px,2fr) minmax(170px,1.2fr);gap:14px;align-items:center;
  padding:10px 8px;border-radius:12px;outline:none}
.prow+.prow{border-top:1px solid var(--grid)}
.prow:hover,.prow:focus-visible{background:var(--surface-2)}
.focusrow{background:var(--accent-soft)}
.focusrow:hover{background:var(--accent-soft)}
.pname{display:flex;gap:8px;align-items:center;min-width:0}
.pname>div,.pscore,.ptrend{display:flex;flex-direction:column;min-width:0}
.pname span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.swatch{width:10px;height:10px;border-radius:3px;flex:none;display:inline-block}
.pscore b{font-size:28px;line-height:1.1;font-variant-numeric:tabular-nums}
.stackbar{display:flex;gap:2px;height:12px;border-radius:4px;overflow:hidden;margin:4px 0}
.stackbar span{display:block;height:100%;min-width:2px}
.pdl{display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.progs{display:grid;gap:10px;margin:6px 0 10px}
.prog{display:grid;grid-template-columns:120px 1fr;gap:4px 12px;align-items:center;padding:6px;border-radius:10px;outline:none}
.prog:hover,.prog:focus-visible{background:var(--surface-2)}
.ptrack{display:flex;gap:2px;height:14px;border-radius:5px;overflow:hidden}
.ptrack span{display:block;height:100%} .ptrack .inv{background:var(--inv)} .ptrack .org{background:var(--org)}
.pnums{grid-column:2;display:flex;flex-wrap:wrap;gap:2px 14px;font-size:12.5px;color:var(--text-secondary);font-variant-numeric:tabular-nums}
.pnums span:first-child{color:var(--text-primary);font-weight:650}
table.countries th,table.countries td{white-space:nowrap}
table.countries .sc{text-align:center;font-variant-numeric:tabular-nums;border-radius:6px}
table.countries thead .sc{font-weight:500;font-size:11px;color:var(--muted);white-space:normal;width:82px;line-height:1.2}
table.countries thead .sc .icon{display:block;margin:0 auto 2px}
table.countries small{display:block;font-weight:400;font-size:11px}
table.countries tr.few th,table.countries tr.few td{opacity:.7}
.brands{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.brand{background:var(--surface-1);border:1px solid var(--border);border-top:5px solid var(--brand);border-radius:18px;padding:16px 18px}
.brand h3{font-size:18px}
.brand p{margin:8px 0 0;font-size:14px}
.brand .pos{color:var(--text-secondary)}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:4px 0 6px}
.kpis div{background:var(--surface-2);border-radius:10px;padding:6px 8px}
.kpis b{display:block;font-size:18px;font-variant-numeric:tabular-nums}
.kpis span{font-size:11px;color:var(--muted);line-height:1.2;display:block}
.lesson{border-top:1px solid var(--border);padding-top:8px}
.linkbtn{appearance:none;background:none;border:0;padding:8px 0 0;color:var(--accent-ink);font:inherit;font-size:14px;font-weight:600;cursor:pointer}
.linkbtn:hover{text-decoration:underline;background:none}
.tablewrap{overflow-x:auto}
.scrollx{overflow-x:auto} .scrollx .matrix{min-width:560px}
table{border-collapse:separate;border-spacing:2px;width:100%;font-size:13px}
table.heat{table-layout:fixed;min-width:620px}
.heat th:first-child{width:30%}
.heat th{font-weight:500;color:var(--text-secondary);text-align:left;padding:4px 6px}
.heat thead th{text-align:center;vertical-align:bottom}
.heat thead th small,.heat .mk small{display:block;color:var(--muted);font-weight:400;font-size:11px}
.heat thead th.focus{color:var(--text-primary);font-weight:700}
.heat .grouprow th{padding-top:14px;color:var(--text-primary);font-weight:700;font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.heat .hc{text-align:center;padding:6px 4px;border-radius:6px;font-variant-numeric:tabular-nums;color:#1b1512}
.heat .hc small{display:block;font-size:11px;opacity:.75}
.heat .hc.on-dark{color:#ffffff}
.heat .hc.empty{color:var(--muted);background:transparent;cursor:default}
.heat .mk{text-align:center;color:var(--text-secondary);font-variant-numeric:tabular-nums;border-left:1px solid var(--grid)}
.scale{display:flex;gap:3px;align-items:center;font-size:12px;color:var(--muted);margin:10px 0 0;flex-wrap:wrap}
.scale i{display:inline-block;width:26px;height:10px;border-radius:2px}
table.plain th,table.plain td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid);vertical-align:middle}
table.plain .num{font-variant-numeric:tabular-nums;text-align:right}
details{margin-top:12px} summary{cursor:pointer;font-weight:600;font-size:14px;color:var(--text-secondary)}
.filters{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;background:var(--surface-1);border:1px solid var(--border);
  border-radius:18px;padding:12px 14px;position:sticky;top:56px;z-index:4}
.filters label{display:flex;flex-direction:column;font-size:12px;color:var(--muted);gap:3px}
.filters label.grow{flex:1 1 180px}
.filters select,.filters input{font:inherit;font-size:14px;padding:6px 8px;border-radius:10px;border:1px solid var(--border);
  background:var(--page);color:var(--text-primary);min-width:0;max-width:100%}
.filters select{max-width:200px}
.evlist{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
.q{background:var(--surface-1);border:1px solid var(--border);border-left:4px solid var(--brand);border-radius:14px;padding:10px 12px;font-size:14px}
.q blockquote{margin:0 0 6px}
.q .orig{font-size:12.5px;color:var(--muted);font-style:italic;margin:0 0 6px}
.q .qm{font-size:12px;color:var(--muted);display:flex;flex-wrap:wrap;gap:2px 10px}
.q .qm b{color:var(--text-secondary);font-weight:600}
.stars-low{color:var(--bad);font-weight:650} .stars-high{color:var(--good);font-weight:650}
.morebtn{display:block;margin:16px auto 0;font:inherit;padding:8px 18px;border-radius:999px;border:1px solid var(--border);
  background:var(--surface-1);color:var(--text-primary);cursor:pointer}
.method{padding-left:18px;margin:0} .method li{margin-bottom:8px}
#tip{position:fixed;z-index:20;pointer-events:none;max-width:320px;padding:8px 10px;border-radius:10px;
  background:var(--surface-1);color:var(--text-primary);border:1px solid var(--border);
  box-shadow:0 6px 20px rgba(0,0,0,.16);font-size:13px;line-height:1.4;display:none}
footer{color:var(--muted);font-size:13px;padding-block:24px 40px;border-top:1px solid var(--border)}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
@media (max-width:900px){
  .jstrip{grid-template-columns:repeat(3,1fr)}
  .stage-body{grid-template-columns:1fr}
  .vnums{grid-template-columns:repeat(2,1fr)}
}
@media (max-width:600px){
  header.top h1{font-size:24px} .headline{font-size:21px} .lede{font-size:16px} h2{font-size:21px}
  .hero{grid-template-columns:1fr;padding:18px} .hero-art{justify-self:center;max-width:280px}
  .jstrip{grid-template-columns:repeat(2,1fr)}
  .tval{font-size:30px} .brow{grid-template-columns:1fr} .wrow{grid-template-columns:96px 1fr 44px}
  .two{grid-template-columns:1fr} .insights,.lanes,.brands,.evlist{grid-template-columns:1fr}
  .filters{position:static} .filters label{flex:1 1 45%} .filters select{max-width:none}
  .kpis{grid-template-columns:repeat(2,1fr)}
  .prow{grid-template-columns:1fr auto;gap:6px 12px} .pdist,.ptrend{grid-column:1 / -1}
  .path::before{display:none} .stage-kpis{margin-left:0;width:100%}
  .trow{grid-template-columns:1fr 64px} .trow .meter{grid-column:1 / -1;grid-row:2}
  .vcard{grid-template-columns:1fr;padding:16px} .vrank{text-align:left;font-size:28px}
  .prog{grid-template-columns:1fr} .pnums{grid-column:1}
}
@media print{
  .tabs,.filters,#ev-more,.linkbtn{display:none}
  [role="tabpanel"][hidden]{display:block}
  .card,.insight,.brand,.stage,.vcard{break-inside:avoid}
}
"""

JS = r"""
(function(){
// ---------- tooltips ----------
const tipEl=document.getElementById('tip');
function show(el,x,y){tipEl.innerHTML=el.dataset.tip;tipEl.style.display='block';
  const r=tipEl.getBoundingClientRect();let L=x+14,T=y+14;
  if(L+r.width>innerWidth-8)L=x-r.width-14; if(T+r.height>innerHeight-8)T=y-r.height-14;
  tipEl.style.left=Math.max(8,L)+'px';tipEl.style.top=Math.max(8,T)+'px';}
function hide(){tipEl.style.display='none';}
document.addEventListener('mouseover',e=>{const el=e.target.closest('[data-tip]');if(el)show(el,e.clientX,e.clientY);});
document.addEventListener('mousemove',e=>{const el=e.target.closest('[data-tip]');if(el)show(el,e.clientX,e.clientY);else hide();});
document.addEventListener('focusin',e=>{const el=e.target.closest('[data-tip]');if(el){const b=el.getBoundingClientRect();show(el,b.left+b.width/2,b.bottom);}});
document.addEventListener('focusout',hide);
addEventListener('scroll',hide,{passive:true});

// ---------- tabs (deep links: #journey, #vault, #evidence, ...) ----------
const tabs=[...document.querySelectorAll('[role="tab"]')];
function select(id,focus){
  tabs.forEach(t=>{const on=t.dataset.tab===id;t.setAttribute('aria-selected',on);t.tabIndex=on?0:-1;
    document.getElementById('p-'+t.dataset.tab).hidden=!on; if(on&&focus)t.focus();});
}
tabs.forEach((t,i)=>{
  t.addEventListener('click',()=>{select(t.dataset.tab);history.replaceState(null,'','#'+t.dataset.tab);scrollTo({top:0});});
  t.addEventListener('keydown',e=>{let j=null;if(e.key==='ArrowRight')j=(i+1)%tabs.length;if(e.key==='ArrowLeft')j=(i-1+tabs.length)%tabs.length;
    if(j!==null){e.preventDefault();tabs[j].click();tabs[j].focus();}});
});
// Journey chips on the overview jump to that stage.
document.querySelectorAll('[data-stage-link]').forEach(a=>a.addEventListener('click',e=>{
  e.preventDefault();select('journey');history.replaceState(null,'','#journey');hide();
  const el=document.getElementById('stage-'+a.dataset.stageLink);if(el)el.scrollIntoView({block:'start'});}));

// ---------- evidence explorer ----------
const D=JSON.parse(document.getElementById('evdata').textContent);
const F={brand:document.getElementById('f-brand'),stage:document.getElementById('f-stage'),theme:document.getElementById('f-theme'),
  stars:document.getElementById('f-stars'),lang:document.getElementById('f-lang'),q:document.getElementById('f-q')};
const list=document.getElementById('ev-list'),count=document.getElementById('ev-count'),more=document.getElementById('ev-more');
let shown=0,rows=[];const PAGE=60;
const esc=s=>s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function filter(){
  const b=F.brand.value,g=F.stage.value,t=F.theme.value,s=F.stars.value,l=F.lang.value,q=F.q.value.trim().toLowerCase();
  rows=D.rows.filter(r=>(!b||r.b===b)&&(!g||(D.stage[r.t]||'before')===g)&&(!t||r.t===t)&&(!l||r.l===l)&&
    (!s||(s==='low'&&r.r<=2)||(s==='mid'&&r.r===3)||(s==='high'&&r.r>=4))&&
    (!q||(r.q+' '+(r.o||'')+' '+D.themes[r.t]).toLowerCase().includes(q)));
  count.textContent=rows.length+' quotes'+(b||g||t||s||l||q?' match these filters':'');
  list.innerHTML='';shown=0;page();
}
function page(){
  const html=rows.slice(shown,shown+PAGE).map(r=>{
    const st=r.r<=2?'stars-low':(r.r>=4?'stars-high':'');
    return '<div class="q" style="--brand:var('+D.colors[r.b]+')"><blockquote>“'+esc(r.q)+'”</blockquote>'+
      (r.o?'<p class="orig">'+esc(r.o)+'</p>':'')+
      '<div class="qm"><b>'+esc(D.brands[r.b])+'</b><span>'+esc(D.themes[r.t])+'</span><span class="'+st+'">'+r.r+'★</span><span>'+r.d+'</span><span>'+esc(D.langs[r.l]||r.l)+'</span></div></div>';
  }).join('');
  list.insertAdjacentHTML('beforeend',html);shown+=PAGE;more.hidden=shown>=rows.length;
}
more.addEventListener('click',page);
Object.values(F).forEach(el=>el.addEventListener(el.tagName==='INPUT'?'input':'change',filter));
document.getElementById('f-reset').addEventListener('click',()=>{Object.values(F).forEach(el=>el.value='');filter();});

function openEvidence(d){
  F.brand.value=d.evBrand||'';F.stage.value=d.evStage||'';F.theme.value=d.evTheme||'';F.stars.value=d.evStars||'';
  F.lang.value='';F.q.value='';filter();
  select('evidence');history.replaceState(null,'','#evidence');scrollTo({top:0});hide();
}
document.addEventListener('click',e=>{const el=e.target.closest('[data-ev]');if(el)openEvidence(el.dataset);});
document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('[data-ev]')){e.preventDefault();e.target.click();}});

function route(){const id=location.hash.slice(1);select(tabs.some(t=>t.dataset.tab===id)?id:'overview');}
filter();route();addEventListener('hashchange',route);
})();
"""


FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;650;700'
         '&family=Source+Sans+3:wght@400;600;700&display=swap">')


def render(data, summary, fragment=False):
    """fragment=True: page content without <html>/<head>/<body>, for publishing as a claude.ai artifact."""
    f = data["focus"]
    brands = [f] + data["competitors"]
    comp_names = ", ".join(short_brand(b) for b in data["competitors"])
    ev = {"rows": data["evidence_rows"],
          "brands": {b: BRAND_NAMES[b] for b in brands},
          "colors": {b: BRAND_COLOR_SLOTS[i] for i, b in enumerate(brands)},
          "themes": THEME_LABEL, "langs": LANG_NAME, "stage": STAGE_OF}
    ev_json = json.dumps(ev, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tabs = [("overview", "Overview"), ("ask", "Ask the reviews"), ("journey", "Customer journey"), ("vault", "Problem Vault"), ("triage", "Review triage"),
            ("focus", f"{short_brand(f)} deep dive"), ("category", "Competitors"),
            ("evidence", "Evidence"), ("method", "Method")]
    tab_buttons = "".join(
        f'<button role="tab" id="t-{k}" data-tab="{k}" aria-controls="p-{k}" aria-selected="false" tabindex="-1">{escape(v)}</button>'
        for k, v in tabs)
    panels = {
        "overview": tab_overview(data, summary),
        "ask": tab_ask(data),
        "triage": tab_triage(data, icon, short_brand),
        "journey": tab_journey(data, summary),
        "vault": tab_vault(data, summary),
        "focus": tab_focus(data, summary),
        "category": tab_category(data, summary),
        "evidence": tab_evidence(data),
        "method": tab_method(data),
    }
    panel_html = "".join(f'<section role="tabpanel" id="p-{k}" aria-labelledby="t-{k}" hidden>{panels[k]}</section>'
                         for k, _ in tabs)
    period = f'{datetime.fromisoformat(data["date_from"]):%d %b} – {datetime.fromisoformat(data["date_to"]):%d %b %Y}'
    head = f"""<title>Walking Pad Insights</title>
<meta name="claude:viewport-fit-sides" content="cover">
{FONTS}
<style>{CSS}{ASK_CSS}{TRI_CSS}{competitors.CSS}</style>"""
    body = f"""<header class="top"><div class="wrap">
  <div class="brandline"><span class="logo"><i></i>Walking Pad Insights</span></div>
  <h1>What walking pad customers say after they click order</h1>
  <p class="meta"><span><b>{escape(short_brand(f))}</b> vs {escape(comp_names)}</span>
    <span>{data["n_reviews"]:,} reviews · {period}</span>
    <span>Trustpilot · Europe incl. UK</span><span>Numbers updated {datetime.now():%d %b %Y}</span>
    {f'<span>AI insights written {datetime.fromisoformat(summary["_written_on"]):%d %b %Y}</span>' if summary.get("_written_on") else ""}</p>
</div></header>
<nav class="tabs" aria-label="Report sections"><div class="wrap" role="tablist">{tab_buttons}</div></nav>
<main class="wrap">{panel_html}</main>
<footer class="wrap">Independent analysis of public reviews, built with an AI agent: Trustpilot reviews → Claude theme tagging → counted
statistics → Claude insights. Not affiliated with any brand shown. Every number links to its source quotes in the Evidence tab.
No reviewer names are stored.</footer>
<div id="tip" role="tooltip"></div>
<script type="application/json" id="evdata">{ev_json}</script>
<script type="application/json" id="askdata">{ask_json(data)}</script>
<script>{JS}</script>
<script>{ASK_JS}</script><script>{TRIAGE_JS}</script>"""
    if fragment:
        return head + "\n" + body
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            f'{head}</head>\n<body>\n{body}\n</body></html>')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="ask Claude for a new insight summary")
    args = parser.parse_args()

    data = build()
    if len(data["months"]) < 2:
        raise SystemExit("Need at least two months of analysed reviews to build the report.")
    summary = get_insights(data, force=args.refresh)
    summary["_competitors"] = competitors.get_lessons(data, force=args.refresh)
    html = render(data, summary)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"report-{data['date_to']}.html"
    out.write_text(html, encoding="utf-8")
    shutil.copyfile(out, REPORTS_DIR / "latest.html")
    # Same report as page content only, for publishing as a private claude.ai link.
    pub = REPORTS_DIR / "publish"
    pub.mkdir(exist_ok=True)
    (pub / "walking-pad-insights.html").write_text(render(data, summary, fragment=True), encoding="utf-8")
    print(f"Report written: {out}\nAlso copied to: {REPORTS_DIR / 'latest.html'}")


if __name__ == "__main__":
    main()
