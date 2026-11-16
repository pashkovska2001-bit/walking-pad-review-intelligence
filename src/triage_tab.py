"""The 'Review triage' tab: output of src/triage_agent.py (cause, owner, urgency, draft reply)."""

import json
import sqlite3
from collections import Counter
from html import escape

from config import DB_PATH, JOURNEY

STAGE_NAME = {"before": "Before the order", **{s["key"]: s["name"] for s in JOURNEY}}
LANG = {"nl": "Dutch", "de": "German", "en": "English", "fr": "French", "es": "Spanish", "it": "Italian"}
URG = {"high": ("High", "u-high"), "medium": ("Medium", "u-med"), "low": ("Low", "u-low")}


def load_triage():
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("""SELECT t.review_id, t.model, t.result, r.review_date, r.country, r.rating, r.language
                               FROM review_triage t JOIN reviews r USING (review_id)
                               ORDER BY r.review_date DESC""").fetchall()
    except sqlite3.OperationalError:
        return []
    return [{"id": r[0], "model": r[1], **json.loads(r[2]), "date": r[3], "country": r[4].upper(),
             "rating": r[5], "lang": r[6]} for r in rows]


def tab_triage(data, icon, short_brand):
    items = load_triage()
    f = short_brand(data["focus"])
    if not items:
        return '<p class="sub">No reviews triaged yet. Run <code>python src/triage_agent.py</code>.</p>'
    quotes = {}
    idx = data["agent_index"]
    for e in data["evidence_rows"]:
        quotes.setdefault("TP-" + idx[e["x"]][6], []).append(e["q"])
    urg = Counter(i["urgency"] for i in items)
    owners = Counter(i["owner"].split(" (")[0].split(";")[0] for i in items)
    models = sorted({i["model"] for i in items})
    cards = []
    for i in items:
        label, cls = URG.get(i["urgency"], ("?", "u-low"))
        qs = quotes.get(i["id"], [])[:2]
        q_html = "".join(f"<blockquote>“{escape(q)}”</blockquote>" for q in qs)
        lang = LANG.get(i.get("reply_language") or i["lang"], (i.get("reply_language") or "").upper())
        cards.append(f"""<article class="card tri">
          <div class="tri-top"><span class="upill {cls}">{label} urgency</span>
            <span class="muted small">{'★' * i['rating']}{'☆' * (5 - i['rating'])} · {escape(i['country'])} · {escape(i['date'])} ·
            <a href="https://www.trustpilot.com/reviews/{escape(i['id'].replace('TP-', ''))}" target="_blank" rel="noopener noreferrer">Open review ↗</a></span></div>
          {q_html}
          <dl class="tri-dl">
            <dt>Cause</dt><dd>{escape(i['cause'])}</dd>
            <dt>Stage</dt><dd>{icon(i['stage'], 16) if i['stage'] in STAGE_NAME and i['stage'] != 'before' else ''} {escape(STAGE_NAME.get(i['stage'], i['stage']))}</dd>
            <dt>Owner</dt><dd>{escape(i['owner'])}</dd>
            <dt>Pattern</dt><dd>{escape(i['pattern'])}</dd>
            <dt>Fix the cause</dt><dd>{escape(i['internal_action'])}</dd>
          </dl>
          <details><summary>Draft public reply ({escape(lang)})</summary><p class="tri-reply">{escape(i['draft_reply'])}</p></details>
        </article>""")
    top_owner = ", ".join(f"{escape(o)} {n}" for o, n in owners.most_common(3))
    live = live_section(data, {i["id"] for i in items}, f)
    return f"""
    <h2>Review triage: an agent for every 1–2★ review</h2>
    <p class="sub">For each new negative {escape(f)} review, an AI agent reads it, checks the Problem Vault and whether the same problem is
    recurring (it decides which lookups it needs), then names the cause, owner and urgency, and drafts a reply in the customer's language.
    A person reviews and sends; nothing is posted automatically. This is how “1–2★ reviews picked up within a day” can scale.</p>
    <div class="tiles">
      <div class="tile"><div class="tlabel">Triaged</div><div class="tval">{len(items)}</div><div class="tnote">latest 1–2★ reviews</div></div>
      <div class="tile bad"><div class="tlabel">Urgency</div><div class="tval">{urg.get('high', 0)} high</div><div class="tnote">{urg.get('medium', 0)} medium · {urg.get('low', 0)} low</div></div>
      <div class="tile"><div class="tlabel">Owners</div><div class="tval small-val">{top_owner}</div><div class="tnote">where the cause gets fixed</div></div>
    </div>
    {live}
    <h3>Already triaged</h3>
    <div class="trigrid">{''.join(cards)}</div>
    <p class="muted small">Agent: {escape(', '.join(models))} with three tools (Problem Vault, pattern check, submit triage); about $0.003 per review.
    Draft replies are examples written by AI for this independent analysis, not sent and not written by or for {escape(f)}. Placeholders in
    [brackets] are filled in by the team. Quotes are max 15 words; open the review for the full text.</p>"""


def live_section(data, done_ids, f, n=10):
    """Untriaged 1-2 star reviews of the focus brand, each with a button that runs the agent live in the page."""
    idx = data["agent_index"]
    by_x = {}
    for e in data["evidence_rows"]:
        by_x.setdefault(e["x"], []).append(e)
    rows = [(x, a) for x, a in enumerate(idx)
            if a[0] == data["focus"] and a[3] <= 2 and "TP-" + a[6] not in done_ids and by_x.get(x)][:n]
    if not rows:
        return ""
    lis = []
    for x, a in rows:
        q = by_x[x][0]["q"]
        lis.append(f"""<li class="lv" data-x="{x}"><div class="lv-row">
          <span class="lv-meta">{'★' * a[3]}{'☆' * (5 - a[3])} · {escape(a[1])} · {escape(a[2])}</span>
          <span class="lv-q">“{escape(q)}”</span>
          <button type="button" class="primary lv-go">Triage live</button></div><div class="lv-out"></div></li>""")
    return f"""
    <div class="askbox lvbox">
      <h3>Try it live</h3>
      <p class="sub">These {escape(f)} 1–2★ reviews have not been triaged yet. Press <b>Triage live</b> and watch the agent work: it opens the
      Problem Vault, checks whether the problem is recurring, then writes the triage and a draft reply. It runs on your own Claude plan.
      The page only holds short quotes and tags, not the full review, so a live triage is based on those.</p>
      <p id="lv-off" class="note" hidden>Live triage works when this page is opened on claude.ai while signed in.</p>
      <ul class="lvlist">{''.join(lis)}</ul>
    </div>"""


CSS = """
.lvbox h3{margin:0 0 4px}
.lvlist{list-style:none;margin:8px 0 0;padding:0}
.lv{border-top:1px solid var(--border);padding:8px 0}
.lv-row{display:grid;grid-template-columns:auto 1fr auto;gap:10px;align-items:center;font-size:14px}
.lv-meta{color:var(--muted);white-space:nowrap}
.lv-go{font-size:13px;padding:6px 14px}
.lv-out:not(:empty){margin-top:8px}
.lv-out .card{margin:0}
@media (max-width:640px){.lv-row{grid-template-columns:1fr}.lv-go{justify-self:start}}
.trigrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;margin-top:12px}
.tri-top{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center}
.upill{font-size:12px;font-weight:700;border-radius:999px;padding:2px 10px}
.u-high{background:var(--neg-soft);color:var(--bad)}.u-med{background:var(--accent-soft);color:var(--accent-ink)}.u-low{background:var(--surface-2);color:var(--muted)}
.tri blockquote{margin:8px 0 0;padding:6px 10px;border-left:3px solid var(--neg);background:var(--surface-2);border-radius:0 8px 8px 0;font-size:14px}
.tri-dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 12px;margin:10px 0;font-size:14px}
.tri-dl dt{font-weight:700;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.03em;padding-top:2px}
.tri-dl dd{margin:0}.tri-dl dd svg{vertical-align:-3px}
.tri details{border-top:1px solid var(--border);padding-top:8px}
.tri summary{cursor:pointer;font-weight:600;color:var(--accent-ink)}
.tri-reply{white-space:pre-line;background:var(--pos-soft);border-radius:10px;padding:10px 12px;font-size:14px}
.small-val{font-size:16px!important;line-height:1.3}
"""


TRIAGE_JS = r"""
(function(){
const A=window.__agent; if(!A)return;
const list=document.querySelector('.lvlist'); if(!list)return;
const {D,R,EV,esc,COUNTRY}=A;
const LANG={nl:'Dutch',de:'German',en:'English',fr:'French',es:'Spanish',it:'Italian'};
const STAGES=D.stages;
const focusRows=R.filter(r=>r.b===D.focus);
const end=D.period[1];
function pattern_check(i){
  const theme=String(i.theme||''); if(!D.themes[theme])throw new Error('Unknown theme. Use one of: '+Object.keys(D.themes).join(', '));
  const days=Math.max(7,Math.min(180,Number(i.days)||30));
  const since=new Date(new Date(end).getTime()-days*864e5).toISOString().slice(0,10);
  const recent=focusRows.filter(r=>r.d>=since),hits=recent.filter(r=>r.t.includes(theme));
  const six=focusRows.filter(r=>r.t.includes(theme)).length,byc={};
  hits.forEach(r=>byc[r.c]=(byc[r.c]||0)+1);
  return{theme,label:D.themes[theme].label,window_days:days,reviews_in_window:recent.length,mentioning_theme:hits.length,
    share_in_window:recent.length?Math.round(hits.length/recent.length*1000)/1000:null,
    share_6_months:Math.round(six/focusRows.length*1000)/1000,by_country:byc,owner:D.owners[theme]||null};
}
const SYSTEM=`You triage negative public reviews for the customer experience lead of a direct-to-consumer walking pad brand (${D.brands[D.focus]}).
You get the review's stars, country, date, auto-tagged themes and short quotes from it (not the full text).
Steps: call problem_vault, call pattern_check for each problem the review raises, then call submit_triage exactly once. After that reply with just "Done."
Rules:
- Base the cause on what the quotes say ("the review says ..."). Never claim facts about the company's stock, carriers or staff.
- Urgency: high = safety issue, product broken or damaged, money owed for a long time, or the customer says they will escalate; medium = an open problem the company can still fix; low = venting about something already resolved.
- Draft reply: in the review's language, at most 90 words, warm and specific, apologise for the specific experience, no excuses, no blame. Never promise a delivery date, a refund or compensation. Invite them to send their order number to [support email]. No customer name. Sign off with "[Name], Customer Care".
- All other fields: plain English, one sentence each.
Journey stage keys: before, ${Object.keys(STAGES).filter(k=>k!=='before').join(', ')}. Theme keys: ${Object.keys(D.themes).join(', ')}.`;
function card(t,r){
  const cls={high:'u-high',medium:'u-med',low:'u-low'}[String(t.urgency).toLowerCase()]||'u-low';
  return `<article class="card tri"><div class="tri-top"><span class="upill ${cls}">${esc(t.urgency)} urgency</span>
    <span class="muted small">Triaged live just now · <a href="https://www.trustpilot.com/reviews/${esc(r.id)}" target="_blank" rel="noopener noreferrer">Open review ↗</a></span></div>
    <dl class="tri-dl"><dt>Cause</dt><dd>${esc(t.cause)}</dd><dt>Stage</dt><dd>${esc(STAGES[t.stage]||t.stage)}</dd>
    <dt>Owner</dt><dd>${esc(t.owner)}</dd><dt>Pattern</dt><dd>${esc(t.pattern)}</dd><dt>Fix the cause</dt><dd>${esc(t.internal_action)}</dd></dl>
    <details open><summary>Draft public reply (${esc(LANG[t.reply_language]||t.reply_language)})</summary><p class="tri-reply">${esc(t.draft_reply)}</p></details></article>`;
}
let running=false;
list.addEventListener('click',async e=>{
  const btn=e.target.closest('.lv-go'); if(!btn||running)return;
  const sample=A.sample;
  if(!sample){document.getElementById('lv-off').hidden=false;return;}
  const li=btn.closest('.lv'),x=Number(li.dataset.x),r=R[x],out=li.querySelector('.lv-out');
  const quotes=EV.filter(ev=>ev.x===x);
  const lang=(quotes.find(q=>q.l)||{}).l||'en';
  out.innerHTML='';const st=document.createElement('p');st.className='muted small';out.append(st);
  const box=A.newTrace(out,st);const sink={};
  const tr=(n,f)=>A.traced(box,n,f);
  const tools=[
    {name:'problem_vault',description:A.T_VAULT.description,inputSchema:A.T_VAULT.inputSchema,execute:tr('problem_vault',A.T_VAULT.fn)},
    {name:'pattern_check',description:'How many of the brand\'s reviews in the last `days` days mention this theme, by country, versus the 6-month share.',
     inputSchema:{type:'object',properties:{theme:{type:'string',description:'theme key'},days:{type:'integer',description:'look-back window, default 30'}},required:['theme']},
     execute:tr('pattern_check',pattern_check)},
    {name:'submit_triage',description:'Record the triage. Call exactly once, as the last step.',
     inputSchema:{type:'object',required:['cause','stage','owner','urgency','pattern','internal_action','reply_language','draft_reply'],properties:{
       cause:{type:'string'},stage:{type:'string'},owner:{type:'string',description:'team that owns the fix; use the Problem Vault owner where it fits'},
       urgency:{type:'string',enum:['high','medium','low']},pattern:{type:'string',description:'one sentence with numbers from pattern_check'},
       internal_action:{type:'string'},reply_language:{type:'string',description:'ISO code, e.g. nl, de'},draft_reply:{type:'string'}}},
     execute:tr('submit_triage',i=>{Object.assign(sink,i);return'Saved.';})},
  ];
  const msg=`Review: ${r.r} stars, ${COUNTRY[r.c]||r.c}, ${r.d}, language ${lang}. Auto-tagged themes: ${r.t.join(', ')||'none'}.
Quotes from the review:
${quotes.map(q=>'- '+(q.o?q.o+' (English: '+q.q+')':q.q)).join('\n')}`;
  running=true;document.querySelectorAll('.lv-go').forEach(b=>b.disabled=true);st.textContent='Starting the agent…';
  try{
    await sample([{role:'user',content:SYSTEM+'\n\n'+msg}],{tools,cache:false});
    if(sink.draft_reply){box.el.open=false;st.remove();out.insertAdjacentHTML('beforeend',card(sink,r));btn.textContent='Done';btn.disabled=true;btn.dataset.done=1;}
    else st.textContent='The agent finished without a triage. Try again.';
  }catch(err){
    st.textContent={not_granted:'Claude is not allowed on this page for you.',rate_limited:'Too many requests right now. Try again in a little while.',
      cancelled:'Stopped.'}[err&&err.code]||'Something went wrong. Try again.';
  }finally{running=false;document.querySelectorAll('.lv-go').forEach(b=>{if(!b.dataset.done)b.disabled=false;});}
});
})();
"""
