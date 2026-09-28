const $ = (s) => document.querySelector(s);
const state = {peak:'All Peaks', query:'', sort:'income', rows:[], source:'demo', mode:'overview', selectedOnly:false, costOnly:false, expirationSet:1, scanLimit:10, watchlist:[], editingSymbol:null, migrationOpen:false, editingEnabled:false, legacyWatchlist:null, chainDescription:''};
const DTE_WINDOWS=['0–7 DTE','8–14 DTE','15–21 DTE','22+ DTE'];
const WATCHLIST_KEY='rhtc-options-watchlist';
const peakMeta = {'AI/I':{label:'AI / Infrastructure',cls:'ai'},'EFM/I':{label:'Energy / Infrastructure',cls:'efm'},'DS/I':{label:'Defense / Space',cls:'defense'},'Other':{label:'Outside the Peaks',cls:'other'}};
// Curated focus symbols; this is not a verified position ledger.
const held = new Set(['MU','OKLO','VG','RDW','RKLB','SMCI','RGTI','UMAC','ORCL','MRVL','ET','CCJ','XTND','OPTX']);
const fmt = (n,d=2) => Number(n||0).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
function changeClass(value){const n=Number(value);return !Number.isFinite(n)||n===0?'':n>0?'positive':'negative'}
function changeText(value,unit){const n=Number(value);if(value===null||value===undefined||value===''||!Number.isFinite(n))return '—';const sign=n>0?'+':n<0?'−':'';return unit==='$'?`${sign}$${fmt(Math.abs(n))}`:`${sign}${fmt(Math.abs(n))}%`}
function quantityForPrice(price){const raw=$('#max-last').value.trim();const ceiling=raw===''?NaN:Number(raw);const last=Number(price);return Number.isFinite(ceiling)&&Number.isFinite(last)&&last>0?Math.trunc(ceiling/last):1}
function incomeForRow(row){const bid=Number(row.bid),ask=Number(row.ask);if(row.error||!Number.isFinite(bid)||!Number.isFinite(ask))return null;return ((bid+ask)/2)*100*quantityForPrice(row.price)}
function contractLabel(r){const expiry=String(r.expiry||'').replaceAll('-','');const strike=Number(r.strike);if(/^\d{8}$/.test(expiry)&&Number.isFinite(strike)){let value=String(strike);if(value.includes('e'))value=strike.toFixed(8).replace(/0+$/,'').replace(/\.$/,'');if(!value.includes('.'))value+='.0';return `${expiry}-${value}`}return r.contract||`${r.symbol} ${r.expiry} $${r.strike} C`}
function safe(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function analysisInline(text){return safe(text).replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>')}
function renderAnalysis(text){
  const lines=String(text||'').replace(/\r/g,'').split('\n'),html=[];let list=null;
  const closeList=()=>{if(list){html.push(`</${list}>`);list=null}};
  for(const raw of lines){const line=raw.trim();if(!line){closeList();continue}const heading=line.match(/^#{1,3}\s+(.+)$/);if(heading){closeList();const plain=/^in plain english$/i.test(heading[1].trim());html.push(`<h3${plain?' class="plain-verdict-heading"':''}>${analysisInline(heading[1])}</h3>`);continue}const bullet=line.match(/^[-*]\s+(.+)$/);const numbered=line.match(/^\d+[.)]\s+(.+)$/);if(bullet||numbered){const wanted=numbered?'ol':'ul';if(list!==wanted){closeList();list=wanted;html.push(`<${list}>`)}html.push(`<li>${analysisInline((bullet||numbered)[1])}</li>`);continue}closeList();html.push(`<p>${analysisInline(line)}</p>`)}closeList();return html.join('')}
function setTheme(theme,persist=true){const dark=theme==='dark';document.documentElement.dataset.theme=dark?'dark':'light';const button=$('#theme-toggle');button.textContent=dark?'☀':'☾';button.setAttribute('aria-label',dark?'Switch to light mode':'Switch to dark mode');button.title=dark?'Switch to light mode':'Switch to dark mode';if(persist){try{localStorage.setItem('rhtc-options-theme',dark?'dark':'light')}catch(e){}}}
try{if(localStorage.getItem('rhtc-options-theme')==='dark')setTheme('dark',false)}catch(e){}
function setSidebarCollapsed(collapsed,persist=true){const sidebar=$('.sidebar');const button=$('#sidebar-toggle');sidebar.classList.toggle('collapsed',collapsed);button.textContent=collapsed?'›':'‹';button.setAttribute('aria-expanded',String(!collapsed));button.setAttribute('aria-label',collapsed?'Expand navigation':'Collapse navigation');button.title=collapsed?'Expand navigation':'Collapse navigation';if(persist){try{localStorage.setItem('rhtc-sidebar-collapsed',collapsed?'true':'false')}catch(e){}}}
try{setSidebarCollapsed(localStorage.getItem('rhtc-sidebar-collapsed')==='true',false)}catch(e){}
function toast(msg){const el=$('#toast');el.textContent=msg;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2800)}
function peakChip(peak){const m=peakMeta[peak]||peakMeta.Other;return `<span class="peak-chip ${m.cls}"><i class="mini-dot"></i>${safe(peak)}</span>`}
function peakName(peak){return ({'AI/I':'AI / Infrastructure','EFM/I':'Energy / Infrastructure','DS/I':'Defense / Space','Other':'Outside the Peaks'})[peak]||peak}
function updateWatchlistCounts(){const counts={'AI/I':0,'EFM/I':0,'DS/I':0,'Other':0};state.watchlist.forEach(r=>counts[r.peak]=(counts[r.peak]||0)+1);$('#universe-value').innerHTML=`${state.watchlist.length} <small>symbols</small>`;$('#count-overview').textContent=state.watchlist.length;$('#count-all').textContent=state.watchlist.length;$('#count-holdings').textContent=state.watchlist.filter(hasHoldingCost).length;$('#count-ai').textContent=counts['AI/I'];$('#count-efm').textContent=counts['EFM/I'];$('#count-ds').textContent=counts['DS/I'];$('#count-other').textContent=counts.Other}
function updateStorageNote(){const note=$('#symbol-storage-status');note.textContent=state.editingEnabled?'This shared list is saved on the RHTC server and appears in every browser.':'Shared editing is locked until Railway has RHTC_WATCHLIST_ADMIN_TOKEN and a persistent Volume mounted at /data (RHTC_DATA_DIR=/data).';$('#import-browser-list').hidden=!(state.migrationOpen&&Array.isArray(state.legacyWatchlist)&&state.legacyWatchlist.length)}
async function initializeWatchlist(){try{const response=await fetch('/options/api/watchlist');if(!response.ok)throw Error('Watchlist unavailable');const data=await response.json();state.watchlist=data.rows;state.migrationOpen=Boolean(data.migration_open);state.editingEnabled=Boolean(data.editing_enabled);try{const saved=JSON.parse(localStorage.getItem(WATCHLIST_KEY)||'null');if(state.migrationOpen&&Array.isArray(saved))state.legacyWatchlist=saved}catch(e){}updateWatchlistCounts();updateStorageNote()}catch(e){toast('Could not load the shared RHTC symbol list.');state.watchlist=[];updateWatchlistCounts()}loadRows({ai:true,snapshot:false})}
function setSymbolError(message=''){$('#symbol-error').textContent=message}
function hasHoldingCost(r){return r.share_price!==null&&r.share_price!==undefined&&r.share_price!==''&&r.quantity!==null&&r.quantity!==undefined&&r.quantity!==''&&Number.isFinite(Number(r.share_price))&&Number.isFinite(Number(r.quantity))}
function holdingDetails(r){const qty=r.quantity==null||r.quantity===''?'':`${fmt(r.quantity,Number.isInteger(Number(r.quantity))?0:2)} shares`;const price=r.share_price==null||r.share_price===''?'':`$${fmt(r.share_price)}/share`;return [qty,price].filter(Boolean).join(' · ')||'No share details'}
function optionalNumber(input){return input.value.trim()===''?null:Number(input.value)}
function renderSymbolList(){const query=$('#symbol-filter').value.trim().toUpperCase();const peak=$('#symbol-peak-filter').value;const symbols=state.watchlist.filter(r=>(!query||r.symbol.includes(query))&&(peak==='All'||r.peak===peak)).slice().sort((a,b)=>a.symbol.localeCompare(b.symbol,undefined,{sensitivity:'base',numeric:true}));$('#symbol-count').textContent=peak==='All'?`${symbols.length} symbols · sorted A–Z`:`${symbols.length} ${peakName(peak)} symbols · sorted A–Z`;
$('#symbol-list').innerHTML=symbols.map(r=>{const editing=state.editingSymbol===r.symbol;if(editing)return `<div class="symbol-entry editing" data-symbol="${safe(r.symbol)}"><input class="symbol-edit-ticker" aria-label="Ticker" maxlength="10" value="${safe(r.symbol)}"><select class="symbol-edit-peak" aria-label="Peak">${peakOptions(r.peak)}</select><input class="symbol-edit-price" aria-label="Share price" type="number" min="0" step="any" placeholder="Share price" value="${safe(r.share_price??'')}"><input class="symbol-edit-quantity" aria-label="Quantity" type="number" min="0" step="any" placeholder="Quantity" value="${safe(r.quantity??'')}"><button type="button" data-action="save">Save</button><button type="button" class="secondary" data-action="cancel">Cancel</button></div>`;return `<div class="symbol-entry" data-symbol="${safe(r.symbol)}"><div class="symbol-description"><b>${safe(r.symbol)}</b><small>${safe(peakName(r.peak))}</small><small>${safe(holdingDetails(r))}</small></div><div class="symbol-actions"><button type="button" data-action="edit" aria-label="Edit ${safe(r.symbol)}">Edit</button><button type="button" class="danger" data-action="delete" aria-label="Delete ${safe(r.symbol)}">Delete</button></div></div>`}).join('')||'<div class="symbol-empty">No symbols match that search.</div>'}
function peakOptions(selected){return [['AI/I','AI / Infrastructure'],['EFM/I','Energy / Infrastructure'],['DS/I','Defense / Space'],['Other','Outside the Peaks']].map(([value,label])=>`<option value="${value}"${selected===value?' selected':''}>${label}</option>`).join('')}
function openSymbols(){state.editingSymbol=null;setSymbolError();$('#symbol-filter').value='';$('#symbol-peak-filter').value='All';renderSymbolList();$('#symbols-modal').classList.add('open')}
function drawPeakBars(){$('#screened-total').textContent=`${state.rows.length} SCREENED`;const counts={'AI/I':0,'EFM/I':0,'DS/I':0,'Other':0};state.rows.forEach(r=>counts[r.peak]=(counts[r.peak]||0)+1);const max=Math.max(...Object.values(counts));$('#peak-bars').innerHTML=Object.entries(counts).map(([p,n])=>{let m=peakMeta[p];return `<div class="peak-bar-row"><span class="peak-bar-label">${m.label}</span><div class="bar-track"><div class="bar-fill ${m.cls}" style="width:${Math.max(2,n/max*100)}%"></div></div><span class="bar-num">${n}</span></div>`}).join('')}
function renderRows(){
  let rows=state.rows.filter(r=>(!state.selectedOnly||held.has(r.symbol))&&(!state.costOnly||hasHoldingCost(r)));
  if(state.mode==='history'){
    const history=JSON.parse(localStorage.getItem('rhtc-option-history')||'[]');
    rows=history.flatMap(s=>s.rows.map(r=>({...r,historyAt:s.at}))).filter(r=>(state.peak==='All Peaks'||r.peak===state.peak)&&r.symbol.toUpperCase().includes(state.query.toUpperCase()));
  }else if(state.sort==='income'){
    rows.sort((a,b)=>{const ai=incomeForRow(a),bi=incomeForRow(b);if(ai===null)return bi===null?0:1;if(bi===null)return -1;return bi-ai});
  }
  rows=rows.filter(r=>!r.error);
  if(!rows.length){$('#rows').innerHTML=`<tr><td colspan="12" class="empty">${state.mode==='history'?'No saved snapshots on this browser yet. Refresh quotes to start a local history.':'No symbols with call data match the selected filters.'}</td></tr>`;$('#showing').textContent='0 rows';return}
  const subset=state.mode==='history'?rows.slice().reverse().slice(0,180):rows;
  $('#rows').innerHTML=subset.map(r=>{
    const error=r.error,yieldVal=Number(r.premium_yield||0),qtyValue=error?null:quantityForPrice(r.price),qty=qtyValue===null?'—':qtyValue.toLocaleString(),income=incomeForRow(r);
    const cost=r.share_price!==null&&r.share_price!==undefined&&r.share_price!==''&&Number.isFinite(Number(r.share_price))?Number(r.share_price):null;
    const askYield=Number(r.price)>0&&Number(r.ask)>0?Number(r.ask)/Number(r.price)*100:null;
    return `<tr><td data-label="Ticker"><div class="ticker"><button class="ticker-details-btn" title="View ${safe(r.symbol)} option details" aria-label="View ${safe(r.symbol)} option details" onclick="viewChain('${safe(r.symbol)}')">${safe(r.symbol)}</button><button class="ticker-ai-btn" type="button" title="Open ChatGPT deep analysis for ${safe(r.symbol)}" aria-label="Open ChatGPT deep analysis for ${safe(r.symbol)}" onclick="analyzeSymbol('${safe(r.symbol)}')"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5 14.4 9.6 21.5 12l-7.1 2.4L12 21.5l-2.4-7.1L2.5 12l7.1-2.4L12 2.5Z"/><path d="m19 2 .8 2.2L22 5l-2.2.8L19 8l-.8-2.2L16 5l2.2-.8L19 2Z"/></svg></button></div></td><td data-label="Peak">${peakChip(r.peak)}</td><td data-label="Last"><span class="number">$${fmt(r.price)}</span></td><td data-label="Change $"><span class="change-value ${changeClass(r.change)}">${changeText(r.change,'$')}</span></td><td data-label="Change %"><span class="change-value ${changeClass(r.change_pct)}">${changeText(r.change_pct,'%')}</span></td><td data-label="Cost"><span class="number">${cost===null?'—':`$${fmt(cost)}`}</span></td><td data-label="Call contract"><div class="contract"><b>${safe(contractLabel(r))}</b><small>${r.dte??'—'} DTE${r.historyAt?` · saved ${new Date(r.historyAt).toLocaleDateString()}`:''}</small></div></td><td data-label="Qty"><span class="number">${qty}</span></td><td data-label="Bid / ask" class="quote"><span class="bid">$${fmt(r.bid)}</span> / $${fmt(r.ask)}<small class="quote-size">${r.bid_size??0} × ${r.ask_size??0}</small></td><td data-label="Bid / ask yield"><span class="yield-pill ${yieldVal>1.5?'high':''}">${fmt(yieldVal)}% / ${askYield===null?'—':fmt(askYield)+'%'}</span></td><td data-label="Income"><span class="number">${income===null?'—':`$${fmt(income)}`}</span></td><td data-label="OI / Vol"><span class="oi">${Number(r.open_interest||0).toLocaleString()} / ${Number(r.volume||0).toLocaleString()}</span></td></tr>`
  }).join('');
  $('#showing').textContent=state.mode==='history'?`${subset.length} saved rows`:`Showing ${rows.length} screened symbols`;
}
function updateStats(){let good=state.rows.filter(r=>!r.error&&Number.isFinite(Number(r.premium_yield)));let sorted=good.map(r=>Number(r.premium_yield)).sort((a,b)=>a-b);let mid=sorted.length?sorted[Math.floor(sorted.length/2)]:0;$('#review-value').innerHTML=`${good.length} <small>calls</small>`;$('#median-value').innerHTML=`${fmt(mid)} <small>%</small>`;const stamp=new Date();$('#asof-value').textContent=stamp.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',timeZone:'America/Los_Angeles'});$('#asof-date').textContent=stamp.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'America/Los_Angeles'});$('#foot-source').textContent=`Data mode: ${state.source}`;$('#source-pill').innerHTML=`<span class="source-dot"></span> ${state.source==='tradier_sandbox'?'TRADIER SANDBOX · DELAYED':state.source==='tradier'?'TRADIER QUOTES':'DEMO DATA'}`;$('#provider-side').textContent=state.source==='tradier_sandbox'?'Tradier sandbox · delayed':state.source==='tradier'?'Tradier · connected':'Demo mode · sample values';$('#modal-mode').textContent=state.source==='tradier_sandbox'?'Sandbox · delayed':state.source==='tradier'?'Tradier connected':'Demo';$('#demo-alert').style.display=state.source==='demo'?'flex':'none';}
async function loadRows({ai=false,snapshot=false}={}){const btn=$('#refresh');btn.disabled=true;$('.refresh-icon').classList.add('spin');$('#rows').innerHTML='<tr><td colspan="12" class="loading">Loading the RHTC option screen…</td></tr>';try{const p=new URLSearchParams({peak:state.peak,q:state.query,sort:state.sort,limit:String(state.scanLimit),expiration_set:String(state.expirationSet),holdings_only:String(state.costOnly)});const maxLast=$('#max-last').value.trim();if(maxLast!=='')p.set('max_last',maxLast);const res=await fetch(`/options/api/opportunities?${p}`);if(!res.ok)throw Error(await res.text());const data=await res.json();state.rows=data.rows;state.source=data.source;updateStats();drawPeakBars();renderRows();if(snapshot)saveSnapshot();if(ai)await loadSummary();}catch(e){$('#rows').innerHTML=`<tr><td colspan="12" class="empty">Could not load data: ${safe(e.message)}. Check the server connection and try again.</td></tr>`;toast('Refresh failed. See the table message.')}finally{btn.disabled=false;$('.refresh-icon').classList.remove('spin')}}
function saveSnapshot(){if(!state.rows.length)return;const history=JSON.parse(localStorage.getItem('rhtc-option-history')||'[]');history.push({at:new Date().toISOString(),rows:state.rows.map(({symbol,peak,price,change,change_pct,strike,expiry,dte,bid,ask,premium_yield,delta,iv,open_interest,volume,bid_size,ask_size,quote_time,contract,share_price,quantity})=>({symbol,peak,price,change,change_pct,strike,expiry,dte,bid,ask,premium_yield,delta,iv,open_interest,volume,contract,share_price,quantity}))});localStorage.setItem('rhtc-option-history',JSON.stringify(history.slice(-12)))}
async function loadSummary(){let text=$('#ai-summary-text');if(!text)return;text.innerHTML='<span class="summary-loading">Reviewing the latest screen…</span>';try{const response=await fetch('/options/api/summary',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:state.source,rows:state.rows})});const data=await response.json();text.textContent=data.summary;$('#ai-summary-mode').textContent=data.mode==='openai'?'OPENAI SUMMARY':'RULE-BASED SUMMARY';}catch(e){text.textContent='Summary is unavailable. The quote table remains available for review.'}}
function renderChainPage(){
  const x=state.chainRows[state.chainIndex];
  if(!x)return;
  $('#chain-page').textContent=DTE_WINDOWS[state.chainIndex]||x.dte_window||'';
  $('#chain-prev').disabled=state.chainIndex===0;
  $('#chain-next').disabled=state.chainIndex===state.chainRows.length-1;
  if(x.error){
    $('#detail-subtitle').textContent='';
    $('#detail-content').innerHTML='<p class="error-text">'+safe(x.error)+'</p>';
    return;
  }
  $('#detail-subtitle').textContent='';
  $('#detail-content').innerHTML=
    '<div class="detail-call-block">'+
      '<div><small>Call strike</small><b>$'+fmt(x.strike)+'</b></div>'+
      '<div><small>Expiration date</small><b>'+safe(x.expiry)+'</b></div>'+
      '<div><small>Days to expiration</small><b>'+Number(x.dte)+' days</b></div>'+
      '<div><small>Call bid / ask</small><b>$'+fmt(x.bid)+' / $'+fmt(x.ask)+'</b></div>'+
      '<div><small>Bid yield</small><b>'+fmt(x.premium_yield)+'%</b></div>'+
    '</div>'+
    '<div class="detail-grid">'+

      '<div><small>Delta / IV</small><b>'+fmt(x.delta,2)+' / '+fmt(x.iv,1)+'%</b></div>'+
      '<div><small>Bid / ask size</small><b>'+Number(x.bid_size||0).toLocaleString()+' / '+Number(x.ask_size||0).toLocaleString()+'</b></div>'+
      '<div><small>Open interest / volume</small><b>'+Number(x.open_interest||0).toLocaleString()+' / '+Number(x.volume||0).toLocaleString()+'</b></div>'+
      '<div><small>Quote timestamp</small><b>'+safe(x.quote_time||'Unavailable')+'</b></div>'+
    '</div>';
}
function quoteCell(label,value,kind='price',hint=''){
  let shown='—';
  if(value!==null&&value!==undefined&&value!==''&&Number.isFinite(Number(value))){
    const n=Number(value),abs=Math.abs(n);
    const compact=abs>=1e12?fmt(abs/1e12,2)+'T':abs>=1e9?fmt(abs/1e9,2)+'B':abs>=1e6?fmt(abs/1e6,2)+'M':fmt(abs,2);
    shown=kind==='price'?'$'+fmt(n):kind==='percent'?changeText(n,'%'):kind==='percentvalue'?fmt(n,2)+'%':kind==='shares'?compact+' shares':kind==='change'?changeText(n,'$'):kind==='marketcap'?'$'+(abs>=1e12?fmt(abs/1e12,2)+'T':abs>=1e9?fmt(abs/1e9,2)+'B':abs>=1e6?fmt(abs/1e6,2)+'M':fmt(n,0)):kind==='money'?(n<0?'−':'')+'$'+compact:kind==='mspr'?(n<0?'−':n>0?'+':'')+fmt(abs):kind==='margin'?fmt(n,2)+'%':kind==='ratio'?fmt(n,2)+'x':Math.round(n).toLocaleString('en-US');
  }
  const cls=kind==='change'||kind==='percent'||kind==='mspr'?changeClass(value):(kind==='money'||kind==='margin')&&Number(value)<0?'negative':'';
  const title=hint?' title="'+safe(hint)+'"':'';
  return '<div class="detail-quote-stat"'+title+'><span>'+label+'</span><b class="'+cls+'">'+shown+'</b></div>';
}
function companyPublicHistory(ipo){
  if(!ipo)return 'Finnhub IPO date is unavailable.';
  const date=new Date(String(ipo)+'T00:00:00Z');
  if(!Number.isFinite(date.getTime()))return 'Finnhub IPO date is unavailable.';
  const now=new Date();
  let years=now.getUTCFullYear()-date.getUTCFullYear();
  const beforeAnniversary=now.getUTCMonth()<date.getUTCMonth()||(now.getUTCMonth()===date.getUTCMonth()&&now.getUTCDate()<date.getUTCDate());
  if(beforeAnniversary)years--;
  const since=date.toLocaleDateString('en-US',{month:'short',year:'numeric',timeZone:'UTC'});
  return years>0?'Public since '+since+' · '+years+' '+(years===1?'year':'years')+' listed':'Public since '+since;
}
function renderCompanyOverview(profile,symbol,quoteName){
  const info=profile&&typeof profile==='object'?profile:{};
  const name=info.name||quoteName||symbol;
  const summary=info.description||(
    info.industry
      ? 'Finnhub classifies this company in the '+info.industry+' industry. A fuller business description is unavailable in the profile returned for this ticker.'
      : 'Finnhub did not return a business description for this ticker.'
  );
  const countryNames={US:'United States',GB:'United Kingdom',CA:'Canada',DE:'Germany',FR:'France',JP:'Japan',CN:'China',AU:'Australia',IL:'Israel',IN:'India',IE:'Ireland',NL:'Netherlands',CH:'Switzerland',KR:'South Korea',TW:'Taiwan'};
  const country=info.country?(countryNames[info.country.toUpperCase()]||info.country):'';
  const headquarters=[info.city,info.state,country].filter(Boolean).join(', ')||'Not available in Finnhub profile';
  const website=typeof info.website==='string'&&(info.website.startsWith('https://')||info.website.startsWith('http://'))?'<a href="'+safe(info.website)+'" target="_blank" rel="noopener noreferrer">Company website ↗</a>':'';
  return '<section class="company-overview"><div class="company-overview-heading"><h3>About '+safe(name)+'</h3>'+website+'</div><p>'+safe(summary)+'</p><div class="company-overview-facts"><div><small>Industry</small><b>'+safe(info.industry||'Not available')+'</b></div><div><small>Headquarters</small><b>'+safe(headquarters)+'</b></div><div><small>Public-market history</small><b>'+safe(companyPublicHistory(info.ipo))+'</b></div></div><small class="company-overview-note">IPO date shows time as a public company; the business may be older.</small></section>';
}
async function viewChain(symbol){
  const modal=$('#detail-modal'),quoteBox=$('#detail-quote-content'),detail=$('#detail-content');
  $('#detail-title').textContent=symbol+' stock quote and covered-call screen';
  $('#detail-subtitle').textContent='Loading stock quote and listed call candidates…';
  $('#detail-description').hidden=true;
  $('#detail-company-overview').innerHTML='<div class="loading">Loading company overview…</div>';
  $('#detail-option-source').innerHTML='';
  quoteBox.innerHTML='<div class="loading">Retrieving stock quote…</div>';
  detail.innerHTML='<div class="loading">Retrieving covered-call data…</div>';
  modal.classList.add('open');
  try{
    const responses=await Promise.all([
      fetch('/options/api/quote/'+encodeURIComponent(symbol)),
      fetch('/options/api/chain/'+encodeURIComponent(symbol))
    ]);
    const quote=await responses[0].json(),chainData=await responses[1].json();
    if(!responses[0].ok)throw Error(quote.detail||'Stock quote unavailable.');
    const sourceLabel=quote.source==='demo'?'Illustrative demo values · Not live market data':quote.source==='tradier_sandbox'?'Tradier sandbox quote · May be delayed':'Tradier stock quote';
    $('#detail-title').textContent=quote.description?symbol+' · '+quote.description:symbol+' stock quote and covered-call screen';
    $('#detail-subtitle').textContent=sourceLabel;
    $('#detail-company-overview').innerHTML=renderCompanyOverview(quote.company_profile,symbol,quote.description);
    const rawTime=quote.quote_time;
    const quoteTime=rawTime&&Number.isFinite(Number(rawTime))&&Number(rawTime)>0?new Date(Number(rawTime)).toLocaleString():rawTime?String(rawTime):'Quote timestamp unavailable';
    quoteBox.innerHTML='<div class="detail-quote-stats">'+[
      quoteCell('Last',quote.price),
      quoteCell('Change',quote.change,'change'),
      quoteCell('Change %',quote.change_pct,'percent'),
      quoteCell('Bid',quote.bid),
      quoteCell('Ask',quote.ask),
      quoteCell('Open',quote.open),
      quoteCell('Day high',quote.high),
      quoteCell('Day low',quote.low),
      quoteCell('Volume',quote.volume,'volume'),
      quoteCell('52-H',quote.week_52_high),
      quoteCell('52-L',quote.week_52_low),
      quoteCell('Average volume',quote.average_volume,'volume'),
      quoteCell('Previous close',quote.previous_close),
      quoteCell('Market cap',quote.market_cap,'marketcap'),
      quoteCell('P/E ratio',quote.price_earnings_ratio,'ratio'),
      quoteCell('Earnings / share (TTM)',quote.earnings_per_share,'money'),
      quoteCell('Net margin (TTM)',quote.profit_margin,'margin'),
      quoteCell('Revenue (TTM)',quote.revenue,'money'),
      quoteCell('Shares outstanding',quote.shares_outstanding,'shares'),
      quoteCell('Total debt to capital',quote.total_debt_to_capital,'percentvalue'),
      quoteCell('Insider sentiment (MSPR)',quote.insider_sentiment_mspr,'mspr',quote.insider_sentiment_month?'MSPR range: −100 (net selling) to +100 (net buying). Latest month: '+quote.insider_sentiment_month+'.':'MSPR range: −100 (net selling) to +100 (net buying).')
    ].join('')+'</div>';
    $('#detail-option-source').innerHTML='<p class="detail-quote-source">'+sourceLabel+' · Quote time: '+safe(quoteTime)+'</p>';
    if(!responses[1].ok){
      detail.innerHTML='<p class="detail-quote-error">'+safe(chainData.detail||'Covered-call data unavailable.')+'</p>';
      return;
    }
    state.chainRows=chainData.rows||[];
    state.chainSource=chainData.source||'demo';
    state.chainDescription=chainData.description||quote.description||'';
    state.chainIndex=0;
    if(!state.chainRows.length)detail.innerHTML='<div class="empty">No covered-call rows were returned for this symbol.</div>';
    else renderChainPage();
    const description=$('#detail-description');
    description.textContent=state.chainDescription;
    const titleText=$('#detail-title').textContent.trim().toLocaleLowerCase();
    const descriptionText=String(state.chainDescription||'').trim().toLocaleLowerCase();
    description.hidden=!descriptionText||titleText.includes(descriptionText);
  }catch(error){
    quoteBox.innerHTML='<p class="detail-quote-error">'+safe(error.message)+'</p>';
    $('#detail-subtitle').textContent='Quote details may be incomplete.';
    toast(symbol+': '+error.message);
  }
}
async function analyzeSymbol(symbol){
  const modal=$('#symbol-analysis-modal'),body=$('#symbol-analysis-body'),sources=$('#symbol-analysis-sources'),status=$('#symbol-analysis-status');
  const row=state.rows.find(item=>item.symbol===symbol)||{};
  $('#symbol-analysis-title').textContent=`${symbol} · Deep analysis`;
  $('#symbol-analysis-subtitle').textContent=`${peakName(row.peak||'Other')} · Current-source research with citations`;
  stopNewsSpeech(false);resetAnalysisPodcast();$('#analysis-read-btn').hidden=true;$('#analysis-mp3-btn').disabled=true;body.textContent='Searching current sources and preparing the analysis…';sources.innerHTML='';status.textContent='';modal.classList.add('open');
  const screen=Object.fromEntries(['price','change','change_pct','strike','expiry','dte','bid','ask','premium_yield','delta','iv','open_interest','volume','bid_size','ask_size','quote_time','source'].filter(key=>row[key]!==undefined).map(key=>[key,row[key]]));
  screen.contract=contractLabel(row);
  screen.quantity=quantityForPrice(row.price);
  screen.estimated_income=incomeForRow(row);
  screen.ask_yield=Number(row.price)>0&&Number(row.ask)>0?Number(row.ask)/Number(row.price)*100:null;
  try{
    const response=await fetch('/options/api/symbol-analysis',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,screen})});
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Analysis request failed.');
    body.innerHTML=renderAnalysis(data.analysis||'No analysis was returned.');
    sources.innerHTML=(data.citations||[]).map((citation,index)=>`<li><a href="${safe(citation.url)}" target="_blank" rel="noopener noreferrer">${safe(citation.title||citation.url)}</a></li>`).join('');
    status.textContent=data.mode==='screen_fallback'?'Quote-based verdict · Current-source research did not finish':`Generated by ChatGPT${data.citations?.length?` · ${data.citations.length} cited sources`:''}`;
    updateAnalysisSpeechControls();
    $('#analysis-mp3-btn').disabled=false;
  }catch(error){body.textContent=error.message.includes('OPENAI_API_KEY')?'ChatGPT analysis is not enabled on the server yet. Add OPENAI_API_KEY to Railway Variables, then redeploy.':error.message;status.textContent='Analysis unavailable';}
}
function pageChain(delta){const next=state.chainIndex+delta;if(next<0||next>=state.chainRows.length)return;state.chainIndex=next;renderChainPage()}
function newsDate(value){if(!value)return 'Date unavailable';const d=new Date(value);return Number.isNaN(d.getTime())?value:new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric'}).format(d)}
function newsPeakChip(peak){const cls=peak==='AI/I'?'ai':peak==='EFM/I'?'efm':peak==='DS/I'?'defense':peak==='Cross-Peak'?'other':'other';return `<span class="peak-chip ${cls}"><i class="mini-dot"></i>${safe(peak||'Other')}</span>`}
let activeNewsSpeech=null,activeAnalysisSpeech=null;
let analysisPodcastAudioUrl=null,analysisPodcastTextUrl=null;

function resetAnalysisPodcast(){if(analysisPodcastAudioUrl)URL.revokeObjectURL(analysisPodcastAudioUrl);if(analysisPodcastTextUrl)URL.revokeObjectURL(analysisPodcastTextUrl);analysisPodcastAudioUrl=null;analysisPodcastTextUrl=null;$('#analysis-podcast-result').hidden=true;$('#analysis-podcast-transcript').value='';$('#analysis-podcast-audio').removeAttribute('src');$('#analysis-podcast-audio').load();$('#analysis-download-mp3').hidden=true;$('#analysis-download-transcript').removeAttribute('href');$('#analysis-download-mp3').removeAttribute('href');$('#analysis-podcast-status').textContent='Uses OpenAI API credits to make a Spotify-ready transcript and narrated MP3.'}
function podcastFileSlug(value){return String(value||'analysis').normalize('NFKD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,72)||'analysis'}
async function readApiError(response,fallback){try{const data=await response.json();return data.detail||fallback}catch(error){return fallback}}
async function createAnalysisPodcast(){const button=$('#analysis-mp3-btn'),status=$('#analysis-podcast-status'),title=$('#symbol-analysis-title').textContent.trim(),subtitle=$('#symbol-analysis-subtitle').textContent.trim(),analysis=$('#symbol-analysis-body').innerText.trim();if(!analysis){status.textContent='Wait for the analysis to finish, then try again.';return}resetAnalysisPodcast();button.disabled=true;button.textContent='Creating Spotify transcript + MP3…';status.textContent='Writing a Spotify-ready spoken transcript…';try{const scriptResponse=await fetch('/options/api/analysis-podcast/transcript',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,subtitle,analysis})});if(!scriptResponse.ok)throw Error(await readApiError(scriptResponse,'Transcript generation failed.'));const scriptData=await scriptResponse.json();const transcript=String(scriptData.transcript||'').trim();if(!transcript)throw Error('OpenAI returned an empty transcript.');$('#analysis-podcast-transcript').value=transcript;analysisPodcastTextUrl=URL.createObjectURL(new Blob([transcript],{type:'text/plain;charset=utf-8'}));const slug=podcastFileSlug(title),transcriptLink=$('#analysis-download-transcript');transcriptLink.href=analysisPodcastTextUrl;transcriptLink.download='RHTC_'+slug+'_Spotify_Transcript.txt';$('#analysis-podcast-result').hidden=false;status.textContent='Transcript ready ('+transcript.length.toLocaleString()+' characters). Creating the MP3…';const audioResponse=await fetch('/options/api/analysis-podcast/audio',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,transcript})});if(!audioResponse.ok)throw Error(await readApiError(audioResponse,'MP3 generation failed.'));const mp3=await audioResponse.blob();if(!mp3.size)throw Error('The MP3 file was empty. Try again.');analysisPodcastAudioUrl=URL.createObjectURL(mp3);$('#analysis-podcast-audio').src=analysisPodcastAudioUrl;const mp3Link=$('#analysis-download-mp3');mp3Link.href=analysisPodcastAudioUrl;mp3Link.download='RHTC_'+slug+'_Spotify.mp3';mp3Link.hidden=false;status.textContent='Ready to review or publish. Download the transcript and MP3 below.'}catch(error){status.textContent=error.message||'Could not create the Spotify assets. Try again.'}finally{button.disabled=false;button.textContent='🎙 Create Spotify Transcript + MP3'}}
async function copyAnalysisPodcastTranscript(){const text=$('#analysis-podcast-transcript').value;if(!text)return;try{await navigator.clipboard.writeText(text);toast('Spotify transcript copied.')}catch(error){const field=$('#analysis-podcast-transcript');field.focus();field.select();toast('Select and copy the transcript.')}}

function updateAnalysisSpeechControls(){const read=$('#analysis-read-btn'),stop=$('#analysis-stop-btn'),supported='speechSynthesis'in window&&'SpeechSynthesisUtterance'in window;if(!read||!stop)return;read.hidden=!supported;read.disabled=!supported;read.textContent=activeAnalysisSpeech?(activeAnalysisSpeech.paused?'▶ Resume':'Ⅱ Pause'):'🔊 Read analysis';stop.hidden=!activeAnalysisSpeech}
function stopAnalysisSpeech(refresh=true){const current=activeAnalysisSpeech;activeAnalysisSpeech=null;if(current&&'speechSynthesis'in window)window.speechSynthesis.cancel();if(refresh)updateAnalysisSpeechControls();return current}
function toggleAnalysisSpeech(){if(!('speechSynthesis'in window)||!('SpeechSynthesisUtterance'in window)){toast('Read aloud is not available in this browser.');return}if(activeAnalysisSpeech){if(activeAnalysisSpeech.paused){window.speechSynthesis.resume();activeAnalysisSpeech.paused=false}else{window.speechSynthesis.pause();activeAnalysisSpeech.paused=true}updateAnalysisSpeechControls();return}stopNewsSpeech(false);const text=[$('#symbol-analysis-title').textContent,$('#symbol-analysis-subtitle').textContent,$('#symbol-analysis-body').innerText].filter(Boolean).join('. ');if(!text.trim())return;const utterance=new SpeechSynthesisUtterance(text),speech={utterance,paused:false};activeAnalysisSpeech=speech;const finish=()=>{if(activeAnalysisSpeech===speech){activeAnalysisSpeech=null;updateAnalysisSpeechControls()}};utterance.onend=finish;utterance.onerror=finish;try{window.speechSynthesis.speak(utterance);updateAnalysisSpeechControls();updateNewsSpeechControls()}catch(error){finish();toast('Could not read this analysis aloud.')}}
function stopNewsSpeech(refresh=true){const current=activeNewsSpeech;activeNewsSpeech=null;if(activeAnalysisSpeech){activeAnalysisSpeech=null;updateAnalysisSpeechControls()}if('speechSynthesis'in window)window.speechSynthesis.cancel();if(refresh){updateNewsSpeechControls();updateAnalysisSpeechControls()}return current}
function updateNewsSpeechControls(){const supported='speechSynthesis'in window&&'SpeechSynthesisUtterance'in window;document.querySelectorAll('.news-item').forEach(card=>{const read=card.querySelector('[data-news-action="read"]'),stop=card.querySelector('[data-news-action="stop"]');if(!read||!stop)return;const current=activeNewsSpeech&&activeNewsSpeech.url===card.dataset.newsUrl;read.disabled=!supported;read.textContent=current?(activeNewsSpeech.paused?'▶ Resume':'Ⅱ Pause'):'🔊 Read excerpt';read.setAttribute('aria-label',current?`${activeNewsSpeech.paused?'Resume':'Pause'} reading ${card.querySelector('h3 a')?.textContent||'this story'}`:`Read title and excerpt aloud: ${card.querySelector('h3 a')?.textContent||'story'}`);stop.hidden=!current})}
function toggleNewsSpeech(card){if(!('speechSynthesis'in window)||!('SpeechSynthesisUtterance'in window)){toast('Read aloud is not available in this browser.');return}if(activeNewsSpeech&&activeNewsSpeech.url===card.dataset.newsUrl){if(activeNewsSpeech.paused){window.speechSynthesis.resume();activeNewsSpeech.paused=false}else{window.speechSynthesis.pause();activeNewsSpeech.paused=true}updateNewsSpeechControls();return}stopAnalysisSpeech(false);stopNewsSpeech(false);const title=card.querySelector('h3 a')?.textContent||'';const source=card.querySelector('.news-source')?.textContent||'';const excerpt=card.querySelector('.news-excerpt')?.textContent||'';const utterance=new SpeechSynthesisUtterance([title,source?`Source: ${source}`:'',excerpt].filter(Boolean).join('. '));const speech={url:card.dataset.newsUrl,utterance,paused:false};activeNewsSpeech=speech;const finish=()=>{if(activeNewsSpeech===speech){activeNewsSpeech=null;updateNewsSpeechControls()}};utterance.onend=finish;utterance.onerror=finish;try{window.speechSynthesis.speak(utterance);updateNewsSpeechControls();updateAnalysisSpeechControls()}catch(error){finish();toast('Could not read this excerpt aloud.')}}
async function analyzeNewsStory(card,button){
  const modal=$('#symbol-analysis-modal'),body=$('#symbol-analysis-body'),sources=$('#symbol-analysis-sources'),status=$('#symbol-analysis-status');
  const title=card.dataset.newsTitle||card.querySelector('h3 a')?.textContent||'News story';
  $('#symbol-analysis-title').textContent='RHTC impact analysis';
  stopNewsSpeech(false);resetAnalysisPodcast();$('#analysis-read-btn').hidden=true;$('#analysis-mp3-btn').disabled=true;$('#symbol-analysis-subtitle').textContent=`${title} · Watchlist companies, Three Peaks, and thesis`;body.textContent='Checking current sources and mapping potential impacts…';sources.innerHTML='';status.textContent='Uses OpenAI web search. Impacts are analytical assessments, not price targets.';modal.classList.add('open');button.disabled=true;
  try{
    const response=await fetch('/options/api/news/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,url:card.dataset.newsUrl||'',snippet:card.dataset.newsSnippet||'',published_at:card.dataset.newsPublishedAt||''})});
    const data=await response.json();if(!response.ok)throw Error(data.detail||'News analysis request failed.');
    body.innerHTML=renderAnalysis(data.analysis||'No analysis was returned.');
    sources.innerHTML=(data.citations||[]).map(citation=>`<li><a href="${safe(citation.url)}" target="_blank" rel="noopener noreferrer">${safe(citation.title||citation.url)}</a></li>`).join('');
    status.textContent=`Generated by ChatGPT${data.citations?.length?` · ${data.citations.length} cited sources`:''}`;
    updateAnalysisSpeechControls();
    $('#analysis-mp3-btn').disabled=false;
  }catch(error){body.textContent=error.message.includes('OPENAI_API_KEY')?'News analysis is not enabled on the server yet. Add OPENAI_API_KEY to Railway Variables, then redeploy.':error.message;status.textContent='Analysis unavailable'}
  finally{button.disabled=false}
}
function renderNews(items){if(activeNewsSpeech)stopNewsSpeech(false);const container=$('#news-items');$('#news-count').textContent=items.length?`${items.length} stories · last 14 days`:'No matching stories in the last 14 days.';$('#count-news').textContent=items.length?String(items.length):'0';if(!items.length){container.innerHTML='<p class="news-empty">No stories match these filters yet. The daily scan runs at 6:00 a.m. Pacific; use Scan for news to search now.</p>';return}container.innerHTML=items.map(item=>{const url=/^https?:\/\//i.test(item.url||'')?item.url:'#';return `<article class="news-item" data-news-url="${safe(url)}" data-news-title="${safe(item.title||'')}" data-news-snippet="${safe(item.snippet||'')}" data-news-published-at="${safe(item.published_at||item.first_seen_at||'')}"><div class="news-item-meta">${newsPeakChip(item.peak)}<span class="news-source">${safe(item.source||'Source')}</span><time>${safe(newsDate(item.published_at||item.first_seen_at))}</time></div><h3><a href="${safe(url)}" target="_blank" rel="noopener noreferrer">${safe(item.title)}</a></h3><p class="news-excerpt">${safe(item.snippet||'No source excerpt was returned.')}</p><div class="news-item-actions"><button class="news-read-btn" type="button" data-news-action="read">🔊 Read excerpt</button><button class="news-stop-btn" type="button" data-news-action="stop" aria-label="Stop reading this excerpt" hidden>Stop</button><button class="news-analyze-btn" type="button" data-news-action="analyze">✦ Analyze RHTC impact</button></div></article>`}).join('');updateNewsSpeechControls()}
async function loadNews({quiet=false}={}){try{const params=new URLSearchParams({days:'14',peak:$('#news-peak').value,q:$('#news-search').value.trim()});const response=await fetch(`/options/api/news?${params}`);if(!response.ok)throw Error('News feed is unavailable.');const data=await response.json();renderNews(data.items||[]);const stamp=data.last_scan_at?new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}).format(new Date(data.last_scan_at))+' PT':'Not scanned yet';$('#news-last-scanned').textContent=data.configured?`LAST SCAN · ${stamp}`:'PERPLEXITY KEY NOT CONFIGURED';if(!data.configured)$('#news-count').textContent='Add PERPLEXITY_API_KEY in Railway Variables to enable scanning.'}catch(error){if(!quiet){$('#news-items').innerHTML=`<p class="news-empty">${safe(error.message)}</p>`;toast('Could not load the RHTC news feed.')}}}
async function scanNews(){const button=$('#scan-news');button.disabled=true;button.querySelector('.refresh-icon').classList.add('spin');try{const response=await fetch('/options/api/news/scan',{method:'POST'});const data=await response.json();if(!response.ok)throw Error(data.detail||'News scan failed.');await loadNews({quiet:true});toast(data.status==='recent'?'The feed was scanned recently; showing saved stories.':`${data.added} stories refreshed.`)}catch(error){toast(error.message)}finally{button.disabled=false;button.querySelector('.refresh-icon').classList.remove('spin')}}
function setMode(mode){state.mode=mode;const isNews=mode==='news';if(!isNews)stopNewsSpeech();$('#options-view').hidden=isNews;$('#news-view').hidden=!isNews;$('#main-pager').hidden=mode==='history';document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.filter===mode||(!n.dataset.filter&&mode==='overview')));if(isNews){loadNews()}else if(mode==='history'){renderRows();toast('Snapshots are saved in this browser.')}else if(mode==='holdings'){state.selectedOnly=true;state.peak='All Peaks';document.querySelectorAll('.peak-item').forEach(n=>n.classList.toggle('selected',n.dataset.peak==='All Peaks'));loadRows({ai:false,snapshot:false})}else{state.selectedOnly=false;renderRows()}}
function pageMain(delta){const next=state.expirationSet+delta;if(next<1||next>4)return;state.expirationSet=next;$('#main-page').textContent=DTE_WINDOWS[next-1];$('#main-prev').disabled=next===1;$('#main-next').disabled=next===4;loadRows({ai:false,snapshot:false})}
async function saveServerWatchlist(rows){if(!state.editingEnabled)throw Error('Shared editing is not enabled yet. Configure the Railway Volume and admin token shown above.');let token=sessionStorage.getItem('rhtc-watchlist-admin-token');if(!token){token=window.prompt('Enter the RHTC watchlist admin token configured in Railway.');if(!token)throw Error('No changes saved. Enter the admin token to continue.')}const response=await fetch('/options/api/watchlist',{method:'PUT',headers:{'Content-Type':'application/json','X-RHTC-Admin-Token':token},body:JSON.stringify({rows})});if(!response.ok){if(response.status===401)sessionStorage.removeItem('rhtc-watchlist-admin-token');let detail='Could not save the shared symbol list.';try{detail=(await response.json()).detail||detail}catch(e){}throw Error(detail)}sessionStorage.setItem('rhtc-watchlist-admin-token',token);return (await response.json()).rows}
async function saveSymbolList(rows){setSymbolError('Saving to the shared RHTC list…');try{state.watchlist=await saveServerWatchlist(rows);state.migrationOpen=false;state.legacyWatchlist=null;localStorage.removeItem(WATCHLIST_KEY);updateWatchlistCounts();updateStorageNote();renderSymbolList();renderRows();setSymbolError('Saved for every browser.');loadRows({ai:false,snapshot:false});return true}catch(e){setSymbolError(e.message);return false}}
function validTicker(symbol){return /^[A-Z][A-Z0-9.-]{0,9}$/.test(symbol)}
async function addSymbol(){const symbol=$('#new-symbol').value.trim().toUpperCase();const peak=$('#new-peak').value;if(!validTicker(symbol)){setSymbolError('Enter a valid ticker (letters, numbers, dots, or dashes).');return}if(state.watchlist.some(r=>r.symbol===symbol)){setSymbolError(`${symbol} is already on the list.`);return}const added={symbol,peak,share_price:optionalNumber($('#new-share-price')),quantity:optionalNumber($('#new-quantity'))};if(await saveSymbolList([added,...state.watchlist])){$('#new-symbol').value='';$('#new-share-price').value='';$('#new-quantity').value='';renderSymbolList()}}
async function saveEditedSymbol(row){const oldSymbol=row.dataset.symbol;const symbol=row.querySelector('.symbol-edit-ticker').value.trim().toUpperCase();const peak=row.querySelector('.symbol-edit-peak').value;if(!validTicker(symbol)){setSymbolError('Enter a valid ticker (letters, numbers, dots, or dashes).');return}if(state.watchlist.some(r=>r.symbol===symbol&&r.symbol!==oldSymbol)){setSymbolError(`${symbol} is already on the list.`);return}const share_price=optionalNumber(row.querySelector('.symbol-edit-price'));const quantity=optionalNumber(row.querySelector('.symbol-edit-quantity'));const updated=state.watchlist.map(r=>r.symbol===oldSymbol?{symbol,peak,share_price,quantity}:r);if(await saveSymbolList(updated)){state.editingSymbol=null;renderSymbolList()}}
window.showSettings=()=>$('#settings-modal').classList.add('open');window.hideSettings=()=>$('#settings-modal').classList.remove('open');window.hideDetail=()=>$('#detail-modal').classList.remove('open');window.hideSymbols=()=>$('#symbols-modal').classList.remove('open');window.hideSymbolAnalysis=()=>{stopAnalysisSpeech();$('#symbol-analysis-modal').classList.remove('open')};window.viewChain=viewChain;window.analyzeSymbol=analyzeSymbol;
$('#manage-symbols').addEventListener('click',openSymbols);$('#add-symbol').addEventListener('click',addSymbol);$('#new-symbol').addEventListener('keydown',e=>{if(e.key==='Enter')addSymbol()});$('#symbol-filter').addEventListener('input',renderSymbolList);$('#symbol-peak-filter').addEventListener('change',renderSymbolList);$('#import-browser-list').addEventListener('click',()=>{if(state.legacyWatchlist)saveSymbolList(state.legacyWatchlist)});
$('#symbol-list').addEventListener('click',async e=>{const button=e.target.closest('button[data-action]');if(!button)return;const row=button.closest('.symbol-entry');if(!row)return;const action=button.dataset.action;setSymbolError();if(action==='edit'){state.editingSymbol=row.dataset.symbol;renderSymbolList()}else if(action==='cancel'){state.editingSymbol=null;renderSymbolList()}else if(action==='save'){saveEditedSymbol(row)}else if(action==='delete'){const updated=state.watchlist.filter(r=>r.symbol!==row.dataset.symbol);if(await saveSymbolList(updated)){state.editingSymbol=null;renderSymbolList()}}});
$('#theme-toggle').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'));
$('#sidebar-toggle').addEventListener('click',()=>setSidebarCollapsed(!$('.sidebar').classList.contains('collapsed')));
$('#chain-prev').addEventListener('click',()=>pageChain(-1));$('#chain-next').addEventListener('click',()=>pageChain(1));
$('#main-prev').addEventListener('click',()=>pageMain(-1));$('#main-next').addEventListener('click',()=>pageMain(1));$('#main-prev').disabled=true;
document.querySelectorAll('.peak-item').forEach(el=>el.addEventListener('click',()=>{const holdings=el.dataset.peak==='Holdings';state.costOnly=holdings;state.peak=holdings?'All Peaks':el.dataset.peak;state.mode='overview';state.selectedOnly=false;document.querySelectorAll('.peak-item').forEach(n=>n.classList.toggle('selected',n===el));setMode('overview');loadRows({ai:false,snapshot:false})}));
document.querySelectorAll('.nav-item').forEach(el=>el.addEventListener('click',()=>{const wasCostOnly=state.costOnly;state.costOnly=false;setMode(el.dataset.filter||'overview');if(wasCostOnly)loadRows({ai:false,snapshot:false})}));
$('#scan-news').addEventListener('click',scanNews);$('#news-peak').addEventListener('change',()=>loadNews());let newsSearchTimer;$('#news-search').addEventListener('input',()=>{clearTimeout(newsSearchTimer);newsSearchTimer=setTimeout(()=>loadNews({quiet:true}),220)});
$('#analysis-read-btn').addEventListener('click',toggleAnalysisSpeech);$('#analysis-stop-btn').addEventListener('click',()=>stopAnalysisSpeech());
$('#analysis-mp3-btn').addEventListener('click',createAnalysisPodcast);$('#analysis-copy-transcript').addEventListener('click',copyAnalysisPodcastTranscript);
$('#news-items').addEventListener('click',event=>{const button=event.target.closest('[data-news-action]');if(!button)return;const card=button.closest('.news-item');if(!card)return;if(button.dataset.newsAction==='read')toggleNewsSpeech(card);else if(button.dataset.newsAction==='stop')stopNewsSpeech();else if(button.dataset.newsAction==='analyze')analyzeNewsStory(card,button)});
$('#refresh').addEventListener('click',()=>loadRows({ai:true,snapshot:true}));$('#review-limit').addEventListener('change',e=>{state.scanLimit=Number(e.target.value);loadRows({ai:false,snapshot:false})});$('#max-last').addEventListener('change',()=>loadRows({ai:false,snapshot:false}));$('#sort').addEventListener('change',e=>{state.sort=e.target.value;loadRows({ai:false,snapshot:false})});let searchTimer;$('#search').addEventListener('input',e=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.query=e.target.value.trim();loadRows({ai:false,snapshot:false})},220)});
$('#market-clock').textContent=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date())+' ET';
initializeWatchlist();
loadNews({quiet:true});
$('#dashboard-logout').addEventListener('click',async()=>{try{await fetch('/options/auth/logout',{method:'POST',credentials:'same-origin'})}finally{location.replace('/options/login')}});
