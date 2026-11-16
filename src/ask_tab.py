"""
The 'Ask the reviews' tab: an AI agent inside the report.

The viewer types a question; Claude (through the claude.ai page capability
`sample`, on the viewer's own Claude account) decides which of two page
tools to call, as often as it needs:
  count_reviews  - counts and averages over every review, with filters and grouping
  search_quotes  - finds short evidence quotes (max 15 words) to cite
and answers with numbers plus numbered sources that link to the reviews.

Only data already in the report is used: tags, stars, dates, countries and
short quotes. No full review texts and no reviewer data.
"""

import json
from html import escape

from config import BRAND_NAMES, JOURNEY, PROBLEM_OWNER, STAGE_OF, THEMES, THEME_GROUP_LABELS

EXAMPLES = [
    "What do competitors' customers praise that Moov customers rarely mention?",
    "Why are German customers less happy than Dutch ones?",
    "Which brand handles refunds and returns best, according to reviews?",
    "What complaints show up even in Moov's invited reviews?",
    "What could Moov learn from WalkingPad's delivery experience?",
]

GOALS = [
    "Find the biggest fixable reason for Moov's 1–2★ reviews in the Netherlands, and what to fix first.",
    "Find one thing Moov could copy from the best-rated competitor, with proof from reviews.",
    "Check whether the delivery problem is getting better or worse, and in which countries.",
    "Find which journey stage costs Moov the most stars and what a CX lead can change there in 30 days.",
]


def ask_data(data):
    brands = [data["focus"]] + data["competitors"]
    themes = {t: {"label": label, "group": g, "stage": STAGE_OF.get(t, "before")}
              for g, ts in THEMES.items() for t, label in ts.items()}
    return {
        "focus": data["focus"],
        "brands": {b: BRAND_NAMES[b] for b in brands},
        "themes": themes,
        "groups": THEME_GROUP_LABELS,
        "stages": {"before": "Before the order", **{s["key"]: s["name"] for s in JOURNEY}},
        "period": [data["date_from"], data["date_to"]],
        "idx": data["agent_index"],
        "owners": PROBLEM_OWNER,
        "vault": [{"theme": v["theme"], "problem": themes[v["theme"]]["label"], "owner": v["owner"], "stage": v["stage"],
                   "share_of_reviews": v["share"], "market_share": v["market_share"], "stars_lost_estimate": v["stars_lost"],
                   "often_together_with": [c["theme"] for c in v.get("co_occurs", [])]} for v in data["vault"]],
    }


def tab_ask(data):
    f = BRAND_NAMES[data["focus"]]
    chips = "".join(f'<button type="button" class="askchip" data-mode="ask">{escape(q)}</button>' for q in EXAMPLES)
    chips += "".join(f'<button type="button" class="askchip" data-mode="inv" hidden>{escape(q)}</button>' for q in GOALS)
    return f"""
    <div class="askhead">
      <h2>Ask the reviews</h2>
      <p class="sub">An AI agent with tools: it <b>counts</b> across all {data["n_reviews"]:,} reviews (any brand, country, theme, star
      rating or month), <b>finds quotes</b> to back each claim and reads the <b>Problem Vault</b>. It decides itself what to look up, shows
      each step as it works, and answers with numbered sources you can open.</p>
    </div>
    <div class="askbox">
      <div class="askmode" role="tablist" aria-label="Agent mode">
        <button type="button" role="tab" aria-selected="true" data-mode="ask">Ask a question</button>
        <button type="button" role="tab" aria-selected="false" data-mode="inv">Investigate a goal</button>
      </div>
      <p class="muted small askmode-note" data-mode="ask">Quick answers, with follow-up questions.</p>
      <p class="muted small askmode-note" data-mode="inv" hidden>Give the agent a goal. It writes a plan, works through it step by step,
        double-checks its main number, and ends with findings, a first action with an owner, and how to measure it.</p>
      <div class="askchips">{chips}</div>
      <form id="ask-form" class="askform">
        <label for="ask-q" class="visually-hidden">Your question</label>
        <textarea id="ask-q" rows="2" maxlength="600" placeholder="e.g. What do customers of {escape(f)}'s competitors say about delivery?"></textarea>
        <div class="askbtns"><button type="submit" id="ask-go" class="primary">Ask</button>
          <button type="button" id="ask-stop" class="linkbtn" hidden>Stop</button>
          <button type="button" id="ask-new" class="linkbtn" hidden>New conversation</button></div>
      </form>
      <p id="ask-status" class="muted small" aria-live="polite"></p>
      <div id="ask-log" class="asklog"></div>
      <p id="ask-off" class="note" hidden>Asking questions works when this page is opened on claude.ai while signed in. Answers use the
        viewer's own Claude plan; the first question asks for permission.</p>
    </div>
    <p class="muted small">How it works: Claude only sees what the tools return (counts, averages, tags and short quotes) and is told to
    use no outside knowledge and to cite a source for every quote. It can still misread a question, so check the sources. Numbers here are
    computed live by the page from the same data as the rest of the report.</p>"""


ASK_CSS = """
.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.askbox{background:var(--surface-1);border:1px solid var(--border);border-radius:18px;padding:16px;margin:8px 0 12px}
.askchips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.askchip{font:inherit;font-size:13.5px;border:1px solid var(--border);background:var(--surface-2);color:var(--text-primary);
  border-radius:999px;padding:6px 12px;cursor:pointer;text-align:left}
.askchip:hover{border-color:var(--accent)}
.askform textarea{width:100%;font:inherit;font-size:16px;border:1px solid var(--axis);border-radius:12px;padding:10px 12px;
  background:var(--page);color:var(--text-primary);resize:vertical}
.askform textarea:focus{outline:2px solid var(--accent);outline-offset:1px}
.askbtns{display:flex;gap:12px;align-items:center;margin-top:8px}
.primary{font:inherit;font-weight:700;background:var(--accent);color:#fff;border:0;border-radius:999px;padding:8px 20px;cursor:pointer}
.primary:disabled{opacity:.5;cursor:default}
.asklog{display:flex;flex-direction:column;gap:14px;margin-top:10px}
.askq{align-self:flex-end;max-width:85%;background:var(--accent-soft);border-radius:14px 14px 4px 14px;padding:8px 12px;font-weight:600}
.aska{background:var(--surface-2);border-radius:14px;padding:12px 14px}
.aska h4{margin:10px 0 4px;font-size:15px}
.aska p{margin:6px 0}.aska ul{margin:6px 0;padding-left:20px}
.cite{display:inline-block;min-width:18px;padding:0 5px;margin:0 1px;border-radius:6px;background:var(--surface-1);
  border:1px solid var(--border);font-size:11.5px;font-weight:700;line-height:17px;text-align:center;color:var(--accent-ink);
  text-decoration:none;vertical-align:1px;cursor:pointer}
.srcs{margin:10px 0 0;padding:10px 0 0;border-top:1px solid var(--border);font-size:13.5px}
.srcs b{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.srcs ol{margin:6px 0 0;padding-left:22px}.srcs li{margin:4px 0}
.srcs li:target,.srcs li.flash{background:var(--accent-soft);border-radius:6px}
.srcs .sm{color:var(--muted)}
.tools-used{font-size:12.5px;color:var(--muted);margin-top:6px}
.askmode{display:inline-flex;gap:2px;background:var(--surface-2);border-radius:999px;padding:3px;margin-bottom:6px}
.askmode button{font:inherit;font-size:14px;font-weight:600;border:0;background:none;color:var(--muted);border-radius:999px;padding:6px 14px;cursor:pointer}
.askmode button[aria-selected="true"]{background:var(--surface-1);color:var(--text-primary);box-shadow:0 1px 2px rgba(0,0,0,.12)}
.askmode-note{margin:2px 0 10px}
.trace{margin:0 0 8px;font-size:13px;color:var(--text-secondary)}
.trace summary{cursor:pointer;color:var(--muted);font-weight:600}
.trace ol{list-style:none;margin:4px 0 0;padding:0}
.trace li{padding:3px 0 3px 22px;position:relative;border-bottom:1px dashed var(--border)}
.trace li::before{content:"↳";position:absolute;left:4px;color:var(--accent-ink)}
.trace li.live::before{content:"⋯"}
.trace .res{color:var(--muted)}
.plan{background:var(--surface-1);border:1px solid var(--border);border-radius:12px;padding:10px 12px;margin:0 0 10px}
.plan b{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.plan ol{list-style:none;margin:6px 0 0;padding:0}
.plan li{display:grid;grid-template-columns:22px 1fr;gap:4px;padding:4px 0;font-size:14px}
.plan li .ic{font-weight:700;color:var(--muted)}
.plan li.doing .ic{color:var(--accent-ink)}.plan li.done .ic{color:var(--good)}
.plan li .fd{grid-column:2;color:var(--text-secondary);font-size:13px}
"""


ASK_JS = r"""
(function(){
const D=JSON.parse(document.getElementById('askdata').textContent);
const EV=JSON.parse(document.getElementById('evdata').textContent).rows;
const COUNTRY={NL:'Netherlands',BE:'Belgium',DE:'Germany',AT:'Austria',GB:'United Kingdom',UK:'United Kingdom',FR:'France',IT:'Italy',ES:'Spain',
  CH:'Switzerland',PL:'Poland',SE:'Sweden',DK:'Denmark',IE:'Ireland',LU:'Luxembourg',NO:'Norway',FI:'Finland',PT:'Portugal',CZ:'Czechia'};
const R=D.idx.map(a=>({b:a[0],c:a[1],d:a[2],r:a[3],o:a[4],t:a[5],id:a[6]}));
const pain=t=>D.themes[t]&&D.themes[t].group==='pain_point';
const arr=v=>v==null||v===''?[]:(Array.isArray(v)?v:[v]).map(x=>String(x).trim()).filter(Boolean);
const lc=v=>arr(v).map(x=>x.toLowerCase());
const brandKey=x=>{x=x.toLowerCase();return Object.keys(D.brands).find(k=>k===x||D.brands[k].toLowerCase()===x)||x;};
function filt(rows,i){
  const bs=lc(i.brands).map(brandKey),cs=arr(i.countries).map(x=>x.toUpperCase()),ts=lc(i.themes_any||i.themes),
    st=lc(i.stages),org=String(i.origin||'').toLowerCase();
  const lo=i.min_stars!=null?Number(i.min_stars):1,hi=i.max_stars!=null?Number(i.max_stars):5;
  return rows.filter(r=>(!bs.length||bs.includes(r.b))&&(!cs.length||cs.includes(r.c))&&r.r>=lo&&r.r<=hi
    &&(!i.date_from||r.d>=i.date_from)&&(!i.date_to||r.d<=i.date_to)&&(!org||r.o===org)
    &&(!ts.length||(r.t||[]).some(t=>ts.includes(t)))&&(!st.length||(r.t||[]).some(t=>st.includes(D.themes[t]?D.themes[t].stage:'')))
  );
}
const round=(x,n=2)=>Math.round(x*10**n)/10**n;
function summary(g,want){
  const n=g.length; if(!n)return{n:0};
  const cnt={}; g.forEach(r=>r.t.forEach(t=>cnt[t]=(cnt[t]||0)+1));
  let th=Object.entries(cnt).map(([t,c])=>({theme:t,label:D.themes[t]?D.themes[t].label:t,share:round(c/n,3),n:c})).sort((a,b)=>b.n-a.n);
  const keep=new Set(lc(want)); th=th.filter((x,i)=>i<12||keep.has(x.theme));
  return{n,avg_stars:round(g.reduce((s,r)=>s+r.r,0)/n),share_1_2_stars:round(g.filter(r=>r.r<=2).length/n,3),
    share_mentioning_a_problem:round(g.filter(r=>r.t.some(pain)).length/n,3),
    share_invited:g.some(r=>r.o)?round(g.filter(r=>r.o==='invited').length/g.filter(r=>r.o).length,3):null,
    themes:th, small_sample:n<15};
}
function count_reviews(i){
  const g=filt(R,i||{}),by=String((i&&i.group_by)||'none');
  const key={brand:r=>D.brands[r.b]||r.b,country:r=>COUNTRY[r.c]||r.c,month:r=>r.d.slice(0,7),stars:r=>r.r+'★',origin:r=>r.o||'unknown'}[by];
  if(!key)return{total:g.length,...summary(g,i&&i.themes_any)};
  const m={}; g.forEach(r=>{const k=key(r);(m[k]=m[k]||[]).push(r);});
  return{total:g.length,group_by:by,groups:Object.entries(m).sort((a,b)=>by==='month'?a[0]<b[0]?-1:1:b[1].length-a[1].length).slice(0,24)
    .map(([k,v])=>({group:k,...summary(v,i&&i.themes_any)}))};
}
const seen=new Map();
function search_quotes(i){
  i=i||{}; const kw=String(i.keyword||'').toLowerCase().trim(),ts=lc(i.themes||i.themes_any),lim=Math.min(15,Math.max(1,Number(i.limit)||8));
  const ok=new Set(filt(R,{...i,themes_any:null,themes:null}).map(r=>r));
  const out=[];
  for(let k=0;k<EV.length&&out.length<lim;k++){
    const e=EV[k],r=R[e.x]; if(!ok.has(r))continue;
    if(ts.length&&!ts.includes(e.t))continue;
    if(kw&&!((e.q||'').toLowerCase().includes(kw)||(e.o||'').toLowerCase().includes(kw)))continue;
    const id='E'+k; seen.set(id,k);
    out.push({source_id:id,brand:D.brands[e.b]||e.b,country:COUNTRY[r.c]||r.c,date:e.d,stars:e.r,theme:D.themes[e.t]?D.themes[e.t].label:e.t,
      quote_en:e.q,...(e.o?{quote_original:e.o}:{})});
  }
  return{found:out.length,quotes:out,note:out.length?'Cite as [E123]':'No quotes match; try fewer filters.'};
}
window.__askTools={count_reviews,search_quotes};

const themeList=Object.entries(D.themes).map(([k,v])=>`${k} = ${v.label} (${v.group.replace('_',' ')}, stage: ${v.stage})`).join('\n');
const brandList=Object.entries(D.brands).map(([k,v])=>`${k} = ${v}${k===D.focus?' (focus brand)':''}`).join('; ');
const RULES=`You are a review analyst inside a report about walking pad brands in Europe. The reader is a customer experience lead.
Data: public Trustpilot reviews from ${D.period[0]} to ${D.period[1]}, Europe, tagged by AI with themes. Brands: ${brandList}.
Journey stages: ${Object.entries(D.stages).map(([k,v])=>k+' = '+v).join('; ')}.
Themes (key = label):
${themeList}

Tools: count_reviews (counts, averages and theme shares, with filters and group_by) and search_quotes (short quotes, max 15 words, each with a source_id).
Rules:
- Use ONLY numbers returned by the tools and quotes returned by search_quotes. No outside knowledge about any brand, no guesses about a company's internal operations.
- Look up before you answer: usually one or two count_reviews calls and one or two search_quotes calls. Compare with the market or other brands where it helps.
- Cite every quote and every claim drawn from a quote with its source id in square brackets, like [E123]. Use 2 to 6 sources. Never invent a source id.
- When a group has fewer than 15 reviews, call it a small sample or a signal.
- Never mention reviewer names or personal details.
- Answer in plain English, short: one-sentence answer first, then 2 to 5 bullets with numbers, then one line "Idea:" with a practical improvement when it fits. Use **bold** sparingly. No tables.`;

const $=id=>document.getElementById(id);
const form=$('ask-form'),q=$('ask-q'),go=$('ask-go'),stop=$('ask-stop'),neu=$('ask-new'),status=$('ask-status'),log=$('ask-log');
let sample=null,turns=[],ctl=null;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function md(text,order){
  const lines=esc(text).split('\n');let html='',inList=false;
  const inline=s=>s.replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/\[(E\d+)\]/g,(m,id)=>{
    if(!seen.has(id))return'';if(!order.includes(id))order.push(id);const n=order.indexOf(id)+1;
    return `<a class="cite" href="#" data-src="${id}" title="Source ${n}">${n}</a>`;});
  for(let l of lines){l=l.trim();
    if(/^[-*•] /.test(l)){if(!inList){html+='<ul>';inList=true;}html+='<li>'+inline(l.slice(2))+'</li>';continue;}
    if(inList){html+='</ul>';inList=false;}
    if(!l)continue;
    if(/^#{1,4} /.test(l)){html+='<h4>'+inline(l.replace(/^#+ /,''))+'</h4>';continue;}
    html+='<p>'+inline(l)+'</p>';}
  if(inList)html+='</ul>';return html;
}
function sources(order){
  if(!order.length)return'';
  return '<div class="srcs"><b>Sources</b><ol>'+order.map(id=>{const e=EV[seen.get(id)],r=R[e.x];
    return `<li data-src-item="${id}">“${esc(e.q)}”${e.o?` <span class="sm">(${esc(e.o)})</span>`:''}
      <span class="sm">· ${esc(D.brands[e.b]||e.b)}, ${esc(COUNTRY[r.c]||r.c)}, ${esc(e.d)}, ${e.r}★ ·</span>
      <a href="https://www.trustpilot.com/reviews/${esc(r.id)}" target="_blank" rel="noopener noreferrer">Open review ↗</a></li>`;}).join('')+'</ol></div>';
}
log.addEventListener('click',e=>{const a=e.target.closest('.cite');if(!a)return;e.preventDefault();
  const li=a.closest('.aska').querySelector(`[data-src-item="${a.dataset.src}"]`);if(li){li.scrollIntoView({block:'nearest'});li.classList.add('flash');setTimeout(()=>li.classList.remove('flash'),1400);}});

function busy(on){go.disabled=on;stop.hidden=!on;q.disabled=on;document.querySelectorAll('.askmode button').forEach(b=>b.disabled=on);}

// ---- plain-English description of each tool call, for the visible trace
const nm=k=>D.brands[k]||(D.themes[k]&&D.themes[k].label)||k;
function filtersText(i){
  const p=[];
  if(arr(i.brands).length)p.push(arr(i.brands).map(b=>nm(brandKey(b))).join(', '));else p.push('all brands');
  if(arr(i.countries).length)p.push(arr(i.countries).map(c=>COUNTRY[c.toUpperCase()]||c).join(', '));
  const th=arr(i.themes_any||i.themes);if(th.length)p.push('“'+th.map(nm).join('” or “')+'”');
  if(arr(i.stages).length)p.push('stage: '+arr(i.stages).map(s=>D.stages[s]||s).join(', '));
  if(i.min_stars!=null||i.max_stars!=null)p.push((i.min_stars||1)+'–'+(i.max_stars||5)+'★');
  if(i.origin)p.push(i.origin);
  if(i.date_from||i.date_to)p.push((i.date_from||'…')+' to '+(i.date_to||'…'));
  if(i.keyword)p.push('word “'+i.keyword+'”');
  return p.join(' · ');
}
function describe(name,i,r){
  i=i||{};
  if(name==='count_reviews'){const by=i.group_by&&i.group_by!=='none'?' by '+i.group_by:'';
    const res=r.groups?`${r.total} reviews in ${r.groups.length} groups`:(r.n?`${r.n} reviews, ${r.avg_stars}★ avg, ${Math.round(r.share_mentioning_a_problem*100)}% mention a problem`:'no reviews');
    return['Counted '+filtersText(i)+by,res];}
  if(name==='search_quotes')return['Searched quotes: '+filtersText(i),`${r.found} found`];
  if(name==='problem_vault')return['Opened the Problem Vault',`top ${r.length} problems`];
  if(name==='make_plan')return['Wrote a plan',`${arr(i.steps).length} steps`];
  if(name==='complete_step')return['Finished step '+i.step,''];
  if(name==='pattern_check')return['Checked if “'+nm(i.theme)+'” is recurring (last '+(i.days||30)+' days)',r.mentioning_theme!=null?`${r.mentioning_theme} of ${r.reviews_in_window} reviews`:''];
  if(name==='submit_triage')return['Wrote the triage and draft reply',''];
  return[name,''];
}
function traced(box,name,fn){
  return async i=>{
    if(name==='complete_step')return fn(i);
    const li=document.createElement('li');li.className='live';li.textContent=describe(name,i,{found:0,groups:null,n:0,length:0})[0]+'…';
    box.ol.append(li);box.el.hidden=false;box.n++;box.sum.textContent=`Agent steps (${box.n})`;(box.status||status).textContent=li.textContent;
    try{const r=await fn(i);const [a,b]=describe(name,i,r);li.className='';li.innerHTML=esc(a)+(b?` <span class="res">→ ${esc(b)}</span>`:'');return r;}
    catch(err){li.className='';li.innerHTML=esc(li.textContent)+' <span class="res">→ error</span>';throw err;}
  };
}
function newTrace(parent,st){
  const el=document.createElement('details');el.className='trace';el.open=true;el.hidden=true;
  const sum=document.createElement('summary');sum.textContent='Agent steps';const ol=document.createElement('ol');
  el.append(sum,ol);parent.append(el);return{el,ol,sum,n:0,status:st};
}

// ---- tool definitions
const T_COUNT={name:'count_reviews',description:'Counts reviews matching filters and returns n, average stars, share of 1-2 star reviews, share mentioning a problem, share invited, and the most common themes with their share. Use group_by to compare brands, countries, months, star ratings or invited vs organic.',
   inputSchema:{type:'object',properties:{brands:{type:'array',items:{type:'string'},description:'brand keys'},countries:{type:'array',items:{type:'string'},description:'ISO codes, e.g. NL, DE, BE, AT, GB'},
     themes_any:{type:'array',items:{type:'string'},description:'keep reviews that mention any of these theme keys'},stages:{type:'array',items:{type:'string'},description:'keep reviews with a theme in these journey stages'},
     min_stars:{type:'integer'},max_stars:{type:'integer'},origin:{type:'string',enum:['invited','organic']},date_from:{type:'string',description:'YYYY-MM-DD'},date_to:{type:'string'},
     group_by:{type:'string',enum:['none','brand','country','month','stars','origin']}}},fn:count_reviews};
const T_QUOTES={name:'search_quotes',description:'Finds short evidence quotes (max 15 words, English, plus the original language) with brand, country, date and stars, newest first. Each has a source_id to cite like [E123].',
   inputSchema:{type:'object',properties:{brands:{type:'array',items:{type:'string'}},countries:{type:'array',items:{type:'string'}},themes:{type:'array',items:{type:'string'},description:'theme keys'},
     keyword:{type:'string',description:'one word or short phrase to find in the quote'},min_stars:{type:'integer'},max_stars:{type:'integer'},origin:{type:'string',enum:['invited','organic']},limit:{type:'integer',description:'1-15, default 8'}}},fn:search_quotes};
const T_VAULT={name:'problem_vault',description:'The focus brand\'s top 5 problems in the last 6 months, ranked by the stars they cost, with owner team, journey stage, share of the brand\'s reviews vs the market, and which problems usually appear together.',
   inputSchema:{type:'object',properties:{}},fn:()=>D.vault};

function toolsFor(mode,box,plan){
  const list=[T_COUNT,T_QUOTES,T_VAULT];
  const out=list.map(t=>({name:t.name,description:t.description,inputSchema:t.inputSchema,execute:traced(box,t.name,t.fn)}));
  if(mode==='inv'){
    out.unshift({name:'make_plan',description:'Call FIRST, once. Write the investigation plan: 3 to 5 short steps, each one thing you will check with the data tools. The last step must be a check that challenges your main finding.',
      inputSchema:{type:'object',properties:{steps:{type:'array',items:{type:'string'},minItems:3,maxItems:5}},required:['steps']},
      execute:traced(box,'make_plan',i=>{plan.set(arr(i.steps));return{ok:true,note:'Plan shown to the reader. Work through it and call complete_step after each step.'};})});
    out.push({name:'complete_step',description:'Call after finishing each plan step, with what you found in one sentence with a number.',
      inputSchema:{type:'object',properties:{step:{type:'integer',description:'1-based step number'},finding:{type:'string'}},required:['step','finding']},
      execute:traced(box,'complete_step',i=>{plan.done(Number(i.step),String(i.finding||''));return{ok:true};})});
  }
  return out;
}
function newPlan(parent){
  const el=document.createElement('div');el.className='plan';el.hidden=true;
  el.innerHTML='<b>Plan</b><ol></ol>';parent.append(el);const ol=el.querySelector('ol');let items=[];
  return{set(steps){ol.innerHTML='';items=steps.map((s,k)=>{const li=document.createElement('li');
      li.innerHTML=`<span class="ic">${k+1}</span><span>${esc(s)}</span>`;ol.append(li);return li;});el.hidden=false;
      if(items[0])items[0].className='doing';},
    done(n,f){const li=items[n-1];if(!li)return;li.className='done';li.querySelector('.ic').textContent='✓';
      const d=document.createElement('span');d.className='fd';d.textContent=f;li.append(d);
      const next=items.find(x=>!x.className);if(next)next.className='doing';}};
}

const INV_RULES=RULES.replace(/- Answer in plain English[\s\S]*$/,'')+`- You are investigating a GOAL, not answering a quick question. Work like an analyst:
  1. Call make_plan first with 3 to 5 steps.
  2. Work through the steps with count_reviews, search_quotes and problem_vault. After each step call complete_step with one sentence and a number.
  3. The last step challenges your main finding: compare with the market or other brands, an earlier period, or invited vs organic reviews, and say whether it still holds.
- Then write the result in plain English, in this order, with these bold labels on their own lines:
**Conclusion** - two sentences.
**Evidence** - 3 to 5 bullets with numbers and sources.
**What to do first** - one action a CX lead can start within 30 days, the owner team, and the number to watch to know it works.
**Limits** - one sentence on what this data cannot tell (for example small samples, or that reviews are not all customers).
Use 3 to 6 sources. No tables.`;

let mode='ask';
document.querySelectorAll('.askmode button').forEach(b=>b.addEventListener('click',()=>{
  mode=b.dataset.mode;
  document.querySelectorAll('.askmode button').forEach(x=>x.setAttribute('aria-selected',x===b?'true':'false'));
  document.querySelectorAll('.askchip,.askmode-note').forEach(c=>c.hidden=c.dataset.mode!==mode);
  q.placeholder=mode==='inv'?'e.g. Find why Belgian customers rate Moov lower, and what to fix first.':q.dataset.ph;
}));
q.dataset.ph=q.placeholder;

let tally={count:0,quotes:0};
async function ask(text){
  text=text.trim(); if(!text||!sample)return;
  const m=mode;
  const qa=document.createElement('div');qa.className='askq';qa.textContent=(m==='inv'?'Goal: ':'')+text;log.append(qa);
  const ans=document.createElement('div');ans.className='aska';log.append(ans);
  const plan=m==='inv'?newPlan(ans):null;const box=newTrace(ans);
  const body=document.createElement('div');body.innerHTML='<p class="muted">Thinking…</p>';ans.append(body);
  ans.scrollIntoView({block:'nearest'});
  if(m==='inv')turns=[];
  turns.push({role:'user',content:(m==='inv'?'GOAL: ':'')+text}); if(turns.length>9)turns=turns.slice(-9);
  ctl=new AbortController();busy(true);status.textContent='Thinking…';q.value='';
  const order=[];
  try{
    const res=await sample([{role:'user',content:m==='inv'?INV_RULES:RULES},...turns],{tools:toolsFor(m,box,plan),cache:false,signal:ctl.signal,
      modelTier:m==='inv'?'complex':'default',onText:({text})=>{body.innerHTML=md(text,order);}});
    body.innerHTML=md(res.text,order)+sources(order)+(res.truncated?'<p class="tools-used">Answer cut short.</p>':'');
    box.el.open=false;
    turns.push({role:'assistant',content:res.text});neu.hidden=false;status.textContent='';
  }catch(e){
    turns.pop();
    if(e&&e.text)body.innerHTML=md(e.text,order)+sources(order);else if(!box.n)ans.remove();else body.innerHTML='';
    const msg={cancelled:'Stopped.',not_granted:'Claude is not allowed on this page for you, so questions are off.',sampling_disabled:'Claude is not available for this account.',
      rate_limited:'Too many questions right now. Try again in a little while.',refused:'Claude declined this question. Try rephrasing it.',
      tools_unavailable:'This view cannot run the agent tools.',session_expired:'Please sign in to claude.ai again.'}[e&&e.code]||'Something went wrong. Try again.';
    status.textContent=msg;
    if(['not_granted','sampling_disabled','tools_unavailable','not_declared','capability_disabled'].includes(e&&e.code)){form.hidden=true;$('ask-off').hidden=false;}
  }finally{busy(false);ctl=null;}
}
form.addEventListener('submit',e=>{e.preventDefault();ask(q.value);});
q.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask(q.value);}});
document.querySelectorAll('.askchip').forEach(c=>c.addEventListener('click',()=>{if(!go.disabled)ask(c.textContent);}));
window.__agent={D,R,EV,arr,esc,COUNTRY,traced,newTrace,T_VAULT,get sample(){return sample;}};
stop.addEventListener('click',()=>ctl&&ctl.abort());
neu.addEventListener('click',()=>{turns=[];log.innerHTML='';neu.hidden=true;status.textContent='';});

busy(true);status.textContent='Connecting…';
(async()=>{
  const s=window.claude&&await window.claude.use('sample').catch(()=>null);
  const lim=s&&await s.limits().catch(()=>null);
  if(!s||(lim&&!lim.tools)){busy(false);go.disabled=true;form.hidden=true;$('ask-off').hidden=false;status.textContent='';
    document.querySelectorAll('.askchip').forEach(c=>c.disabled=true);return;}
  sample=s;busy(false);status.textContent='';
})();
})();
"""


def ask_json(data):
    return json.dumps(ask_data(data), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
