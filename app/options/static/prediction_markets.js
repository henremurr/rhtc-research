
'use strict';
const el=id=>document.getElementById(id),pageSize=50;let offset=0,total=0,serial=0,deduplicate=false,activeRequest,lastResultsKey='';
function line(parent,label,value){if(value===null||value===undefined||value===''||Array.isArray(value)&&!value.length)return;const p=document.createElement('p'),b=document.createElement('strong');b.textContent=label+': ';p.append(b,document.createTextNode(String(value)));parent.append(p)}
const pct=n=>Number.isFinite(n)?(n*100).toFixed(1)+'%':'Unavailable';
function render(m){const a=document.createElement('article'),h=document.createElement('h2');h.textContent=m.title;a.append(h);line(a,'Provider',m.provider==='kalshi'?'Kalshi':'Polymarket');line(a,'Classification',m.topics.join(' · ')||'Unclassified');line(a,'Market-implied probabilities',Object.entries(m.probabilities).map(([k,v])=>k+' '+pct(v)).join(' · ')||'Unavailable');line(a,'Relevance',m.relevance===null?'Semantic review pending':m.relevance+'/10');line(a,'Market quality',m.quality);line(a,'Liquidity / 24h volume',String(m.liquidity??'Unavailable')+' '+(m.liquidity_unit||'')+' / '+String(m.volume24h??'Unavailable')+' '+(m.volume_unit||''));line(a,'Open interest',m.open_interest==null?null:String(m.open_interest)+' '+(m.open_interest_unit||''));line(a,'Bid-ask spread',pct(m.spread));for(const d of ['1','7','30'])line(a,d+'-day change',Object.entries(m.changes_pp?.[d]||{}).map(([k,v])=>k+' '+(v>0?'+':'')+v+' pp').join(' · ')||'Insufficient history');line(a,'Event end date',m.end_date);line(a,'Watchlist research candidates',m.watchlist_matches);line(a,'Outside-watchlist candidates (unverified)',m.outside_candidates);line(a,'Recorded holdings possibly affected',m.holdings.map(x=>x.symbol+' — '+(x.account||'Unassigned')+' — '+x.quantity+' shares'+(x.call_expiration?' — call expiry '+x.call_expiration:'')+(x.additional_calls?.length?' — '+x.additional_calls.length+' additional call records':'')));line(a,'Broad thematic exposure (not direct links)',m.thematic_exposure);if(m.research){line(a,'Company research candidates',m.research.companies);line(a,'Opportunity hypothesis',m.research.opportunity);line(a,'Risk hypothesis',m.research.risk);line(a,'Independent confirmation required',m.research.confirmation);line(a,'Resolution clarity (AI assessment)',m.research.resolution_clarity)}const d=document.createElement('details'),s=document.createElement('summary');s.textContent='Resolution rules and source';d.append(s);line(d,'Rules',m.description||'Unavailable');line(d,'Resolution source',m.resolution_source||'Unavailable');line(d,'Provider market ID',m.id);if(m.provider!=='kalshi'&&m.slug&&/^[a-zA-Z0-9_-]+$/.test(m.slug)){const link=document.createElement('a');link.href='https://polymarket.com/market/'+m.slug;link.textContent='Original market reference';link.target='_blank';link.rel='noopener noreferrer';d.append(link)}a.append(d);return a}
async function load(){
const request=++serial;
activeRequest?.abort();
const controller=new AbortController();
activeRequest=controller;
const timeout=setTimeout(()=>controller.abort(),25000);
el('status').textContent='Loading saved research…';
try{const params=new URLSearchParams({provider:el('provider').value,topic:el('topic').value,exposure:el('exposure').value,q:el('search').value,sort:el('sort').value,offset,limit:pageSize,deduplicate});
const resultsKey=params.toString();
if(resultsKey!==lastResultsKey){
  el('rows').replaceChildren();
  total=0;
  el('prev').disabled=true;
  el('next').disabled=true;
}
const r=await fetch('/options/api/prediction-markets?'+params,{cache:'no-store',signal:controller.signal});if(!r.ok)throw Error('Unable to retrieve market research ('+r.status+')');const data=await r.json();if(request!==serial)return;lastResultsKey=resultsKey;total=data.count;el('rows').replaceChildren(...data.markets.map(render));if(data.index_pending){el('status').textContent='Catalog indexing in progress. '+total.toLocaleString()+' contracts retained; results will be available after indexing.';el('prev').disabled=true;el('next').disabled=true;return;}
if(data.scan&&total===0){
  const empty=document.createElement('p');
  empty.textContent=data.direct_search?'No contracts directly match the search and current filters.':'No markets match the current filters.';
  el('rows').append(empty);
}
el('status').textContent=(data.scan?(data.scan.partial?'Partial scan started: ':'Last complete scan: ')+new Date(data.scan.stamp).toLocaleString()+' · '+data.scan.count+' markets discovered · '+data.reviewed+(data.direct_search?' matching contracts semantically reviewed · Showing ':' semantically reviewed · Showing ')+(total?offset+1:0)+'–'+Math.min(offset+pageSize,total)+' of '+total:'No completed scan yet')+(data.scanning?' · Scan running':'')+(data.reviewing?' · Semantic review running':'');if(deduplicate)el('status').textContent+=' · '+(data.duplicates_removed||0).toLocaleString()+' duplicate contracts hidden';const st=data.scan_status;if(st){el('status').textContent+=' · Scan status: '+(st.state==='running'&&!data.scanning?'Interrupted or stale':st.state)+' · '+(st.pages??0)+' pages · '+(st.discovered??0)+' markets retrieved'+(st.error?' · '+st.error:'');}if(data.kalshi_status){const ks=data.kalshi_status;el('status').textContent+=' · Kalshi: '+ks.state+(ks.error?' · '+ks.error:'');const kscan=data.provider_scans?.kalshi;if(kscan)el('status').textContent+=' · '+kscan.count+' markets · '+new Date(kscan.stamp).toLocaleString();}const rs=data.research_status;if(rs){el('status').textContent+=' · Research: '+rs.state+(rs.reviewed!=null?' · '+rs.reviewed+' saved this cycle':'')+(rs.pending!=null?' · '+rs.pending+' pending':'')+(rs.reason?' · '+rs.reason:'');}const u=data.ai_usage;if(u){el('status').textContent+=' · AI today: '+u.requests+'/'+u.request_limit+' requests · '+(u.input_tokens+u.output_tokens).toLocaleString()+' tokens'+(u.estimated_usd==null?' · Cost unavailable':' · Estimated cost USD '+u.estimated_usd.toFixed(4))+(u.in_flight?' · '+u.in_flight+' in progress':'')+(u.unresolved_usage?' · '+u.unresolved_usage+' unresolved usage':'')+(u.rejected?' · '+u.rejected+' rejected':'');}el('refresh').disabled=data.scanning;el('prev').disabled=offset===0;el('next').disabled=offset+pageSize>=total}catch(e){
  if(request===serial)el('status').textContent=controller.signal.aborted?'The request timed out. Tap Reload results to retry.':e.message;
}finally{
  clearTimeout(timeout);
  if(activeRequest===controller)activeRequest=null;
}}
el('apply').onclick=el('provider').onchange=el('sort').onchange=()=>{offset=0;load()};
el('search').addEventListener('keydown',event=>{
  if(event.key==='Enter'){
    event.preventDefault();
    el('apply').click();
  }
});el('prev').onclick=()=>{offset=Math.max(0,offset-pageSize);load()};el('next').onclick=()=>{if(offset+pageSize<total){offset+=pageSize;load()}};el('reload').onclick=load;
el('deduplicate').onclick=()=>{
  deduplicate=!deduplicate;
  el('deduplicate').setAttribute('aria-pressed',String(deduplicate));
  el('deduplicate').textContent=deduplicate?'Show duplicates':'Remove duplicates';
  offset=0;
  load();
};
el('print').onclick=()=>window.print();el('refresh').onclick=async()=>{el('refresh').disabled=true;try{const r=await fetch('/options/api/prediction-markets/refresh?'+new URLSearchParams({provider:el('provider').value}),{method:'POST'});if(!r.ok)throw Error('Refresh unavailable ('+r.status+')');el('status').textContent='Scan queued. Previously saved data remains available.';setTimeout(load,2000)}catch(e){el('status').textContent=e.message}finally{el('refresh').disabled=false}};load();setInterval(()=>{if(!document.hidden&&!deduplicate&&!activeRequest&&!el('search').value.trim())load()},60000);
