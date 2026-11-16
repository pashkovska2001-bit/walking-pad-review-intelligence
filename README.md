# Walking Pad Review Intelligence

An AI-assisted customer experience project: it turns public Trustpilot reviews of
walking pads (compact home treadmills) into insights a CX team can act on, and adds
two AI agents on top.

It compares **Moov** with **WalkingPad (KingSmith)**, **Merach** and **Sportstech**
on European reviews (incl. UK) from the last 6 months, about 1,200 reviews.

> Independent analysis of public reviews. Not affiliated with, commissioned by or
> endorsed by any brand mentioned. **No review data is included in this repository**,
> only the code (see [Data rules](#data-rules)).

## What it produces

One self-contained HTML report, refreshed every 2 days, organised along the
customer journey after the order:

| Tab | What a CX lead gets |
|---|---|
| Overview | Headline, key numbers, three insights, a post-purchase message plan and an action roadmap |
| Ask the reviews | An AI agent that answers questions or **investigates a goal** step by step, with cited sources |
| Customer journey | Six stages (order & wait, delivery, set-up, first weeks, service, returns), what goes wrong and right, vs competitors |
| Problem Vault | The focus brand's top 5 problems ranked by stars lost, with owner, trend, cause and fix |
| Review triage | An AI agent that triages every 1–2★ review: cause, owner, urgency, draft reply |
| Deep dive | By country, invited vs organic reviews, reply speed, monthly trend |
| Competitors | What each competitor's customers praise and complain about, and one idea to borrow |
| Evidence | Every tagged quote (max 15 words), filterable; every number links back here |
| Method | Definitions, AI quality checks and limitations |

## The pipeline

```
Trustpilot (via Apify, public reviews only)
  -> collect_trustpilot.py    new reviews, Europe only, no reviewer data
  -> analyze.py               Claude Haiku tags each review with fixed themes + a short quote
  -> report_data.py           counts, shares, stars lost, trends (plain Python, no AI)
  -> insights.py              Claude Opus writes the insight briefing from the numbers
  -> competitors.py           Claude Opus writes one lesson per competitor
  -> triage_agent.py          agent: triages new 1-2★ reviews
  -> build_report.py          one HTML file
```

`scripts/run_update.sh` runs everything with hard cost caps per run. A typical
run costs a few cents.

## The AI agents

**1. Ask the reviews** (`src/ask_tab.py`, runs in the report page)
The viewer types a question or a goal. Claude runs on the viewer's own claude.ai
account and chooses between page tools:
- `count_reviews`: counts, averages and theme shares with any filter (brand, country, theme, stars, month, invited/organic) and grouping
- `search_quotes`: short evidence quotes, each with a source id
- `problem_vault`: the top 5 problems with owner and journey stage
- in **Investigate** mode also `make_plan` and `complete_step`: the agent writes a 3–5 step plan, works through it, challenges its own main finding, and ends with Conclusion, Evidence, What to do first (owner + metric) and Limits

Every step is shown live, and every claim cites numbered sources that link to the original review.

**2. Review triage** (`src/triage_agent.py`, Claude Haiku via the tool runner)
For each new 1–2★ review of the focus brand the agent checks the Problem Vault and
whether the problem is recurring (`pattern_check`), then records the cause, journey
stage, owner team, urgency and a draft public reply in the customer's language.
Nothing is posted; drafts are for a person to edit. About $0.003 per review.
The report can also run this triage live, in the page, on untriaged reviews.

## How the analysis is checked

- Themes come from a fixed list (`src/config.py`), so counts stay comparable over time.
- For every theme Claude returns a word-for-word quote (max 15 words) plus a translation, so every number can be traced to evidence.
- `check_agreement.py`: Claude Opus independently re-tags a random sample of real reviews; Haiku agreed on 85% of tags and found 97% of the problems Opus found.
- `generate_sample_data.py` + `check_accuracy.py`: a labelled fictional test set with planted patterns, used only to test the pipeline before real data (never in the report).
- The insight prompts forbid outside knowledge and claims about any company's internal operations.

## Run it yourself

Python 3.9+.

```bash
python3 -m venv ~/.venvs/walking-pad-insights
~/.venvs/walking-pad-insights/bin/pip install -r requirements.txt
export ANTHROPIC_API_KEY=...   # never stored in code
export APIFY_TOKEN=...
scripts/run_update.sh          # collect -> tag -> triage -> report (reports/latest.html)
```

Useful flags: `collect_trustpilot.py --weeks 26 --max-charge 1.30` (6-month backfill),
`analyze.py --max-cost 0.10`, `triage_agent.py --limit 8 --model claude-haiku-5-5`,
`build_report.py --refresh` (rewrite insight texts).

## Data rules

- Public reviews only, collected through a data provider (Apify) rather than scraping directly.
- No reviewer names or personal data are collected or shown.
- Review texts, databases and generated reports stay local (`.gitignore`); they are reviewers' content and are not republished here.
- The report shows only short quotes (max 15 words) that link to the original review.
- API keys come from environment variables only.

## Limitations

- Trustpilot reviewers are not all customers: unhappy customers and invited customers are both over-represented, in different ways.
- Amazon and retailer product reviews are not included yet.
- AI tagging is checked against a stronger model, not against human labels.
- Small country samples are flagged as signals, not conclusions.
