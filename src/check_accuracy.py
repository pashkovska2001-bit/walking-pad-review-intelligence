"""
Check how well Claude found the patterns we planted in the FICTIONAL data.

Only works for the sample data (it needs data/sample_ground_truth.csv).

Two simple scores per theme:
- precision: when Claude tagged this theme, how often was it really there?
- recall:    when the theme was really there, how often did Claude find it?

Run:  python src/check_accuracy.py
"""

import csv
import json
import os
import sqlite3
from collections import Counter, defaultdict

os.environ.setdefault("WPI_DATASET", "sample")   # needs the planted labels
from config import DATA_DIR, DB_PATH, PROJECT_DIR, all_theme_keys

truth_rows = list(csv.DictReader(open(DATA_DIR / "sample_ground_truth.csv", encoding="utf-8")))
truth = {r["review_id"]: (r["planted_sentiment"], set(filter(None, r["planted_themes"].split("|"))))
         for r in truth_rows}

conn = sqlite3.connect(DB_PATH)
ai_sent = dict(conn.execute("SELECT review_id, sentiment FROM review_analysis"))
ai_themes = defaultdict(set)
for rid, theme in conn.execute("SELECT review_id, theme FROM review_themes"):
    ai_themes[rid].add(theme)

ids = [rid for rid in ai_sent if rid in truth]
print(f"Reviews compared: {len(ids)}\n")

sent_ok = sum(ai_sent[r] == truth[r][0] for r in ids)
print(f"Sentiment matches planted label: {sent_ok}/{len(ids)} ({sent_ok / len(ids):.0%})")
confusion = Counter((truth[r][0], ai_sent[r]) for r in ids if ai_sent[r] != truth[r][0])
for (planted, ai), n in confusion.most_common(5):
    print(f"   planted {planted:8} -> AI said {ai:8}: {n}")

tp, fp, fn = Counter(), Counter(), Counter()
for r in ids:
    planted, found = truth[r][1], ai_themes[r]
    for t in found & planted:
        tp[t] += 1
    for t in found - planted:
        fp[t] += 1
    for t in planted - found:
        fn[t] += 1

print(f"\n{'theme':24} {'planted':>7} {'found':>6} {'precision':>9} {'recall':>7}")
for t in all_theme_keys():
    planted_n = tp[t] + fn[t]
    if planted_n == 0 and fp[t] == 0:
        continue
    prec = tp[t] / (tp[t] + fp[t]) if tp[t] + fp[t] else 0
    rec = tp[t] / planted_n if planted_n else 0
    print(f"{t:24} {planted_n:7} {tp[t] + fp[t]:6} {prec:9.0%} {rec:7.0%}")

all_tp, all_fp, all_fn = sum(tp.values()), sum(fp.values()), sum(fn.values())
precision, recall = all_tp / (all_tp + all_fp), all_tp / (all_tp + all_fn)
print(f"\nOverall theme precision {precision:.0%}, recall {recall:.0%}")

# Saved so the real-data report can say how the tagging model was validated.
models = sorted({m for (m,) in conn.execute("SELECT DISTINCT model FROM review_analysis")})
with open(PROJECT_DIR / "data" / "accuracy.json", "w") as f:
    json.dump({"models": models, "reviews": len(ids), "precision": round(precision, 3),
               "recall": round(recall, 3), "sentiment_match": round(sent_ok / len(ids), 3)}, f)
