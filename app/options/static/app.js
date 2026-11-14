const $ = (s) => document.querySelector(s);
const state = {peak:'All Peaks', query:'', sort:'rhtc_score', rows:[], source:'demo', mode:'overview', selectedOnly:false, costOnly:false, accountFilter:'all', stockScoreFilter:'all', callScoreFilter:'all', expirationSet:1, displayLimit:300, watchlist:[], editingSymbol:null, migrationOpen:false, editingEnabled:false, legacyWatchlist:null, chainDescription:''};
const DTE_WINDOWS=['0–7 DTE','8–14 DTE','15–22 DTE','22–28 DTE','29–35 DTE','36–42 DTE','37–49 DTE','48–56 DTE','57–63 DTE','64–70 DTE','70+ DTE'];
const WATCHLIST_KEY='rhtc-options-watchlist';
const watchlistLastQuoteCache=new Map(),watchlistLastQuotePending=new Set();
const peakMeta = {'AI/I':{label:'AI / Infrastructure',cls:'ai'},'EFM/I':{label:'Energy / Infrastructure',cls:'efm'},'DS/I':{label:'Defense / Space',cls:'defense'},'Other':{label:'Outside the Peaks',cls:'other'}};
// Curated focus symbols; this is not a verified position ledger.
const fmt = (n,d=2) => Number(n||0).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
function changeClass(value){const n=Number(value);return !Number.isFinite(n)||n===0?'':n>0?'positive':'negative'}
function changeText(value,unit){const n=Number(value);if(value===null||value===undefined||value===''||!Number.isFinite(n))return '—';const sign=n>0?'+':n<0?'−':'';return unit==='$'?`${sign}$${fmt(Math.abs(n))}`:`${sign}${fmt(Math.abs(n))}%`}
function parseMaxSpend(value){const raw=String(value??'').replace(/[$,\s]/g,'');return raw===''?NaN:Number(raw)}
function formatMaxSpend(value){return '$'+Math.round(value).toLocaleString('en-US')}
function quantityForPrice(price){const spend=parseMaxSpend($('#max-spend').value);const ceiling=spend/100;const last=Number(price);return Number.isFinite(ceiling)&&Number.isFinite(last)&&last>0?Math.trunc(ceiling/last):1}
function incomeForRow(row){const bid=Number(row.bid),ask=Number(row.ask);if(row.error||!Number.isFinite(bid)||!Number.isFinite(ask))return null;return ((bid+ask)/2)*100*quantityForPrice(row.price)}
function contractLabel(r){const expiry=String(r.expiry||'').replaceAll('-','');const strike=Number(r.strike);if(/^\d{8}$/.test(expiry)&&Number.isFinite(strike)){let value=String(strike);if(value.includes('e'))value=strike.toFixed(8).replace(/0+$/,'').replace(/\.$/,'');if(!value.includes('.'))value+='.0';return `${expiry}-${value}`}return r.contract||`${r.symbol} ${r.expiry} $${r.strike} C`}
function safe(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function analysisInline(text){return safe(text).replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>')}
function analysisTotalScore(lines){const source=lines.join(' ');const patterns=[/\bIncome\s*:\s*([1-5])\s*\/\s*5\b/i,/\bUpside cushion\s*:\s*([1-5])\s*\/\s*5\b/i,/\bEvent risk\s*:\s*([1-5])\s*\/\s*5\b/i,/\bLiquidity\s*:\s*([1-5])\s*\/\s*5\b/i];const scores=patterns.map(pattern=>{const match=source.match(pattern);return match?Number(match[1]):null});if(scores.some(score=>score===null))return null;return Math.max(1,Math.min(5,Math.round(scores.reduce((sum,score)=>sum+score,0)/scores.length)))}
function analysisScorecardMarkup(line){const clean=line.replace(/^\*\*|\*\*$/g,'').trim();if(!/^Scorecard\b/i.test(clean))return null;const pattern=/\b(Income|Upside cushion|Event risk|Liquidity)\s*:\s*([1-5])\s*\/\s*5\b/gi;const matches=[...clean.matchAll(pattern)];const labels=new Set(matches.map(match=>match[1].toLowerCase()));if(labels.size!==4)return null;let html='',cursor=0;for(const match of matches){html+=analysisInline(clean.slice(cursor,match.index));const label=match[1],score=Number(match[2]);html+=`${analysisInline(label)}: <span class="analysis-score-token analysis-score-${score}" aria-label="${safe(label)} score: ${score} out of 5">${score}/5</span>`;cursor=match.index+match[0].length}html+=analysisInline(clean.slice(cursor));return `<p class="analysis-scorecard">${html}</p>`}
function renderAnalysis(text){
  const lines=String(text||'').replace(/\r/g,'').split('\n'),html=[];let list=null,orderedCount=0;const totalScore=analysisTotalScore(lines);
  const closeList=()=>{if(list){html.push(`</${list}>`);list=null}};
  for(const raw of lines){const line=raw.trim();if(!line)continue;const heading=line.match(/^#{1,3}\s+(.+)$/);if(heading){closeList();orderedCount=0;const plain=/^in plain english$/i.test(heading[1].trim());const covered=/^covered-call verdict\b/i.test(heading[1].trim());const badge=covered&&totalScore!==null?` <span class="analysis-total-score analysis-score-${totalScore}" title="Equal-weight average of the four scorecard categories, rounded to the nearest whole number" aria-label="Total score: ${totalScore} out of 5">Total score ${totalScore}/5</span>`:'';html.push(`<h3${plain?' class="plain-verdict-heading"':''}>${analysisInline(heading[1])}${badge}</h3>`);continue}const scorecard=analysisScorecardMarkup(line);if(scorecard){closeList();orderedCount=0;html.push(scorecard);continue}const bullet=line.match(/^[-*]\s+(.+)$/);const numbered=line.match(/^\d+[.)]\s+(.+)$/);if(bullet||numbered){const wanted=numbered?'ol':'ul';if(list!==wanted){closeList();list=wanted;html.push(wanted==='ol'&&orderedCount?`<ol start="${orderedCount+1}">`:`<${list}>`)}if(numbered)orderedCount++;html.push(`<li>${analysisInline((bullet||numbered)[1])}</li>`);continue}closeList();orderedCount=0;html.push(`<p>${analysisInline(line)}</p>`)}closeList();return html.join('')}
function setTheme(theme,persist=true){const dark=theme==='dark';document.documentElement.dataset.theme=dark?'dark':'light';const button=$('#theme-toggle');button.textContent=dark?'☀':'☾';button.setAttribute('aria-label',dark?'Switch to light mode':'Switch to dark mode');button.title=dark?'Switch to light mode':'Switch to dark mode';if(persist){try{localStorage.setItem('rhtc-options-theme',dark?'dark':'light')}catch(e){}}}
try{setTheme(localStorage.getItem('rhtc-options-theme')||'dark',false)}catch(e){setTheme('dark',false)}
function toast(msg){const el=$('#toast');el.textContent=msg;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2800)}
function peakChip(peak){const m=peakMeta[peak]||peakMeta.Other;return `<span class="peak-chip ${m.cls}">${safe(peak)}</span>`}
function peakName(peak){return ({'AI/I':'AI / Infrastructure','EFM/I':'Energy / Infrastructure','DS/I':'Defense / Space','Other':'Outside the Peaks'})[peak]||peak}
function compactPeakName(peak){return ({'AI/I':'AI/I','EFM/I':'EFM/I','DS/I':'DS/I','Other':'Other'})[peak]||peak}
function updateWatchlistCounts(){$('#universe-value').innerHTML=`${state.watchlist.length} <small>symbols</small>`;$('#count-overview').textContent=state.watchlist.length}
function updateStorageNote(){const note=$('#symbol-storage-status');note.textContent=state.editingEnabled?'This shared list is saved on the RHTC server and appears in every browser.':'Shared editing is locked until Railway has a persistent Volume mounted at /data (RHTC_DATA_DIR=/data).';$('#import-browser-list').hidden=!(state.migrationOpen&&Array.isArray(state.legacyWatchlist)&&state.legacyWatchlist.length)}
async function initializeWatchlist(){try{const response=await fetch('/options/api/watchlist');if(!response.ok)throw Error('Watchlist unavailable');const data=await response.json();state.watchlist=data.rows;state.migrationOpen=Boolean(data.migration_open);state.editingEnabled=Boolean(data.editing_enabled);try{const saved=JSON.parse(localStorage.getItem(WATCHLIST_KEY)||'null');if(state.migrationOpen&&Array.isArray(saved))state.legacyWatchlist=saved}catch(e){}updateWatchlistCounts();updateStorageNote()}catch(e){toast('Could not load the shared RHTC symbol list.');state.watchlist=[];updateWatchlistCounts()}loadRows({ai:true,snapshot:false})}
function setSymbolError(message=''){$('#symbol-error').textContent=message}
function hasPositiveQuantity(r){const quantity=Number(r.quantity);return r.quantity!==null&&r.quantity!==undefined&&r.quantity!==''&&Number.isFinite(quantity)&&quantity>0}
function hasHoldingDetails(r){return hasPositiveQuantity(r)}
function belongsToAccountGroup(symbol,account){if(!account||account==='all')return true;return state.watchlist.some(item=>item.symbol===symbol&&hasPositiveQuantity(item)&&(account==='No account'?!item.account:String(item.account||'')===account||(['Fidelity','Schwab','Vanguard'].includes(account)&&String(item.account||'').startsWith(account))))}
function stockScoreValue(r){if(r.stock_score===null||r.stock_score===undefined||String(r.stock_score).trim()==='')return null;const score=Number(r.stock_score);return Number.isFinite(score)&&score>=0&&score<=5?score:null}
function isMissingStockScore(r){return stockScoreValue(r)===null}
function matchesStockScoreFilter(r){const filter=state.stockScoreFilter;if(filter==='all')return true;if(filter==='missing')return isMissingStockScore(r);const score=stockScoreValue(r);if(score===null)return false;const lower=Number(filter);return Number.isFinite(lower)&&score>=lower&&(lower===5?score<=5:score<lower+1)}
function callScoreValue(r){if(r.call_score===null||r.call_score===undefined||String(r.call_score).trim()==='')return null;const score=Number(r.call_score);return Number.isFinite(score)&&score>=0&&score<=5?score:null}
function isMissingCallScore(r){return callScoreValue(r)===null}
function matchesCallScoreFilter(r){const filter=state.callScoreFilter;if(filter==='all')return true;if(filter==='missing')return isMissingCallScore(r);const score=callScoreValue(r);if(score===null)return false;const minimum=Number(filter);return Number.isFinite(minimum)&&score>=minimum}
function combinedRhtcScore(r){const stock=Number(r.stock_score),call=r.call_score===null||r.call_score===undefined?null:Number(r.call_score);return Number.isInteger(stock)&&stock>=1&&stock<=5&&call!==null&&Number.isFinite(call)&&call>=0&&call<=5?stock+call:null}
function holdingDetails(r){const qty=r.quantity==null||r.quantity===''?'':`${fmt(r.quantity,Number.isInteger(Number(r.quantity))?0:2)} shares`;const price=r.share_price==null||r.share_price===''?'':`$${fmt(r.share_price)}/share`;return [qty,price].filter(Boolean).join(' · ')||'No share details'}
function optionalNumber(input){return input.value.trim()===''?null:Number(input.value)}
function optionalInteger(input){if(input.value.trim()==='')return null;const n=Number(input.value);return Number.isInteger(n)&&n>=0?n:NaN}
function daysToExpiry(value){const match=String(value||'').trim().match(/^(\d{2})(\d{2})(\d{2})$/);if(!match)return null;const year=2000+Number(match[1]),month=Number(match[2]),day=Number(match[3]),expiry=Date.UTC(year,month-1,day),date=new Date(expiry);if(date.getUTCFullYear()!==year||date.getUTCMonth()!==month-1||date.getUTCDate()!==day)return null;const now=new Date(),today=Date.UTC(now.getFullYear(),now.getMonth(),now.getDate());return Math.round((expiry-today)/86400000)}
function symbolYield(r){const premium=Number(r.lt_premium),shares=Number(r.quantity),price=Number(r.share_price),basis=shares*price;if(r.lt_premium==null||r.lt_premium===''||r.quantity==null||r.quantity===''||r.share_price==null||r.share_price===''||!Number.isFinite(premium)||!Number.isFinite(basis)||basis<=0)return null;return premium/basis*100}
function longTermDetails(r){const parts=[];if(r.lt_qty!=null&&r.lt_qty!=='')parts.push(`${r.lt_qty} ct`);if(r.lt_premium!=null&&r.lt_premium!=='')parts.push('premium $' + fmt(r.lt_premium));const yieldPct=symbolYield(r);if(yieldPct!==null)parts.push(`yield ${yieldPct.toFixed(2)}%`);return parts.join(' · ')}
function symbolAccountKey(symbol,account){return `${symbol}\u0000${account||''}`}
function symbolPositionCost(r){const price=Number(r.share_price),quantity=Number(r.quantity);return r.share_price!==null&&r.share_price!==undefined&&r.share_price!==''&&r.quantity!==null&&r.quantity!==undefined&&r.quantity!==''&&Number.isFinite(price)&&Number.isFinite(quantity)?price*quantity:null}
function symbolCallPremium(r){const premium=Number(r.lt_premium);return r.lt_premium!==null&&r.lt_premium!==undefined&&r.lt_premium!==''&&Number.isFinite(premium)?premium:null}
function comparePgRows(a,b){const pgA=String(a.pg||'').trim(),pgB=String(b.pg||'').trim();if(!pgA&&!pgB)return a.symbol.localeCompare(b.symbol,undefined,{sensitivity:'base',numeric:true});if(!pgA)return 1;if(!pgB)return -1;return pgA.localeCompare(pgB,undefined,{sensitivity:'base',numeric:true})||a.symbol.localeCompare(b.symbol,undefined,{sensitivity:'base',numeric:true})}
function compareSortValue(a,b){const av=String(a||'').trim(),bv=String(b||'').trim();if(!av&&!bv)return 0;if(!av)return 1;if(!bv)return -1;return av.localeCompare(bv,undefined,{sensitivity:'base',numeric:true})}
function compareSymbolRows(a,b){return a.symbol.localeCompare(b.symbol,undefined,{sensitivity:'base',numeric:true})}
function compareManagerRows(a,b,order){let primary;if(order==='buffett'){const av=Number(a.buffett_score),bv=Number(b.buffett_score),aHas=a.buffett_score!==null&&a.buffett_score!==undefined&&a.buffett_score!==''&&Number.isFinite(av),bHas=b.buffett_score!==null&&b.buffett_score!==undefined&&b.buffett_score!==''&&Number.isFinite(bv);primary=aHas&&bHas?bv-av:aHas?-1:bHas?1:0}else if(order==='ceo-risk'){const av=Number(a.ceo_risk_score),bv=Number(b.ceo_risk_score),aHas=Number.isFinite(av)&&a.ceo_risk_score!==null,bHas=Number.isFinite(bv)&&b.ceo_risk_score!==null;primary=aHas&&bHas?bv-av:aHas?-1:bHas?1:0}else if(order==='rhtc-score'){const av=combinedRhtcScore(a),bv=combinedRhtcScore(b),aHas=av!==null,bHas=bv!==null;primary=aHas&&bHas?bv-av:aHas?-1:bHas?1:0}else primary=order==='pg'?compareSortValue(a.pg,b.pg):order==='tier'?compareSortValue(peakName(a.peak),peakName(b.peak)):order==='expy'?compareSortValue(a.lt_expy,b.lt_expy):order==='account'?compareSortValue(a.account,b.account):compareSymbolRows(a,b);return primary||compareSymbolRows(a,b)}
function canAddCoveredCall(r){const shares=Number(r.quantity),calls=Number(r.lt_qty||0);return Number.isFinite(shares)&&shares>0&&Number.isFinite(calls)&&calls<Math.floor(shares/100)}
function updateWatchlistLastPriceDisplay(){
  let currentValue=0;
  document.querySelectorAll('#symbol-list .symbol-entry:not(.editing)').forEach(entry=>{
    const cell=entry.querySelector('.symbol-last-price');
    if(!cell)return;
    const quote=watchlistLastQuoteCache.get(entry.dataset.symbol);
    if(!quote||!Number.isFinite(quote.price)){
      cell.textContent='· last —';
      cell.classList.remove('last-up','last-down','last-flat');
      return;
    }
    const quantity=Number(entry.dataset.quantity);
    if(entry.dataset.quantity!==''&&Number.isFinite(quantity))currentValue+=quantity*quote.price;
    cell.textContent='· last $'+fmt(quote.price);
    cell.classList.remove('last-up','last-down','last-flat');
    const cost=Number(entry.dataset.sharePrice);
    if(entry.dataset.sharePrice===''||!Number.isFinite(cost)){
      cell.classList.add('last-flat');
      return;
    }
    const lastCents=Math.round(quote.price*100),costCents=Math.round(cost*100);
    cell.classList.add(lastCents<costCents?'last-down':lastCents>costCents?'last-up':'last-flat');
  });
  $('#symbol-current-value').textContent='$'+fmt(currentValue);
}
async function refreshWatchlistLastPrices(rows){const now=Date.now(),symbols=[...new Set(rows.map(row=>row.symbol))],needed=symbols.filter(symbol=>{const cached=watchlistLastQuoteCache.get(symbol);return(!cached||now-cached.at>30000)&&!watchlistLastQuotePending.has(symbol)});for(let i=0;i<needed.length;i+=8){const batch=needed.slice(i,i+8);batch.forEach(symbol=>watchlistLastQuotePending.add(symbol));await Promise.all(batch.map(async symbol=>{try{const response=await fetch('/options/api/quote/'+encodeURIComponent(symbol));if(!response.ok)throw Error('quote unavailable');const quote=await response.json(),price=Number(quote.price);watchlistLastQuoteCache.set(symbol,{price:Number.isFinite(price)&&price>0?price:null,at:Date.now()})}catch(error){watchlistLastQuoteCache.set(symbol,{price:null,at:Date.now()})}finally{watchlistLastQuotePending.delete(symbol)}}));updateWatchlistLastPriceDisplay()}}
function getFilteredSymbolRows(){const query=$('#symbol-filter').value.trim().toUpperCase();const selectedFilter=$('#symbol-peak-filter').value;const sortBy=$('#symbol-order-by').value||'pg';const holdingsOnly=selectedFilter==='Holdings';const callsWritten=selectedFilter==='Show calls written';const addCalls=selectedFilter==='Add calls';const accountTracker=selectedFilter==='Account Tracker';const accountFilter=selectedFilter.startsWith('account:')?selectedFilter.slice(8):null;return state.watchlist.filter(r=>(!query||r.symbol.includes(query))&&(selectedFilter==='All'||(holdingsOnly?hasHoldingDetails(r):callsWritten?Boolean(String(r.lt_call||'').trim()):addCalls?((r.account||'')!=='Schwab PRCA'&&canAddCoveredCall(r)):accountTracker?Boolean(String(r.pg||'').trim()):accountFilter!==null?(hasPositiveQuantity(r)&&(accountFilter==='No account'?!r.account:r.account===accountFilter)):r.peak===selectedFilter))).slice().sort((a,b)=>compareManagerRows(a,b,sortBy))}
function renderSymbolList(){const query=$('#symbol-filter').value.trim().toUpperCase();const selectedFilter=$('#symbol-peak-filter').value;const sortBy=$('#symbol-order-by').value||'pg';const holdingsOnly=selectedFilter==='Holdings';const callsWritten=selectedFilter==='Show calls written';const addCalls=selectedFilter==='Add calls';const accountTracker=selectedFilter==='Account Tracker';const accountFilter=selectedFilter.startsWith('account:')?selectedFilter.slice(8):null;const symbols=getFilteredSymbolRows();const countLabel=holdingsOnly?'holdings with details':callsWritten?'calls written':addCalls?'add call candidates':accountTracker?'PG values':accountFilter!==null?accountFilter:selectedFilter==='All'?'symbols':`${peakName(selectedFilter)} symbols`;const sortLabel=sortBy==='buffett'?'Buffett score':sortBy==='ceo-risk'?'CEO Risk':sortBy==='rhtc-score'?'RHTC Score':sortBy==='pg'?'PG':sortBy==='tier'?'tier':sortBy==='expy'?'expiry':sortBy==='account'?'account':'A–Z';$('#symbol-count').textContent=`${symbols.length} ${countLabel} · sorted by ${sortLabel}`;
$('#symbol-list').innerHTML=symbols.map(r=>{const accountKey=r.account||'';const editing=state.editingSymbol===symbolAccountKey(r.symbol,accountKey);if(editing)return `<div class="symbol-entry editing" data-symbol="${safe(r.symbol)}" data-account="${safe(accountKey)}"><input class="symbol-edit-ticker" aria-label="Ticker" maxlength="10" value="${safe(r.symbol)}"><select class="symbol-edit-peak" aria-label="Peak">${peakOptions(r.peak)}</select><input class="symbol-edit-price" aria-label="Share price" type="number" min="0" step="any" placeholder="Share price" value="${safe(r.share_price??'')}"><input class="symbol-edit-quantity" aria-label="Quantity" type="number" min="0" step="any" placeholder="Quantity" value="${safe(r.quantity??'')}"><select class="symbol-edit-account" aria-label="Account">${accountOptions(r.account)}</select><input class="symbol-edit-lt-call" aria-label="LT-Call strike" type="text" maxlength="12" placeholder="LT-Call" value="${safe(r.lt_call??'')}"><input class="symbol-edit-lt-expy" aria-label="LT-Expy" type="text" maxlength="6" placeholder="YYMMDD" value="${safe(r.lt_expy??'')}"><input class="symbol-edit-lt-qty" aria-label="LT-Qty" type="number" min="0" step="1" placeholder="LT-Qty" value="${safe(r.lt_qty??'')}"><input class="symbol-edit-lt-premium" aria-label="LT-Premium $" type="number" min="0" step="any" placeholder="LT-Premium $" value="${safe(r.lt_premium??'')}"><input class="symbol-edit-pg" aria-label="PG" type="text" maxlength="3" value="${safe(r.pg??'')}"><button type="button" data-action="save">Save</button><button type="button" class="secondary" data-action="cancel">Cancel</button></div>`;return `<div class="symbol-entry" data-position-cost="${symbolPositionCost(r)??''}" data-call-premium="${symbolCallPremium(r)??''}" data-quantity="${safe(r.quantity??'')}" data-share-price="${safe(r.share_price??'')}" data-symbol="${safe(r.symbol)}" data-account="${safe(r.account||'')}"><div class="symbol-actions symbol-delete-action"><button type="button" class="danger icon-button" data-action="delete" aria-label="Delete ${safe(r.symbol)}" title="Delete ${safe(r.symbol)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 7h12m-10 0 1 14h6l1-14M9 7V4h6v3m-7 0h8"/></svg></button></div><small class="symbol-pg-details">${safe(r.pg||'—')}</small><button type="button" class="symbol-buffett-score" data-action="buffett-report" aria-label="Open Buffett report for ${safe(r.symbol)}" title="${Number.isFinite(Number(r.buffett_score))&&r.buffett_score!==null&&r.buffett_score!==''?'Open Buffett report · '+Number(r.buffett_score).toFixed(1)+'/100':'Open or create Buffett report'}">${Number.isFinite(Number(r.buffett_score))&&r.buffett_score!==null&&r.buffett_score!==''?Number(r.buffett_score).toFixed(1):'View'}</button><button type="button" class="symbol-ceo-risk-score" data-action="ceo-risk-report" aria-label="Open or create CEO Risk report for ${safe(r.symbol)}" title="${(r.ceo_risk_score!==null&&r.ceo_risk_score!==undefined&&r.ceo_risk_score!==''&&Number.isFinite(Number(r.ceo_risk_score)))?'CEO Risk '+Number(r.ceo_risk_score).toFixed(1)+'/100 · '+safe(r.ceo_risk_rating||''):'Open or create CEO Risk report'}">${r.ceo_risk_score!==null&&r.ceo_risk_score!==undefined&&r.ceo_risk_score!==''&&Number.isFinite(Number(r.ceo_risk_score))?Number(r.ceo_risk_score).toFixed(0):'—'}</button><small class="symbol-rhtc-score" title="RHTC score = stock score + call score (maximum 10)">${r.stock_score!==null&&r.stock_score!==undefined&&r.stock_score!==''&&r.call_score!==null&&r.call_score!==undefined&&r.call_score!==''&&Number.isFinite(Number(r.stock_score))&&Number.isFinite(Number(r.call_score))&&Number(r.stock_score)>=1&&Number(r.stock_score)<=5&&Number(r.call_score)>=0&&Number(r.call_score)<=5?(Number(r.stock_score)+Number(r.call_score)).toFixed(1):'—'}</small><div class="symbol-description">${'<button type="button" class="buffett-report-ticker" data-action="stock-report" aria-label="Open stock analysis report for '+safe(r.symbol)+'" title="'+(Number(r.stock_report_count||0)>0?'Open saved stock analysis reports':'Open stock analysis screen')+'">'+safe(r.symbol)+'</button>'}<small>${safe(compactPeakName(r.peak))}</small><small class="symbol-account">${safe(r.account||'No account')}</small><small class="symbol-holding-details">${safe(holdingDetails(r))}</small><small class="symbol-last-price">· last —</small><div class="symbol-option-details"><small class="symbol-lt-call-details">${safe(r.lt_call?r.lt_call+' strike':'—')}</small><small class="symbol-lt-expy-details">${safe(r.lt_expy?`expires ${r.lt_expy}${daysToExpiry(r.lt_expy)!==null?' · dte '+daysToExpiry(r.lt_expy):''}`:'—')}</small><small class="symbol-lt-details">${safe(longTermDetails(r))}</small></div></div><div class="symbol-actions"><button type="button" class="icon-button" data-action="edit" aria-label="Edit ${safe(r.symbol)}" title="Edit ${safe(r.symbol)}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25Zm17.71-10.04a1 1 0 0 0 0-1.41l-2.51-2.51a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 2-1.66Z"/></svg></button></div></div>`}).join('')||'<div class="symbol-empty">No symbols match that search.</div>';const displayedRows=[...$('#symbol-list').querySelectorAll('.symbol-entry:not(.editing)')];const totalValue=displayedRows.reduce((sum,row)=>{const value=row.dataset.positionCost;return value!==''&&Number.isFinite(Number(value))?sum+Number(value):sum},0);const callPremiumTotal=displayedRows.reduce((sum,row)=>{const value=row.dataset.callPremium;return value!==''&&Number.isFinite(Number(value))?sum+Number(value):sum},0);$('#symbol-total-amount').textContent='$'+fmt(totalValue);$('#symbol-call-premium-total').textContent='$'+fmt(callPremiumTotal);updateWatchlistLastPriceDisplay();void refreshWatchlistLastPrices(symbols)}
function peakOptions(selected){return [['','Select Peak'],['AI/I','AI / Infrastructure'],['EFM/I','Energy / Infrastructure'],['DS/I','Defense / Space'],['Other','Outside the Peaks']].map(([value,label])=>`<option value="${value}"${(selected??'')===value?' selected':''}>${label}</option>`).join('')}
function accountOptions(selected){return [['','No account'],['Fidelity Brokerage','Fidelity Brokerage'],['Fidelity IRA','Fidelity IRA'],['Schwab PRCA','Schwab PRCA'],['Vanguard 401k','Vanguard 401k'],['Vanguard IRA-M','Vanguard IRA-M']].map(([value,label])=>`<option value="${safe(value)}"${(selected||'')===value?' selected':''}>${safe(label)}</option>`).join('')}
function openFullscreenModal(backdrop,modal,toggle=null){modal.classList.add('is-fullscreen');backdrop.classList.add('is-fullscreen','open');if(toggle){toggle.setAttribute('aria-label','Exit full screen');toggle.title='Exit full screen';toggle.setAttribute('aria-pressed','true')}}
function resetFullscreenModal(backdrop,modal,toggle=null){modal.classList.remove('is-fullscreen');backdrop.classList.remove('is-fullscreen','open');if(toggle){toggle.setAttribute('aria-label','Enter full screen');toggle.title='Enter full screen';toggle.setAttribute('aria-pressed','false')}}
function openSymbols(){state.editingSymbol=null;setSymbolError();$('#symbol-filter').value='';$('#symbol-peak-filter').value='Holdings';$('#symbol-order-by').value='expy';renderSymbolList();const backdrop=$('#symbols-modal');openFullscreenModal(backdrop,backdrop.querySelector('.modal'))}
function drawPeakBars(){$('#screened-total').textContent=`${state.rows.length} SCREENED`;const counts={'AI/I':0,'EFM/I':0,'DS/I':0,'Other':0};state.rows.forEach(r=>counts[r.peak]=(counts[r.peak]||0)+1);const max=Math.max(...Object.values(counts));$('#peak-bars').innerHTML=Object.entries(counts).map(([p,n])=>{let m=peakMeta[p];return `<div class="peak-bar-row"><span class="peak-bar-label">${m.label}</span><div class="bar-track"><div class="bar-fill ${m.cls}" style="width:${Math.max(2,n/max*100)}%"></div></div><span class="bar-num">${n}</span></div>`}).join('')}
function renderRows(){
  let rows=state.rows.filter(r=>(!state.selectedOnly||state.watchlist.some(item=>item.symbol===r.symbol&&hasPositiveQuantity(item)))&&(!state.costOnly||hasHoldingDetails(r))&&(state.mode==='history'||belongsToAccountGroup(r.symbol,state.accountFilter))&&matchesStockScoreFilter(r)&&matchesCallScoreFilter(r));
  if(state.mode==='history'){
    const history=JSON.parse(localStorage.getItem('rhtc-option-history')||'[]');
    rows=history.flatMap(s=>s.rows.map(r=>({...r,call_score:r.call_score??r.average_total_score,historyAt:s.at}))).filter(r=>(state.peak==='All Peaks'||r.peak===state.peak)&&r.symbol.toUpperCase().includes(state.query.toUpperCase()));
  }else if(state.sort==='rhtc_score'){
    rows.sort((a,b)=>{const ai=combinedRhtcScore(a),bi=combinedRhtcScore(b);if(ai===null)return bi===null?0:1;if(bi===null)return -1;return bi-ai});
  }else if(state.sort==='income'){
    rows.sort((a,b)=>{const ai=incomeForRow(a),bi=incomeForRow(b);if(ai===null)return bi===null?0:1;if(bi===null)return -1;return bi-ai});
  }
  if(!rows.length){$('#rows').innerHTML=`<tr><td colspan="14" class="empty">${state.mode==='history'?'No saved snapshots on this browser yet. Refresh quotes to start a local history.':'No symbols match the selected filters.'}</td></tr>`;$('#showing').textContent='0 rows';return}
  const orderedRows=state.mode==='history'?rows.slice().reverse().slice(0,180):rows;const subset=orderedRows.slice(0,Number(state.displayLimit)||300);
  $('#rows').innerHTML=subset.map(r=>{
    const error=r.error,noListedExpiration=Boolean(error&&/No listed expiration/i.test(error)),yieldVal=Number(r.premium_yield||0),qtyValue=Number(r.price)>0?quantityForPrice(r.price):null,qty=noListedExpiration||qtyValue===null?'—':qtyValue.toLocaleString(),income=incomeForRow(r),incomeClass=income===null?'income-neutral':income>parseMaxSpend($('#max-spend').value)*.02?'income-high':'income-neutral';
    const stockScore=Number.isInteger(Number(r.stock_score))&&Number(r.stock_score)>=1&&Number(r.stock_score)<=5?Number(r.stock_score):null;
    const stockLabel=r.stock_rating_label||({1:'Avoid',2:'Sell',3:'Watch',4:'Grow',5:'Bargain'}[stockScore]||'');
    const stockScoreClass=stockScore===null?'':`analysis-score-${stockScore}`;
    const callScore=r.call_score!==null&&r.call_score!==undefined&&Number.isFinite(Number(r.call_score))?Number(r.call_score):null;
    const callScoreClass=callScore===null?'':`analysis-score-${Math.max(1,Math.min(5,Math.round(callScore)))}`;
    const rhtcScore=stockScore!==null&&callScore!==null&&callScore>=0&&callScore<=5?stockScore+callScore:null;
    const rhtcScoreClass=rhtcScore===null?'':rhtcScore<5?'rhtc-score-low':'rhtc-score-high';
    const askYield=Number(r.price)>0&&Number(r.ask)>0?Number(r.ask)/Number(r.price)*100:null;
    return `<tr><td data-label="Ticker"><div class="ticker"><button class="ticker-details-btn" title="View ${safe(r.symbol)} option details" aria-label="View ${safe(r.symbol)} option details" onclick="viewChain('${safe(r.symbol)}')">${safe(r.symbol)}</button></div></td><td data-label="Peak">${peakChip(r.peak)}</td><td data-label="Stock score">${Number(r.stock_report_count)>0?`<button type="button" class="stock-score-pill ${stockScoreClass} stock-score-report-link" title="View the latest stock analysis and saved reports for ${safe(r.symbol)}" aria-label="View stock analysis reports for ${safe(r.symbol)}" onclick="viewStockReports('${safe(r.symbol)}')">${stockScore===null?'—':`${stockScore} · ${safe(stockLabel)}`}</button>`:`<span class="stock-score-pill ${stockScoreClass}">${stockScore===null?'—':`${stockScore} · ${safe(stockLabel)}`}</span>`}</td><td data-label="Call score"><span class="call-score-pill ${callScoreClass}">${callScore===null?'—':`${fmt(callScore)}/5`}</span></td><td data-label="RHTC / 10"><span class="rhtc-score-pill ${rhtcScoreClass}">${rhtcScore===null?'—':`${fmt(rhtcScore)}/10`}</span></td><td data-label="Last"><span class="number ${changeClass(r.change_pct)}">${Number(r.price)>0?`${String.fromCharCode(36)}${fmt(r.price)}`:'—'}</span></td><td data-label="Call contract"><div class="contract"><b>${noListedExpiration?'None listed':error?'Options data unavailable':safe(contractLabel(r))}</b>${error&&!noListedExpiration?`<small>${safe(error)}</small>`:''}${r.historyAt?`<small>Saved ${new Date(r.historyAt).toLocaleDateString()}</small>`:''}</div></td><td data-label="DTE"><span class="number">${error?'—':r.dte??'—'}</span></td><td data-label="Qty"><span class="number">${qty}</span></td><td data-label="Bid / ask" class="quote">${error?'—':`<span class="bid">$${fmt(r.bid)}</span>/${fmt(r.ask)}`}</td><td data-label="Bid / ask yield"><span class="yield-pill ${yieldVal>1.5?'high':''}">${error?'—':`${fmt(yieldVal)}%/${askYield===null?'—':fmt(askYield)+'%'}`}</span></td><td data-label="Income"><span class="number income-value ${incomeClass}">${income===null?'—':`${fmt(income)}`}</span></td><td data-label="Volume"><span class="quote-size quote-volume">${error?'—':`${Number(r.bid_size||0).toLocaleString()} × ${Number(r.ask_size||0).toLocaleString()}`}</span></td><td data-label="OI / Vol"><span class="oi">${error?'—':`${Number(r.open_interest||0).toLocaleString()}/${Number(r.volume||0).toLocaleString()}`}</span></td></tr>`
  }).join('');
  $('#showing').textContent=state.mode==='history'?`Showing ${subset.length} of ${orderedRows.length} saved rows`:`Showing ${subset.length} of ${rows.length} screened symbols`;
}
function updateStats(){let good=state.rows.filter(r=>!r.error&&Number.isFinite(Number(r.premium_yield)));let sorted=good.map(r=>Number(r.premium_yield)).sort((a,b)=>a-b);let mid=sorted.length?sorted[Math.floor(sorted.length/2)]:0;$('#review-value').innerHTML=`${good.length} <small>calls</small>`;$('#median-value').innerHTML=`${fmt(mid)} <small>%</small>`;const stamp=new Date();$('#asof-value').textContent=stamp.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',timeZone:'America/Los_Angeles'});$('#asof-date').textContent=stamp.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'America/Los_Angeles'});$('#foot-source').textContent=`Data mode: ${state.source}`;$('#source-pill').innerHTML=`<span class="source-dot"></span> ${state.source==='tradier_sandbox'?'TRADIER SANDBOX · DELAYED':state.source==='tradier'?'TRADIER QUOTES':'DEMO DATA'}`;$('#modal-mode').textContent=state.source==='tradier_sandbox'?'Sandbox · delayed':state.source==='tradier'?'Tradier connected':'Demo';const demoAlert=$('#demo-alert');if(demoAlert)demoAlert.style.display=state.source==='demo'?'flex':'none';}
async function loadRows({ai=false,snapshot=false}={}){const btn=$('#refresh');btn.disabled=true;$('.refresh-icon').classList.add('spin');$('#rows').innerHTML='<tr><td colspan="14" class="loading">Loading the RHTC option screen…</td></tr>';try{const peaks=state.peak==='All Peaks'?['AI/I','EFM/I','DS/I','Other']:[state.peak];const allRows=[];let source='demo';const spend=parseMaxSpend($('#max-spend').value);for(const peak of peaks){const p=new URLSearchParams({peak,q:state.query,sort:state.sort==='rhtc_score'?'income':state.sort,limit:'200',expiration_set:String(state.expirationSet),holdings_only:String(state.costOnly)});if(state.accountFilter!=='all')p.set('account',state.accountFilter);if(!state.costOnly&&state.accountFilter==='all'&&Number.isFinite(spend))p.set('max_last',String(spend/100));const res=await fetch(`/options/api/opportunities?${p}`);if(!res.ok)throw Error(await res.text());const data=await res.json();allRows.push(...(data.rows||[]));if(data.source)source=data.source;}state.rows=allRows;if(!['rhtc_score','income'].includes(state.sort)){const key=state.sort;state.rows.sort((a,b)=>{if(key==='ticker_az'||key==='ticker_za'){const order=String(a.symbol||'').toUpperCase().localeCompare(String(b.symbol||'').toUpperCase());return key==='ticker_za'?-order:order;}const av=Number(a[key]),bv=Number(b[key]);const left=Number.isFinite(av)?av:0,right=Number.isFinite(bv)?bv:0;return key==='dte'?left-right:right-left;});}state.source=source;updateStats();drawPeakBars();renderRows();if(snapshot)saveSnapshot();if(ai)await loadSummary();}catch(e){$('#rows').innerHTML=`<tr><td colspan="14" class="empty">Could not load data: ${safe(e.message)}. Check the server connection and try again.</td></tr>`;toast('Refresh failed. See the table message.')}finally{btn.disabled=false;$('.refresh-icon').classList.remove('spin')}}
function saveSnapshot(){if(!state.rows.length)return;const history=JSON.parse(localStorage.getItem('rhtc-option-history')||'[]');history.push({at:new Date().toISOString(),rows:state.rows.map(({symbol,peak,price,change,change_pct,strike,expiry,dte,bid,ask,premium_yield,delta,iv,open_interest,volume,bid_size,ask_size,quote_time,contract,share_price,quantity,call_score,stock_score,stock_rating_label})=>({symbol,peak,price,change,change_pct,strike,expiry,dte,bid,ask,premium_yield,delta,iv,open_interest,volume,bid_size,ask_size,contract,share_price,quantity,call_score,stock_score,stock_rating_label}))});localStorage.setItem('rhtc-option-history',JSON.stringify(history.slice(-12)))}
async function loadSummary(){let text=$('#ai-summary-text');if(!text)return;text.innerHTML='<span class="summary-loading">Reviewing the latest screen…</span>';try{const response=await fetch('/options/api/summary',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:state.source,rows:state.rows})});const data=await response.json();text.textContent=data.summary;$('#ai-summary-mode').textContent=data.mode==='openai'?'OPENAI SUMMARY':'RULE-BASED SUMMARY';}catch(e){text.textContent='Summary is unavailable. The quote table remains available for review.'}}
function renderChainPage(){
  const x=state.chainRows[state.chainIndex];
  if(!x)return;
  $('#chain-page').textContent=DTE_WINDOWS[state.chainIndex]||x.dte_window||'';
  $('#chain-prev').disabled=state.chainIndex===0;
  $('#chain-next').disabled=state.chainIndex===state.chainRows.length-1;
  if(x.error){
    $('#call-analyze-btn').disabled=true;
    $('#call-analysis-status').textContent='No covered call is available to analyze.';
    $('#call-analysis-results').hidden=true;
    $('#detail-subtitle').textContent='';
    $('#detail-content').innerHTML='<p class="error-text">'+safe(x.error)+'</p>';
    return;
  }
  const context=window.stockQuoteContext||{};
  context.call=x;
  window.stockQuoteContext=context;
  $('#call-analyze-btn').disabled=false;
  $('#call-analyze-btn').textContent='✦ Analyze call';
  $('#call-analysis-status').textContent='Uses current-source research and OpenAI API credits.';
  $('#call-analysis-results').hidden=true;
  $('#call-analysis-details').innerHTML='';
  $('#call-analysis-sources').innerHTML='';
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
function renderEarningsEvents(quote={}){
  const prior=quote.prior_earnings&&typeof quote.prior_earnings==='object'?quote.prior_earnings:null;
  const next=quote.next_earnings&&typeof quote.next_earnings==='object'?quote.next_earnings:null;
  const dateLabel=value=>value?new Date(value+'T00:00:00Z').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}):'Unavailable';
  const amount=(value,unit='$')=>value===null||value===undefined||value===''||!Number.isFinite(Number(value))?'Unavailable':unit+Number(value).toFixed(2);
  const row=(label,event,actual)=>'<div class="earnings-event"><b>'+label+'</b><span>'+dateLabel(event?.date)+'</span><span>EPS '+(actual?'actual ':'estimate ')+amount(actual?event?.eps_actual:event?.eps_estimate)+'</span>'+(actual&&event?.eps_estimate!==null&&event?.eps_estimate!==undefined?'<span>Estimate '+amount(event.eps_estimate)+'</span>':'')+'</div>';
  return '<section class="earnings-events"><h3>Earnings dates and EPS</h3><div class="earnings-events-grid">'+row('Prior reported',prior,true)+row('Next scheduled',next,false)+'</div><small>EPS amounts are per share; next date and estimates depend on company/Finnhub reporting.</small></section>';
}
async function showEarningsReport(){
  const modal=$('#earnings-report-modal'),status=$('#earnings-report-status'),content=$('#earnings-report-content');
  modal.classList.add('open');status.textContent='Loading saved upcoming earnings…';content.innerHTML='';
  try{
    const response=await fetch('/options/api/earnings-report',{credentials:'same-origin',cache:'no-store'});
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Could not load the earnings report.');
    const events=Array.isArray(data.events)?data.events:[];
    $('#earnings-report-meta').textContent='Future scheduled dates · as of '+(data.as_of||new Date().toISOString().slice(0,10));
    content.onclick=event=>{const button=event.target.closest('[data-stock-symbol]');if(button)viewStockReports(button.dataset.stockSymbol)};
  content.innerHTML=events.length?'<div class="earnings-report-table-wrap"><table class="earnings-report-table"><thead><tr><th>Next earnings</th><th>Ticker</th><th>EPS estimate</th></tr></thead><tbody>'+events.map(event=>{
      const eventDate=event.date?new Date(event.date+'T00:00:00Z').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}):'—';
      const epsValue=Number(event.eps_estimate);
      const epsAvailable=event.eps_estimate!==null&&event.eps_estimate!==undefined&&Number.isFinite(epsValue);
      const eps=epsAvailable?String.fromCharCode(36)+epsValue.toFixed(2):'Unavailable';
      const epsColor=epsAvailable?(epsValue>0?'#58d68d':'#ff6b6b'):'';
      const ticker=String(event.symbol||'');
      const tickerButton='<button type="button" class="earnings-ticker-link" data-stock-symbol="'+safe(ticker)+'" aria-label="View stock analysis for '+safe(ticker)+'">'+safe(ticker)+'</button>';
      return '<tr><td>'+safe(eventDate)+'</td><td>'+tickerButton+'</td><td style="color:'+epsColor+'">'+safe(eps)+'</td></tr>';
    }).join('')+'</tbody></table></div>':'<p class="earnings-report-empty">No upcoming earnings have been saved yet. Run Analyze Stock on tickers to populate the report.</p>';
    status.textContent=events.length+' upcoming ticker'+(events.length===1?'':'s');
  }catch(error){status.textContent=error.message}
}
function closeEarningsReport(){$('#earnings-report-modal').classList.remove('open')}
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
    info.description_pending
      ? 'Looking up the official company website for a business description…'
      : info.industry
      ? 'Finnhub classifies this company in the '+info.industry+' industry. A fuller business description is unavailable in the profile returned for this ticker.'
      : 'Finnhub did not return a business description for this ticker.'
  );
  const descriptionAttribution=info.description_source==='company website'?'<small class="company-overview-note">Business description retrieved from the company website.</small>':'';
  const descriptionMarkup=String(summary).split(/\n{2,}/).map(paragraph=>paragraph.trim()).filter(Boolean).map(paragraph=>'<p>'+safe(paragraph)+'</p>').join('');
  const sourceLinks=(Array.isArray(info.business_sources)?info.business_sources:[]).filter(source=>source&&typeof source.url==='string'&&/^https?:\/\//i.test(source.url)).map(source=>'<a href="'+safe(source.url)+'" target="_blank" rel="noopener noreferrer">'+safe(source.title||'Company source')+' ↗</a>').join('');
  const countryNames={US:'United States',GB:'United Kingdom',CA:'Canada',DE:'Germany',FR:'France',JP:'Japan',CN:'China',AU:'Australia',IL:'Israel',IN:'India',IE:'Ireland',NL:'Netherlands',CH:'Switzerland',KR:'South Korea',TW:'Taiwan'};
  const country=info.country?(countryNames[info.country.toUpperCase()]||info.country):'';
  const headquarters=[info.city,info.state,country].filter(Boolean).join(', ')||'Not available in Finnhub profile';
  const website=typeof info.website==='string'&&(info.website.startsWith('https://')||info.website.startsWith('http://'))?'<a href="'+safe(info.website)+'" target="_blank" rel="noopener noreferrer">Company website ↗</a>':'';
  return '<section class="company-overview"><div class="company-overview-heading"><h3>About '+safe(name)+'</h3>'+website+'</div><div class="company-overview-description">'+descriptionMarkup+'</div>'+descriptionAttribution+(sourceLinks?'<div class="company-overview-sources"><small>Business sources</small>'+sourceLinks+'</div>':'')+'<div class="company-overview-facts"><div><small>Industry</small><b>'+safe(info.industry||'Not available')+'</b></div><div><small>Headquarters</small><b>'+safe(headquarters)+'</b></div><div><small>Public-market history</small><b>'+safe(companyPublicHistory(info.ipo))+'</b></div></div><small class="company-overview-note">IPO date shows time as a public company; the business may be older.</small></section>';
}
async function loadCompanyWebsiteProfile(symbol,quoteName){
  try{
    const response=await fetch('/options/api/company-profile/'+encodeURIComponent(symbol),{credentials:'same-origin',cache:'no-store'});
    const profile=await response.json();
    if(!response.ok)throw Error(profile.detail||'Company profile unavailable.');
    const context=window.stockQuoteContext;
    if(!context||context.symbol!==symbol)return;
    context.quote.company_profile={...(context.quote.company_profile||{}),...profile,description_pending:false};
    $('#detail-company-overview').innerHTML=renderCompanyOverview(context.quote.company_profile,symbol,quoteName);
  }catch(error){
    const context=window.stockQuoteContext;
    if(!context||context.symbol!==symbol)return;
    context.quote.company_profile={...(context.quote.company_profile||{}),description_pending:false};
    $('#detail-company-overview').innerHTML=renderCompanyOverview(context.quote.company_profile,symbol,quoteName);
  }
}
async function analyzeStockQuote(){
  const context=window.stockQuoteContext||{};
  const symbol=context.symbol,quote=context.quote||{};
  const button=$('#stock-analyze-btn'),status=$('#stock-analysis-status'),results=$('#stock-analysis-results');
  if(!symbol){status.textContent='Load a stock quote before analyzing.';return}
  button.disabled=true;button.textContent='Analyzing…';status.textContent='Searching current sources and preparing the stock assessment…';
  results.hidden=true;
  try{
    const response=await fetch('/options/api/stock-analysis',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,quote})});
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Stock analysis request failed.');
    const labels={1:'Avoid',2:'Sell',3:'Watch',4:'Grow',5:'Bargain'};
    const rating=Number(data.rating),label=labels[rating]||data.rating_label||'Unrated';
    state.rows=state.rows.map(item=>item.symbol===symbol?{
      ...item,
      ...(Number.isInteger(rating)&&rating>=1&&rating<=5?{stock_score:rating,stock_rating_label:label}:{}),
      stock_report_count:Number(data.report_count)||1,
    }:item);
    state.watchlist=state.watchlist.map(item=>item.symbol===symbol?{...item,stock_report_count:Number(data.report_count)||1}:item);
    updateStockReportsButton(symbol,Number(data.report_count)||1);
    renderRows();
    const summary=$('#stock-analysis-summary');
    summary.innerHTML='<div class="stock-rating stock-rating-'+(Number.isFinite(rating)?rating:0)+'"><span>RHTC rating</span><b>'+(Number.isFinite(rating)?rating+' · ':'')+safe(label)+'</b></div><div class="stock-ranking-scale" aria-label="Rating scale">1 Avoid · 2 Sell · 3 Watch · 4 Grow · 5 Bargain</div><div class="stock-summary-copy">'+renderAnalysis(data.summary||'Summary was not returned.')+'</div>';
    const detailText=String(data.details||'Detailed analysis was not returned.');
    const detailedHeading=/^\s*#{1,3}\s*Detailed analysis\b[^\n]*\n/im.exec(detailText);
    const details=detailedHeading?detailText.slice(detailedHeading.index+detailedHeading[0].length).trim():detailText;
    $('#stock-analysis-details').innerHTML=renderAnalysis(details||'Detailed analysis was not returned.');
    $('#stock-analysis-sources').innerHTML=(data.citations||[]).map(citation=>'<li><a href="'+safe(citation.url)+'" target="_blank" rel="noopener noreferrer">'+safe(citation.title||citation.url)+'</a></li>').join('');
    results.hidden=false;status.textContent=data.citations?.length?'Current-source analysis · '+data.citations.length+' cited sources':'Current-source analysis';
  }catch(error){
    status.textContent=error.message.includes('OPENAI_API_KEY')?'Analysis is not enabled. Add OPENAI_API_KEY to Railway Variables, then redeploy.':error.message;
  }finally{
    button.disabled=false;button.textContent='✦ Analyze stock';
  }
}
function updateStockReportsButton(symbol,count){
  if(window.stockQuoteContext?.symbol!==symbol)return;
  const button=$('#stock-reports-btn');
  if(!button)return;
  button.disabled=Number(count)<1;
  button.textContent=Number(count)>0?'View reports ('+Number(count)+')':'View reports';
}
function viewCurrentStockReports(){
  const symbol=window.stockQuoteContext?.symbol;
  if(symbol)viewStockReports(symbol);
}
async function searchTickerNews(){
  const symbol=window.stockQuoteContext?.symbol;
  const button=$('#ticker-news-btn'),results=$('#ticker-news-results'),content=$('#ticker-news-content'),sources=$('#ticker-news-sources');
  if(!symbol)return;
  button.disabled=true;button.textContent='Searching…';results.hidden=true;
  try{
    const response=await fetch('/options/api/ticker-news',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol})});
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Ticker news search failed.');
    content.innerHTML=renderAnalysis(data.summary||'No current news summary was returned.');
    sources.innerHTML=(data.citations||[]).map(citation=>'<li><a href="'+safe(citation.url)+'" target="_blank" rel="noopener noreferrer">'+safe(citation.title||citation.url)+'</a></li>').join('');
    results.hidden=false;
  }catch(error){
    content.textContent=error.message.includes('OPENAI_API_KEY')?'News search is not enabled. Add OPENAI_API_KEY to Railway Variables, then redeploy.':error.message;
    sources.innerHTML='';results.hidden=false;
  }finally{button.disabled=false;button.textContent='⌕ Search ticker news'}
}
async function analyzeCallQuote(){
  const context=window.stockQuoteContext||{},call=context.call||{},symbol=context.symbol;
  const button=$('#call-analyze-btn'),status=$('#call-analysis-status'),results=$('#call-analysis-results');
  if(!symbol||!call.strike){status.textContent='Load a covered-call quote before analyzing.';return}
  const row={...(state.rows.find(item=>item.symbol===symbol)||{}),...call,symbol,price:context.quote?.price,change:context.quote?.change,change_pct:context.quote?.change_pct,source:call.source||state.chainSource||context.quote?.source};
  const screen=analysisScreenForRow(row);
  button.disabled=true;button.textContent='Analyzing…';status.textContent='Searching current sources and preparing the covered-call assessment…';results.hidden=true;
  try{
    const response=await fetch('/options/api/symbol-analysis',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,screen})});
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Call analysis request failed.');
    if(data.call_score!==null&&data.call_score!==undefined&&Number.isFinite(Number(data.call_score))){
      const score=Number(data.call_score);
      state.rows=state.rows.map(item=>item.symbol===symbol?{...item,call_score:score}:item);
      state.watchlist=state.watchlist.map(item=>item.symbol===symbol?{...item,call_score:score,analysis_count:data.analysis_count}:item);
      renderRows();
    }
    $('#call-analysis-details').innerHTML=renderAnalysis(data.analysis||'No call analysis was returned.');
    $('#call-analysis-sources').innerHTML=(data.citations||[]).map(citation=>'<li><a href="'+safe(citation.url)+'" target="_blank" rel="noopener noreferrer">'+safe(citation.title||citation.url)+'</a></li>').join('');
    results.hidden=false;
    status.textContent=data.mode==='screen_fallback'?'Quote-based verdict · Current-source research did not finish':(data.citations?.length?'Current-source analysis · '+data.citations.length+' cited sources':'Current-source analysis');
  }catch(error){
    status.textContent=error.message.includes('OPENAI_API_KEY')?'Analysis is not enabled. Add OPENAI_API_KEY to Railway Variables, then redeploy.':error.message;
  }finally{
    button.disabled=false;button.textContent='✦ Analyze call';
  }
}
async function viewChain(symbol){
  const modal=$('#detail-modal'),quoteBox=$('#detail-quote-content'),detail=$('#detail-content');
  $('#detail-title').textContent=symbol+' stock quote and covered-call screen';
  $('#detail-subtitle').textContent='Loading stock quote and listed call candidates…';
  $('#detail-description').hidden=true;
  $('#detail-company-overview').innerHTML='<div class="loading">Loading company overview…</div>';
  $('#detail-option-source').innerHTML='';
  window.stockQuoteContext=null;
  $('#stock-reports-btn').disabled=true;$('#stock-reports-btn').textContent='View reports';
  $('#stock-analyze-btn').disabled=true;$('#stock-analysis-status').textContent='Uses current-source research and OpenAI API credits.';
    $('#stock-analysis-results').hidden=true;$('#stock-analysis-summary').innerHTML='';$('#stock-analysis-details').innerHTML='';$('#stock-analysis-sources').innerHTML='';
  $('#ticker-news-btn').disabled=true;$('#ticker-news-btn').textContent='⌕ Search ticker news';$('#ticker-news-results').hidden=true;$('#ticker-news-content').innerHTML='';$('#ticker-news-sources').innerHTML='';
  $('#call-analyze-btn').disabled=true;$('#call-analyze-btn').textContent='✦ Analyze call';$('#call-analysis-status').textContent='Uses current-source research and OpenAI API credits.';$('#call-analysis-results').hidden=true;$('#call-analysis-details').innerHTML='';$('#call-analysis-sources').innerHTML='';
  quoteBox.innerHTML='<div class="loading">Retrieving stock quote…</div>';
  detail.innerHTML='<div class="loading">Retrieving covered-call data…</div>';
  openFullscreenModal(modal,modal.querySelector('.detail-modal'),$('#detail-fullscreen-toggle'));
  try{
    const responses=await Promise.all([
      fetch('/options/api/quote/'+encodeURIComponent(symbol)),
      fetch('/options/api/chain/'+encodeURIComponent(symbol))
    ]);
    const quote=await responses[0].json(),chainData=await responses[1].json();
    if(!responses[0].ok)throw Error(quote.detail||'Stock quote unavailable.');
    window.stockQuoteContext={symbol,quote};
    $('#detail-stock-earnings').innerHTML=renderEarningsEvents(quote);
    const stockReportCount=Number(((state.rows||[]).find(row=>row.symbol===symbol)||(state.watchlist||[]).find(row=>row.symbol===symbol))?.stock_report_count)||0;
    updateStockReportsButton(symbol,stockReportCount);
    $('#stock-analyze-btn').disabled=false;
    $('#ticker-news-btn').disabled=false;
    const sourceLabel=quote.source==='demo'?'Illustrative demo values · Not live market data':quote.source==='tradier_sandbox'?'Tradier sandbox quote · May be delayed':'Tradier stock quote';
    $('#detail-title').textContent=quote.description?symbol+' · '+quote.description:symbol+' stock quote and covered-call screen';
    $('#detail-subtitle').textContent=sourceLabel;
    const companyProfile=quote.company_profile&&typeof quote.company_profile==='object'?quote.company_profile:{};
    if(!companyProfile.description){companyProfile.description_pending=true;quote.company_profile=companyProfile;void loadCompanyWebsiteProfile(symbol,quote.description)}
    $('#detail-company-overview').innerHTML=renderCompanyOverview(companyProfile,symbol,quote.description);
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
function hasAnalyzableCallData(row){
  const hasNumber=value=>value!==null&&value!==undefined&&value!==''&&Number.isFinite(Number(value));
  return Boolean(row)&&!row.error&&hasNumber(row.strike)&&Number(row.strike)>0&&String(row.expiry||'').trim()!==''&&hasNumber(row.bid)&&hasNumber(row.ask);
}
function analysisScreenForRow(row){
  const screen=Object.fromEntries(['price','change','change_pct','strike','expiry','dte','bid','ask','premium_yield','delta','iv','open_interest','volume','bid_size','ask_size','quote_time','source'].filter(key=>row[key]!==undefined).map(key=>[key,row[key]]));
  screen.contract=contractLabel(row);
  screen.quantity=quantityForPrice(row.price);
  screen.estimated_income=incomeForRow(row);
  screen.ask_yield=Number(row.price)>0&&Number(row.ask)>0?Number(row.ask)/Number(row.price)*100:null;
  return screen;
}
async function analyzeSymbol(symbol){activeNewsStory=null;activeAnalysisCitations=[];
  const modal=$('#symbol-analysis-modal'),body=$('#symbol-analysis-body'),sources=$('#symbol-analysis-sources'),status=$('#symbol-analysis-status');
  const row=state.rows.find(item=>item.symbol===symbol)||{};
  const strike=Number(row.strike),expiry=String(row.expiry||'').trim(),contractParts=[];
  if(Number.isFinite(strike)&&strike>0)contractParts.push(`${fmt(strike)} Call`);
  if(/^\d{4}-\d{2}-\d{2}$/.test(expiry)){const [year,month,day]=expiry.split('-').map(Number);contractParts.push(new Date(Date.UTC(year,month-1,day)).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}))}
  else if(expiry)contractParts.push(expiry);
  $('#symbol-analysis-title').textContent=contractParts.length?`${symbol} · ${contractParts.join(' · ')}`:`${symbol} · Deep analysis`;
  $('#symbol-analysis-subtitle').textContent=`${peakName(row.peak||'Other')} · Current-source research with citations`;
  stopNewsSpeech(false);resetAnalysisPodcast();$('#analysis-read-btn').hidden=true;$('#analysis-mp3-btn').disabled=true;body.textContent='Searching current sources and preparing the analysis…';sources.innerHTML='';status.textContent='';openFullscreenModal(modal,modal.querySelector('.analysis-modal'),$('#analysis-fullscreen-toggle'));
  const screen=analysisScreenForRow(row);
  try{
    const response=await fetch('/options/api/symbol-analysis',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,screen})});
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Analysis request failed.');
    if(data.call_score!==null&&data.call_score!==undefined&&Number.isFinite(Number(data.call_score))){
      state.rows=state.rows.map(item=>item.symbol===symbol?{...item,call_score:data.call_score}:item);
      state.watchlist=state.watchlist.map(item=>item.symbol===symbol?{...item,call_score:data.call_score,analysis_count:data.analysis_count}:item);
      renderRows();
    }
    body.innerHTML=renderAnalysis(data.analysis||'No analysis was returned.');
    sources.innerHTML=(data.citations||[]).map((citation,index)=>`<li><a href="${safe(citation.url)}" target="_blank" rel="noopener noreferrer">${safe(citation.title||citation.url)}</a></li>`).join('');
    status.textContent=data.mode==='screen_fallback'?'Quote-based verdict · Current-source research did not finish':`Generated by ChatGPT${data.citations?.length?` · ${data.citations.length} cited sources`:''}`;
    updateAnalysisSpeechControls();
    $('#analysis-mp3-btn').disabled=false;
  }catch(error){body.textContent=error.message.includes('OPENAI_API_KEY')?'ChatGPT analysis is not enabled on the server yet. Add OPENAI_API_KEY to Railway Variables, then redeploy.':error.message;status.textContent='Analysis unavailable';}
}
let activeBuffettReportSymbol='',activeBuffettReportOffset=0,activeBuffettReportCount=0,activeBuffettReportId=null;
async function viewBuffettReports(symbol,offset=0){
  const modal=$('#buffett-report-modal'),status=$('#buffett-report-status');
  activeBuffettReportSymbol=symbol;activeBuffettReportId=null;modal.classList.add('open');status.textContent='Checking for a saved Buffett report…';
  $('#buffett-report-delete').disabled=true;$('#buffett-report-delete-all').disabled=true;
  $('#buffett-report-title').textContent=symbol+' · Buffett screen';
  $('#buffett-report-score').innerHTML='';$('#buffett-report-metrics').innerHTML='';$('#buffett-report-source-review').innerHTML='';$('#buffett-report-criteria').innerHTML='';$('#buffett-report-citations').innerHTML='';
  try{
    let response=await fetch('/options/api/buffett-screen/reports/'+encodeURIComponent(symbol)+'?offset='+encodeURIComponent(offset),{credentials:'same-origin',cache:'no-store'});
    let data=await response.json();
    if(response.status===404&&offset===0){
      status.textContent='No saved Buffett report for '+symbol+'. Creating one now…';
      response=await fetch('/options/api/buffett-screen',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol})});
      const created=await response.json();if(!response.ok)throw Error(created.detail||'Could not create a Buffett report for '+symbol+'.');
      const score=Number(created.buffett_score??created.score_percent),criteria=Array.isArray(created.criteria)?created.criteria:[];
      for(const row of state.watchlist||[])if(String(row.symbol||'').toUpperCase()===symbol){
        row.buffett_pass=created.buffett_pass;row.buffett_score=Number.isFinite(score)?score:null;row.buffett_updated_at=created.buffett_updated_at;row.buffett_report_count=Number(created.report_count)||1;
        row.buffett_criteria_json=JSON.stringify({buffett_pass:created.buffett_pass,buffett_score:row.buffett_score,score_percent:row.buffett_score,criteria:criteria,metrics:created.metrics,citations:created.citations});
      }
      renderSymbolList();
      status.textContent='Buffett report created. Loading saved report…';
      response=await fetch('/options/api/buffett-screen/reports/'+encodeURIComponent(symbol)+'?offset=0',{credentials:'same-origin',cache:'no-store'});
      data=await response.json();
    }
    if(!response.ok)throw Error(data.detail||'Saved Buffett report is unavailable.');
    const report=data.report||{};activeBuffettReportOffset=Number(data.offset)||0;activeBuffettReportCount=Number(data.report_count)||0;activeBuffettReportId=Number(report.report_id)||null;
    $('#buffett-report-delete').disabled=!activeBuffettReportId;$('#buffett-report-delete-all').disabled=activeBuffettReportCount<1;
    $('#buffett-report-meta').textContent='Report '+(activeBuffettReportOffset+1)+' of '+activeBuffettReportCount+' · '+newsTimestamp(report.created_at);
    const reportCriteria=report.criteria||[],criteriaPassed=reportCriteria.filter(item=>Number(item.score)===4||item.pass).length,criteriaTotal=Number(report.criteria_total)||reportCriteria.length||13;
    const scoreValue=Number(report.score_percent),scorePercent=Number.isFinite(scoreValue)?scoreValue:(criteriaPassed/criteriaTotal*100);
    const ratingLabel=String(report.rating_label||((scorePercent<25)?'Avoid':(scorePercent<45)?'Sell':(scorePercent<65)?'Watch':(scorePercent<80)?'Buy':'Bargain'));
    $('#buffett-report-score').innerHTML='<div class="buffett-overall-score score rating-'+safe(ratingLabel.toLowerCase())+'"><b>'+safe(ratingLabel.toUpperCase())+' · '+scorePercent.toFixed(1)+'/100</b></div>';
    const metrics=report.metrics||{};
    const labels={market_cap_usd:'Market capitalization',cash_and_short_term_investments_usd:'Cash and short-term investments',total_interest_bearing_debt_usd:'Interest-bearing debt',operating_cash_required_usd:'Operating cash reserve',normalized_annual_net_income_usd:'Normalized annual net income',annual_dividend_per_share_usd:'Annual dividend per share',share_price_usd:'Share price',dividend_yield_percent:'Dividend yield',dividend_coverage_earnings:'Dividend coverage · earnings',dividend_coverage_free_cash_flow:'Dividend coverage · free cash flow',gross_margin_percent:'Gross margin',return_on_equity_percent:'Return on equity',net_profit_margin_percent:'Net profit margin',cash_available_after_essential_expenses_severe_drop_usd:'Cash after severe-drop essential expenses',annual_cash_needs_severe_drop_usd:'Annual cash needs · severe-drop case'};
    $('#buffett-report-metrics').innerHTML=Object.entries(labels).map(([key,label])=>{const value=metrics[key];let shown='Unavailable';if(value!==null&&value!==undefined&&Number.isFinite(Number(value))){const n=Number(value);shown=key.endsWith('_usd')?'$'+n.toLocaleString('en-US',{maximumFractionDigits:2}):key.endsWith('_percent')?n.toFixed(2)+'%':n.toLocaleString('en-US',{maximumFractionDigits:3})}return '<div class="buffett-metric"><span>'+safe(label)+'</span><b>'+safe(shown)+'</b></div>'}).join('');
    const savedAnalysis=report.saved_stock_analysis||{},sourceReview=report.source_review||[],finnhubStatus=report.finnhub_data_status||{},finnhubFields=report.finnhub_filled_fields||[],secStatus=report.sec_data_status||{};
    const savedReports=Array.isArray(savedAnalysis.reports)?savedAnalysis.reports:(savedAnalysis.found?[savedAnalysis]:[]);
    let reviewHtml=savedAnalysis.found?'<p class="buffett-source-summary">Reviewed '+safe(String(savedAnalysis.report_count||savedReports.length||1))+' saved stock analysis report'+((Number(savedAnalysis.report_count||savedReports.length||1)===1)?'':'s')+' from newest to oldest:</p><ol class="buffett-stock-report-history">'+savedReports.map(item=>'<li>Report '+safe(String(item.report_id||''))+' · '+safe(newsTimestamp(item.created_at))+' · '+safe(item.rating_label||'Unrated')+'</li>').join('')+'</ol>':'<p class="buffett-source-summary">No saved stock analysis was available for this ticker.</p>';
    const secAvailable=Array.isArray(secStatus.available_fields)?secStatus.available_fields:[],secFilled=Array.isArray(secStatus.filled_fields)?secStatus.filled_fields:[];
    const fieldLabel=value=>String(value).replace(/_usd$/,'').replace(/_percent$/,'%').replaceAll('_',' ');
    const secLine='SEC Company Facts: '+safe(secStatus.status||'unavailable')+(secStatus.form?' · '+safe(secStatus.form)+' period ended '+safe(secStatus.period_end||'')+' (filed '+safe(secStatus.filed_date||'')+')':'')+(secStatus.annual_period_end?' · annual statements through '+safe(secStatus.annual_period_end):'')+(secAvailable.length?' · extracted '+safe(String(secAvailable.length))+' fields':'')+(secFilled.length?' · applied: '+safe(secFilled.map(fieldLabel).join(', ')):'')+(secStatus.detail?' · '+safe(secStatus.detail):'');
    reviewHtml+='<p class="buffett-source-summary">'+secLine+'</p>';
    const finnhubLine='Finnhub data: '+safe(finnhubStatus.status||'unavailable')+' · '+safe(String(finnhubStatus.annual_periods||0))+' annual and '+safe(String(finnhubStatus.quarterly_periods||0))+' quarterly periods'+(finnhubFields.length?' · filled missing fields: '+safe(finnhubFields.map(x=>String(x).replace(/_usd$/,'').replace(/_percent$/,'%').replaceAll('_',' ')).join(', ')):'');
    reviewHtml+='<p class="buffett-source-summary">'+finnhubLine+'</p>';
    if(finnhubStatus.detail)reviewHtml+='<p class="buffett-source-summary">'+safe(finnhubStatus.detail)+'</p>';
    reviewHtml+=sourceReview.length?'<div class="buffett-source-review-list">'+sourceReview.map(item=>'<a class="buffett-source-review-item '+(item.status==='reviewed'?'reviewed':'unavailable')+'" href="'+safe(item.url)+'" target="_blank" rel="noopener noreferrer" aria-label="Open source: '+safe(item.title||item.url)+'"><span class="buffett-source-link-title">'+safe(item.title||item.url)+'</span><span>'+(item.status==='reviewed'?(item.truncated?'Reviewed first 750 KB':'Fetched and reviewed'):'Could not fetch')+(item.characters?' · '+safe(String(item.characters))+' chars':'')+'</span>'+(item.detail?'<small>'+safe(item.detail)+'</small>':'')+'</a>').join('')+'</div>':'<p class="buffett-source-summary">No source links were stored in the saved analysis.</p>';
    $('#buffett-report-source-review').innerHTML=reviewHtml;

    const criterionGrades=['DEFICIENT','WEAK','MIXED','STRONG','FULL STANDARD'];
    $('#buffett-report-criteria').innerHTML=(report.criteria||[]).slice().sort((a,b)=>Number(a.id)-Number(b.id)).map(item=>{const rawScore=Number(item.score),criterionScore=Number.isFinite(rawScore)?Math.max(0,Math.min(4,Math.round(rawScore))):(item.pass?4:0);return '<li class="buffett-criterion '+(criterionScore>=3?'pass':'fail')+' score-'+criterionScore+'"><div><b>'+safe(String(item.id)+'. '+(item.name||''))+'</b><span>'+criterionGrades[criterionScore]+' · '+criterionScore+'/4</span></div><p>'+safe(item.evidence||'No supporting detail was saved.')+'</p></li>'}).join('');
    $('#buffett-report-citations').innerHTML=(report.citations||[]).map(cite=>'<li><a href="'+safe(cite.url)+'" target="_blank" rel="noopener noreferrer">'+safe(cite.title||cite.url)+'</a><small> · '+safe(cite.origin||'Source')+(cite.review_status?' · '+safe(cite.review_status):'')+'</small></li>').join('');
    $('#buffett-report-previous').disabled=activeBuffettReportOffset>=activeBuffettReportCount-1;
    $('#buffett-report-next').disabled=activeBuffettReportOffset<=0;status.textContent='';
  }catch(error){status.textContent=error.message;$('#buffett-report-previous').disabled=true;$('#buffett-report-next').disabled=true;$('#buffett-report-delete').disabled=true;$('#buffett-report-delete-all').disabled=true}
}
function navigateBuffettReport(direction){if(!activeBuffettReportSymbol)return;const offset=activeBuffettReportOffset+direction;if(offset<0||offset>=activeBuffettReportCount)return;viewBuffettReports(activeBuffettReportSymbol,offset)}
async function deleteBuffettReport(){
  if(!activeBuffettReportSymbol||!activeBuffettReportId)return;
  const symbol=activeBuffettReportSymbol,reportId=activeBuffettReportId;
  if(!confirm('Delete this Buffett report for '+symbol+'? This cannot be undone.'))return;
  const status=$('#buffett-report-status'),button=$('#buffett-report-delete');
  button.disabled=true;status.textContent='Deleting Buffett report…';
  try{
    const response=await fetch('/options/api/buffett-screen/reports/'+encodeURIComponent(symbol)+'/'+encodeURIComponent(reportId),{method:'DELETE',credentials:'same-origin'});
    const data=await response.json();if(!response.ok)throw Error(data.detail||'Could not delete the Buffett report.');
    for(const row of state.watchlist||[])if(row.symbol===symbol)row.buffett_report_count=Number(data.report_count)||0;
    if(Number(data.report_count)>0)await viewBuffettReports(symbol,Math.min(activeBuffettReportOffset,Number(data.report_count)-1));
    else{closeBuffettReportViewer();toast('Deleted the Buffett report. No saved reports remain for '+symbol+'.');}
  }catch(error){status.textContent=error.message;button.disabled=false}
}
async function deleteAllBuffettReports(){
  if(!activeBuffettReportSymbol||activeBuffettReportCount<1)return;
  const symbol=activeBuffettReportSymbol;
  if(!confirm('Delete all '+activeBuffettReportCount+' Buffett reports for '+symbol+'? This cannot be undone.'))return;
  const status=$('#buffett-report-status'),button=$('#buffett-report-delete-all');
  button.disabled=true;status.textContent='Deleting all Buffett reports…';
  try{
    const response=await fetch('/options/api/buffett-screen/reports/'+encodeURIComponent(symbol),{method:'DELETE',credentials:'same-origin'});
    const data=await response.json();if(!response.ok)throw Error(data.detail||'Could not delete Buffett reports.');
    for(const row of state.watchlist||[])if(row.symbol===symbol)row.buffett_report_count=0;
    closeBuffettReportViewer();toast('Deleted '+(Number(data.deleted_count)||0)+' Buffett reports for '+symbol+'.');
  }catch(error){status.textContent=error.message;button.disabled=false}
}
function closeBuffettReportViewer(){$('#buffett-report-modal').classList.remove('open')}

let activeStockReportSymbol='',activeStockReportOffset=0,activeStockReportCount=0,activeStockReportId=null;

async function viewStockReports(symbol,offset=0){
  const modal=$('#stock-report-modal'),status=$('#stock-report-status');
  activeStockReportSymbol=symbol;
  modal.classList.add('open');
  status.textContent='Loading saved stock analysis…';
  $('#stock-report-delete').disabled=true;$('#stock-report-delete-all').disabled=true;
  $('#stock-report-title').textContent=symbol+' · Stock analysis';
  $('#stock-report-summary').innerHTML='';
  $('#stock-report-details').innerHTML='';
  $('#stock-report-citations').innerHTML='';
  $('#stock-report-quote').textContent='';
  $('#stock-report-earnings').innerHTML='';
  try{
    let response=await fetch('/options/api/stock-analysis/reports/'+encodeURIComponent(symbol)+'?offset='+encodeURIComponent(offset),{credentials:'same-origin',cache:'no-store'});
    let data=await response.json();
    if(response.status===404&&offset===0){
      status.textContent='No saved stock analysis for '+symbol+'. Creating one now…';
      const quoteResponse=await fetch('/options/api/quote/'+encodeURIComponent(symbol),{credentials:'same-origin'});
      const quote=await quoteResponse.json();
      if(!quoteResponse.ok)throw Error(quote.detail||'Could not load a quote for '+symbol+'.');
      response=await fetch('/options/api/stock-analysis',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,quote})});
      const created=await response.json();
      if(!response.ok)throw Error(created.detail||'Could not create a stock analysis for '+symbol+'.');
      for(const row of state.watchlist||[])if(String(row.symbol||'').toUpperCase()===symbol){row.stock_report_count=Number(created.report_count)||1;row.stock_score=created.rating??null;row.stock_rating_label=created.rating_label??null}
      renderSymbolList();
      status.textContent='Stock analysis created. Loading saved report…';
      response=await fetch('/options/api/stock-analysis/reports/'+encodeURIComponent(symbol)+'?offset=0',{credentials:'same-origin',cache:'no-store'});
      data=await response.json();
    }
    if(!response.ok)throw Error(data.detail||'Saved stock analysis is unavailable.');
    const report=data.report||{};
    activeStockReportOffset=Number(data.offset)||0;
    activeStockReportCount=Number(data.report_count)||0;
    activeStockReportId=Number(report.report_id)||null;
    const rating=Number(report.rating),label=report.rating_label||'Unrated';
    $('#stock-report-rating').innerHTML='<div class="stock-rating stock-rating-'+(Number.isInteger(rating)?rating:0)+'"><span>RHTC rating</span><b>'+(Number.isInteger(rating)?rating+' · ':'')+safe(label)+'</b></div>';
    $('#stock-report-meta').textContent='Report '+(activeStockReportOffset+1)+' of '+activeStockReportCount+' · '+newsTimestamp(report.created_at);
    $('#stock-report-summary').innerHTML=renderAnalysis(report.summary||'Summary was not saved.');
    $('#stock-report-details').innerHTML=renderAnalysis(report.details||'Detailed analysis was not saved.');
    $('#stock-report-citations').innerHTML=(report.citations||[]).map(citation=>'<li><a href="'+safe(citation.url)+'" target="_blank" rel="noopener noreferrer">'+safe(citation.title||citation.url)+'</a></li>').join('');
    const quote=report.quote||{};
    $('#stock-report-earnings').innerHTML=renderEarningsEvents(quote);
    const price=Number(quote.price);
    $('#stock-report-quote').textContent='Quote snapshot: '+(quote.price!==null&&quote.price!==undefined&&Number.isFinite(price)?'$'+price.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):'price unavailable')+' · '+(quote.quote_time||'timestamp unavailable')+' · '+(quote.source||'source unavailable');
    $('#stock-report-previous').disabled=activeStockReportOffset>=activeStockReportCount-1;
    $('#stock-report-next').disabled=activeStockReportOffset<=0;
    $('#stock-report-delete').disabled=!activeStockReportId;
    $('#stock-report-delete-all').disabled=activeStockReportCount<1;
    status.textContent='';
  }catch(error){
    status.textContent=error.message;
    $('#stock-report-previous').disabled=true;
    $('#stock-report-next').disabled=true;
    $('#stock-report-delete').disabled=true;
    $('#stock-report-delete-all').disabled=true;
  }
}
function navigateStockReport(direction){
  if(!activeStockReportSymbol)return;
  const nextOffset=activeStockReportOffset+direction;
  if(nextOffset<0||nextOffset>=activeStockReportCount)return;
  viewStockReports(activeStockReportSymbol,nextOffset);
}
async function deleteStockReport(){
  if(!activeStockReportSymbol||!activeStockReportId)return;
  const symbol=activeStockReportSymbol,reportId=activeStockReportId;
  if(!confirm('Delete this stock analysis report for '+symbol+'? This cannot be undone.'))return;
  const status=$('#stock-report-status'),button=$('#stock-report-delete');button.disabled=true;status.textContent='Deleting stock analysis report…';
  try{
    const response=await fetch('/options/api/stock-analysis/reports/'+encodeURIComponent(symbol)+'/'+encodeURIComponent(reportId),{method:'DELETE',credentials:'same-origin'});
    const data=await response.json();if(!response.ok)throw Error(data.detail||'Could not delete the stock analysis report.');
    for(const row of state.rows||[])if(row.symbol===symbol){row.stock_report_count=Number(data.report_count)||0;row.stock_score=data.rating??null;row.stock_rating_label=data.rating_label??null}
    for(const row of state.watchlist||[])if(row.symbol===symbol){row.stock_report_count=Number(data.report_count)||0;row.stock_score=data.rating??null;row.stock_rating_label=data.rating_label??null}
    updateStockReportsButton(symbol,Number(data.report_count)||0);
    renderRows();renderSymbolList();
    if(Number(data.report_count)>0)await viewStockReports(symbol,Math.min(activeStockReportOffset,Number(data.report_count)-1));
    else{closeStockReportViewer();toast('Deleted the stock analysis report. No saved reports remain for '+symbol+'.')}
  }catch(error){status.textContent=error.message;button.disabled=false}
}
async function deleteAllStockReports(){
  if(!activeStockReportSymbol||activeStockReportCount<1)return;
  const symbol=activeStockReportSymbol;
  if(!confirm('PURGE all '+activeStockReportCount+' stock analysis reports for '+symbol+'? This cannot be undone.'))return;
  const status=$('#stock-report-status'),button=$('#stock-report-delete-all');button.disabled=true;status.textContent='Purging stock analysis reports…';
  try{
    const response=await fetch('/options/api/stock-analysis/reports/'+encodeURIComponent(symbol),{method:'DELETE',credentials:'same-origin'});
    const data=await response.json();if(!response.ok)throw Error(data.detail||'Could not delete stock analysis reports.');
    for(const row of state.rows||[])if(row.symbol===symbol){row.stock_report_count=0;row.stock_score=null;row.stock_rating_label=null}
    for(const row of state.watchlist||[])if(row.symbol===symbol){row.stock_report_count=0;row.stock_score=null;row.stock_rating_label=null}
    updateStockReportsButton(symbol,0);
    renderRows();renderSymbolList();closeStockReportViewer();toast('Purged '+(Number(data.deleted_count)||0)+' stock analysis reports for '+symbol+'.');
  }catch(error){status.textContent=error.message;button.disabled=false}
}
function closeStockReportViewer(){
  $('#stock-report-modal').classList.remove('open');
}

async function analyzeDisplayedSymbols(){
  const button=$('#analyze-displayed-btn'),stockButton=$('#analyze-displayed-stocks-btn'),progress=$('#batch-analysis-status');
  const displayedSymbols=[...new Set([...document.querySelectorAll('#rows .ticker-details-btn')].map(el=>el.textContent.trim()).filter(Boolean))];
  const rowsBySymbol=new Map(state.rows.map(row=>[row.symbol,row]));
  const unavailable=displayedSymbols.filter(symbol=>!hasAnalyzableCallData(rowsBySymbol.get(symbol)));
  const symbols=displayedSymbols.filter(symbol=>hasAnalyzableCallData(rowsBySymbol.get(symbol)));
  if(!symbols.length){
    const message=unavailable.length?`Skipped ${unavailable.length} displayed symbols because option data is unavailable.`:'There are no displayed calls to analyze.';
    progress.textContent=message;
    progress.title=unavailable.map(symbol=>`${symbol}: option data unavailable`).join('\n');
    toast(message);
    return;
  }
  const skipped=unavailable.map(symbol=>`${symbol}: option data unavailable`);
  let updated=0,completed=0;
  button.disabled=true;stockButton.disabled=true;
  button.title='Runs a current-source analysis for each displayed covered call and uses OpenAI API credits.';
  try{
    const batchSize=200,batchCount=Math.ceil(symbols.length/batchSize);
    for(let batchIndex=0;batchIndex<batchCount;batchIndex++){
      const batch=symbols.slice(batchIndex*batchSize,(batchIndex+1)*batchSize);
      for(const symbol of batch){
        const row=rowsBySymbol.get(symbol);
        button.textContent=`Analyzing call ${completed+1}/${symbols.length}…`;
        progress.textContent=`Batch ${batchIndex+1}/${batchCount} · completed ${completed} of ${symbols.length} · analyzing ${symbol}`;
        try{
          const response=await fetch('/options/api/symbol-analysis',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,screen:analysisScreenForRow(row)})});
          const data=await response.json();
          if(!response.ok)throw Error(data.detail||'Analysis request failed');
          if(data.total_score===null||data.total_score===undefined||data.call_score===null||data.call_score===undefined||!Number.isFinite(Number(data.call_score))){
            skipped.push(`${symbol}: no scorecard returned`);
            continue;
          }
          state.rows=state.rows.map(item=>item.symbol===symbol?{...item,call_score:Number(data.call_score)}:item);
          state.watchlist=state.watchlist.map(item=>item.symbol===symbol?{...item,call_score:Number(data.call_score),analysis_count:data.analysis_count}:item);
          updated++;
          renderRows();
        }catch(error){skipped.push(`${symbol}: ${error.message}`)}finally{
          completed++;
          progress.textContent=`Completed ${completed} of ${symbols.length}`;
        }
      }
    }
    const unavailableText=unavailable.length?` · ${unavailable.length} unavailable skipped`:'';
    const failedCount=skipped.length-unavailable.length;
    const failedText=failedCount>0?` · ${failedCount} analysis skipped`:'';
    progress.textContent=`Updated ${updated}/${symbols.length}${unavailableText}${failedText}`;
    progress.title=skipped.join('\n');
    toast(unavailable.length||failedCount?`Updated ${updated} call scores; ${skipped.length} skipped.`:`Updated Call score for ${updated} displayed calls.`);
  }finally{
    button.disabled=false;stockButton.disabled=false;
    button.textContent='Analyze calls';
  }
}
async function analyzeDisplayedStocks(){
  const button=$('#analyze-displayed-stocks-btn'),callButton=$('#analyze-displayed-btn'),progress=$('#batch-analysis-status');
  const symbols=[...new Set([...document.querySelectorAll('#rows .ticker-details-btn')].map(el=>el.textContent.trim()).filter(Boolean))];
  if(!symbols.length){toast('There are no displayed stocks to analyze.');return}
  const labels={1:'Avoid',2:'Sell',3:'Watch',4:'Grow',5:'Bargain'};
  const skipped=[];
  let updated=0,completed=0;
  button.disabled=true;callButton.disabled=true;progress.title='';
  try{
    const batchSize=200,batchCount=Math.ceil(symbols.length/batchSize);
    for(let batchIndex=0;batchIndex<batchCount;batchIndex++){
      const batch=symbols.slice(batchIndex*batchSize,(batchIndex+1)*batchSize);
      for(const symbol of batch){
      button.textContent=`Analyzing stock ${completed+1}/${symbols.length}…`;
      progress.textContent=`Batch ${batchIndex+1}/${batchCount} · completed ${completed} of ${symbols.length} · analyzing ${symbol}`;
      try{
        const quoteResponse=await fetch('/options/api/quote/'+encodeURIComponent(symbol));
        const quote=await quoteResponse.json();
        if(!quoteResponse.ok)throw Error(quote.detail||'Stock quote request failed');
        const response=await fetch('/options/api/stock-analysis',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol,quote})});
        const data=await response.json();
        if(!response.ok)throw Error(data.detail||'Stock analysis request failed');
        state.rows=state.rows.map(item=>item.symbol===symbol?{...item,stock_report_count:Number(data.report_count)||1}:item);
        state.watchlist=state.watchlist.map(item=>item.symbol===symbol?{...item,stock_report_count:Number(data.report_count)||1}:item);
        const rating=Number(data.rating),label=labels[rating]||data.rating_label;
        if(!Number.isInteger(rating)||rating<1||rating>5||!label){
          renderRows();
          skipped.push(`${symbol}: no valid stock rating returned`);
          continue;
        }
        state.rows=state.rows.map(item=>item.symbol===symbol?{...item,stock_score:rating,stock_rating_label:label,stock_report_count:Number(data.report_count)||1}:item);
        state.watchlist=state.watchlist.map(item=>item.symbol===symbol?{...item,stock_score:rating,stock_rating_label:label}:item);
        updated++;
        renderRows();
      }catch(error){skipped.push(`${symbol}: ${error.message}`)}finally{
        completed++;
        progress.textContent=`Completed ${completed} of ${symbols.length}`;
      }
      }
    }
    progress.textContent=skipped.length?`Updated ${updated}/${symbols.length} · ${skipped.length} skipped`:`Updated Stock / 5 for ${updated}/${symbols.length} displayed stocks`;
    progress.title=skipped.join('\n');
    toast(skipped.length?`Updated ${updated} stock scores; ${skipped.length} skipped. See status for details.`:`Updated Stock / 5 for ${updated} displayed stocks.`);
  }finally{
    button.disabled=false;callButton.disabled=false;
    button.textContent='Analyze stocks';
  }
}

let activeCeoRiskSymbol='',activeCeoRiskOffset=0,activeCeoRiskCount=0,activeCeoRiskId=null;
async function viewCeoRiskReports(symbol,offset=0){
  const modal=$('#ceo-risk-report-modal'),status=$('#ceo-risk-report-status');
  activeCeoRiskSymbol=symbol;activeCeoRiskId=null;modal.classList.add('open');status.textContent='Loading saved CEO Risk assessment…';
  $('#ceo-risk-report-delete').disabled=true;$('#ceo-risk-report-purge').disabled=true;
  $('#ceo-risk-report-title').textContent=symbol+' · CEO Risk';$('#ceo-risk-report-score').innerHTML='';$('#ceo-risk-report-profile').innerHTML='';$('#ceo-risk-report-factors').innerHTML='';$('#ceo-risk-report-scenarios').innerHTML='';$('#ceo-risk-report-signals').innerHTML='';$('#ceo-risk-report-citations').innerHTML='';
  try{
    let response=await fetch('/options/api/ceo-risk/reports/'+encodeURIComponent(symbol)+'?offset='+encodeURIComponent(offset),{credentials:'same-origin',cache:'no-store'});let data=await response.json();
    if(response.status===404&&offset===0){status.textContent='No saved CEO Risk report for '+symbol+'. Creating one now…';response=await fetch('/options/api/ceo-risk',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol})});const created=await response.json();if(!response.ok)throw Error(created.detail||'Could not create a CEO Risk report for '+symbol+'.');for(const row of state.watchlist||[])if(String(row.symbol||'').toUpperCase()===symbol){row.ceo_risk_score=created.risk_score;row.ceo_risk_rating=created.risk_rating;row.ceo_risk_updated_at=created.created_at;row.ceo_risk_report_count=created.report_count}renderSymbolList();status.textContent='CEO Risk report created. Loading saved report…';response=await fetch('/options/api/ceo-risk/reports/'+encodeURIComponent(symbol)+'?offset=0',{credentials:'same-origin',cache:'no-store'});data=await response.json()}
    if(!response.ok)throw Error(data.detail||'Saved CEO Risk report is unavailable.');const report=data.report||{};activeCeoRiskOffset=Number(data.offset)||0;activeCeoRiskCount=Number(data.report_count)||0;activeCeoRiskId=Number(report.report_id)||null;
    $('#ceo-risk-report-delete').disabled=!activeCeoRiskId;$('#ceo-risk-report-purge').disabled=activeCeoRiskCount<1;$('#ceo-risk-report-meta').textContent='Report '+(activeCeoRiskOffset+1)+' of '+activeCeoRiskCount+' · '+newsTimestamp(report.created_at);
    for(const row of state.watchlist||[])if(String(row.symbol||'').toUpperCase()===symbol){row.ceo_risk_score=Number(report.risk_score);row.ceo_risk_rating=report.risk_rating;row.ceo_risk_updated_at=report.created_at;row.ceo_risk_report_count=activeCeoRiskCount}const rating=String(report.risk_rating||'Unrated');$('#ceo-risk-report-score').innerHTML='<div class="buffett-overall-score score ceo-risk-rating-'+safe(rating.toLowerCase())+'"><b>'+safe(rating.toUpperCase())+' CEO RISK · '+Number(report.risk_score||0).toFixed(1)+'/100</b><span>Confidence '+safe(String(report.confidence??'—'))+'%</span></div>';
    $('#ceo-risk-report-profile').innerHTML='<div class="buffett-metric"><span>Company</span><b>'+safe(report.company_name||symbol)+'</b></div><div class="buffett-metric"><span>CEO</span><b>'+safe(report.ceo_name||'Not identified')+'</b></div><div class="buffett-metric"><span>Assessment date</span><b>'+safe(report.as_of||'Not specified')+'</b></div><p class="ceo-risk-summary">'+safe(report.summary||'')+'</p>';
    const grades=['LOW','LIMITED','MODERATE','HIGH','SEVERE'];$('#ceo-risk-report-factors').innerHTML=(report.factors||[]).map(item=>{const score=Math.max(0,Math.min(4,Number(item.risk_score)||0));return '<li class="buffett-criterion '+(score>=3?'fail':'pass')+'"><div><b>'+safe(item.name||'Risk factor')+'</b><span>'+grades[score]+' · '+score+'/4</span></div><p>'+safe(item.evidence||'No supporting evidence was saved.')+'</p></li>'}).join('');
    $('#ceo-risk-report-scenarios').innerHTML=(report.scenarios||[]).map(item=>'<li class="ceo-risk-scenario"><b>'+safe(item.event||'Scenario')+'</b><p><strong>Likely effect:</strong> '+safe(item.likely_effect||'')+'</p><p><strong>Recovery path:</strong> '+safe(item.recovery_path||'')+'</p></li>').join('');
    $('#ceo-risk-report-signals').innerHTML=(report.monitor_signals||[]).map(item=>'<li>'+safe(item)+'</li>').join('');$('#ceo-risk-report-citations').innerHTML=(report.citations||[]).map(cite=>'<li><a href="'+safe(cite.url)+'" target="_blank" rel="noopener noreferrer">'+safe(cite.title||cite.url)+'</a></li>').join('');
    $('#ceo-risk-report-previous').disabled=activeCeoRiskOffset>=activeCeoRiskCount-1;$('#ceo-risk-report-next').disabled=activeCeoRiskOffset<=0;status.textContent='';
  }catch(error){status.textContent=error.message;$('#ceo-risk-report-previous').disabled=true;$('#ceo-risk-report-next').disabled=true;$('#ceo-risk-report-delete').disabled=true;$('#ceo-risk-report-purge').disabled=true}
}
function navigateCeoRiskReport(direction){if(!activeCeoRiskSymbol)return;const offset=activeCeoRiskOffset+direction;if(offset<0||offset>=activeCeoRiskCount)return;viewCeoRiskReports(activeCeoRiskSymbol,offset)}
async function deleteCeoRiskReport(){if(!activeCeoRiskSymbol||!activeCeoRiskId)return;const symbol=activeCeoRiskSymbol,reportId=activeCeoRiskId;if(!confirm('Delete this CEO Risk report for '+symbol+'? This cannot be undone.'))return;const status=$('#ceo-risk-report-status'),button=$('#ceo-risk-report-delete');button.disabled=true;status.textContent='Deleting CEO Risk report…';try{const response=await fetch('/options/api/ceo-risk/reports/'+encodeURIComponent(symbol)+'/'+encodeURIComponent(reportId),{method:'DELETE',credentials:'same-origin'});const data=await response.json();if(!response.ok)throw Error(data.detail||'Could not delete the CEO Risk report.');for(const row of state.watchlist||[])if(row.symbol===symbol){row.ceo_risk_report_count=Number(data.report_count)||0;if(!row.ceo_risk_report_count){row.ceo_risk_score=null;row.ceo_risk_rating=null;row.ceo_risk_updated_at=null}}if(Number(data.report_count)>0)await viewCeoRiskReports(symbol,Math.min(activeCeoRiskOffset,Number(data.report_count)-1));else{closeCeoRiskReportViewer();renderSymbolList();toast('Deleted the CEO Risk report. No saved reports remain for '+symbol+'.')}}catch(error){status.textContent=error.message;button.disabled=false}}
async function deleteAllCeoRiskReports(){if(!activeCeoRiskSymbol||activeCeoRiskCount<1)return;const symbol=activeCeoRiskSymbol;if(!confirm('Purge all '+activeCeoRiskCount+' CEO Risk reports for '+symbol+'? This cannot be undone.'))return;const status=$('#ceo-risk-report-status'),button=$('#ceo-risk-report-purge');button.disabled=true;status.textContent='Deleting all CEO Risk reports…';try{const response=await fetch('/options/api/ceo-risk/reports/'+encodeURIComponent(symbol),{method:'DELETE',credentials:'same-origin'});const data=await response.json();if(!response.ok)throw Error(data.detail||'Could not purge CEO Risk reports.');for(const row of state.watchlist||[])if(row.symbol===symbol){row.ceo_risk_score=null;row.ceo_risk_rating=null;row.ceo_risk_updated_at=null;row.ceo_risk_report_count=0}closeCeoRiskReportViewer();renderSymbolList();toast('Purged '+(Number(data.deleted_count)||0)+' CEO Risk reports for '+symbol+'.')}catch(error){status.textContent=error.message;button.disabled=false}}
function closeCeoRiskReportViewer(){$('#ceo-risk-report-modal').classList.remove('open')}
async function purgeAllCeoRiskReports(){if(!state.editingEnabled){$('#ceo-risk-screen-status').textContent='Shared watchlist storage is unavailable; reports cannot be purged.';return}if(!confirm('PURGE ALL CEO RISK REPORTS? This permanently deletes every saved CEO Risk report for all tickers. Buffett reports, stock analyses, and the watchlist will not change.'))return;if(!confirm('Final confirmation: permanently delete all CEO Risk reports?'))return;const button=$('#ceo-risk-purge-btn'),screen=$('#ceo-risk-screen-btn'),status=$('#ceo-risk-screen-status');button.disabled=true;screen.disabled=true;button.textContent='Purging…';status.textContent='Deleting all CEO Risk reports…';try{const response=await fetch('/options/api/ceo-risk/reports',{method:'DELETE',credentials:'same-origin'});const data=await response.json();if(!response.ok)throw Error(data.detail||'Could not purge CEO Risk reports.');for(const row of state.watchlist||[]){row.ceo_risk_score=null;row.ceo_risk_rating=null;row.ceo_risk_updated_at=null;row.ceo_risk_report_count=0}renderSymbolList();status.textContent='Purged '+(Number(data.deleted_count)||0)+' CEO Risk reports.';toast(status.textContent)}catch(error){status.textContent=error.message}finally{button.disabled=false;screen.disabled=false;button.textContent='Purge CEO Risk'}}
async function runCeoRiskScreen(){const symbols=[...new Set(getFilteredSymbolRows().map(row=>String(row.symbol||'').trim().toUpperCase()).filter(Boolean))];if(!symbols.length){$('#ceo-risk-screen-status').textContent='No tickers match the current watchlist filters.';return}if(!state.editingEnabled){$('#ceo-risk-screen-status').textContent='Shared watchlist storage is unavailable; results cannot be saved.';return}if(!confirm('Run CEO Risk research for '+symbols.length+' distinct tickers currently shown? This makes one web research request per ticker and may incur API charges. Higher scores indicate greater CEO dependency and succession risk.'))return;const button=$('#ceo-risk-screen-btn'),status=$('#ceo-risk-screen-status');button.disabled=true;button.textContent='Assessing…';let scores=[],errors=[];try{for(let i=0;i<symbols.length;i++){const symbol=symbols[i];status.textContent='CEO Risk assessment '+(i+1)+'/'+symbols.length+' · '+symbol;try{const response=await fetch('/options/api/ceo-risk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol})});const data=await response.json();if(!response.ok)throw Error(data.detail||('HTTP '+response.status));const score=Number(data.risk_score);state.watchlist.forEach(row=>{if(String(row.symbol||'').toUpperCase()===symbol){row.ceo_risk_score=score;row.ceo_risk_rating=data.risk_rating;row.ceo_risk_updated_at=data.created_at;row.ceo_risk_report_count=data.report_count}});if(Number.isFinite(score))scores.push(score);else errors.push(symbol+': report returned no score')}catch(error){errors.push(symbol+': '+String(error.message||error))}if((i+1)%5===0||i===symbols.length-1)renderSymbolList()}renderSymbolList();const average=scores.length?scores.reduce((sum,value)=>sum+value,0)/scores.length:0;status.textContent='Complete: '+scores.length+' tickers assessed · average risk '+average.toFixed(1)+'/100 · '+errors.length+' research errors.'+(errors.length?' First errors: '+errors.slice(0,3).join(' | '):'');status.title=errors.join('\n')}finally{button.disabled=false;button.textContent='CEO Risk'}}

async function purgeAllBuffettReports(){
  if(!state.editingEnabled){$('#buffett-screen-status').textContent='Shared watchlist storage is unavailable; reports cannot be purged.';return}
  if(!window.confirm('PURGE ALL BUFFETT DATA? This will permanently delete every saved Buffett report and clear every Buffett score for all tickers. The watchlist and stock-analysis reports will not be changed.'))return;
  if(!window.confirm('Final confirmation: permanently delete all Buffett reports and scores?'))return;
  const button=$('#buffett-purge-btn'),screenButton=$('#buffett-screen-btn'),status=$('#buffett-screen-status');
  button.disabled=true;screenButton.disabled=true;button.textContent='Purging…';status.textContent='Deleting all Buffett reports and scores…';
  try{
    const response=await fetch('/options/api/buffett-screen/reports',{method:'DELETE',credentials:'same-origin'});
    const data=await response.json();if(!response.ok)throw Error(data.detail||'Could not purge Buffett reports.');
    for(const row of state.watchlist||[]){
      row.buffett_pass=null;row.buffett_score=null;row.buffett_updated_at=null;row.buffett_criteria_json=null;row.buffett_report_count=0;
    }
    renderSymbolList();
    status.textContent='Purged '+(Number(data.deleted_count)||0)+' Buffett reports and cleared all Buffett scores.';
    toast(status.textContent);
  }catch(error){status.textContent=error.message}
  finally{button.disabled=false;screenButton.disabled=false;button.textContent='Purge'}
}

async function runBuffettScreen(){
  const symbols=[...new Set(getFilteredSymbolRows().map(row=>String(row.symbol||'').trim().toUpperCase()).filter(Boolean))];
  if(!symbols.length){$('#buffett-screen-status').textContent='No tickers match the current watchlist filters.';return}
  if(!state.editingEnabled){$('#buffett-screen-status').textContent='Shared watchlist storage is unavailable; results cannot be saved.';return}
  if(!window.confirm('Run the Buffett screen for '+symbols.length+' distinct tickers currently shown by the watchlist filters? This makes one OpenAI web research request per ticker and may incur API charges. Each ticker receives a percentage score based on its 13 criteria; missing evidence scores 0.'))return;
  const button=$('#buffett-screen-btn'),status=$('#buffett-screen-status');button.disabled=true;button.textContent='Screening…';
  let scores=[],errors=[];
  try{
    for(let i=0;i<symbols.length;i++){
      const symbol=symbols[i];status.textContent='Buffett screen '+(i+1)+'/'+symbols.length+' · '+symbol;
      try{
        const response=await fetch('/options/api/buffett-screen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol})});
        const data=await response.json();if(!response.ok)throw new Error(data.detail||('HTTP '+response.status));
        const returnedScore=Number(data.buffett_score??data.score_percent),criteriaTotal=(data.criteria||[]).length||13,criteriaPassed=(data.criteria||[]).filter(item=>item.pass).length,score=Number.isFinite(returnedScore)?returnedScore:criteriaPassed/criteriaTotal*100;
        state.watchlist.forEach(row=>{if(String(row.symbol||'').toUpperCase()===symbol){row.buffett_pass=data.buffett_pass;row.buffett_score=score;row.buffett_updated_at=data.buffett_updated_at;row.buffett_criteria_json=JSON.stringify({buffett_pass:data.buffett_pass,buffett_score:score,score_percent:score,criteria_passed:criteriaPassed,criteria_total:criteriaTotal,buffett_updated_at:data.buffett_updated_at,criteria:data.criteria,metrics:data.metrics,adjusted_pe:data.adjusted_pe,citations:data.citations});row.buffett_report_count=data.report_count}});
        if(Number.isFinite(score))scores.push(score);else errors.push(symbol+': screen returned no score');
      }catch(error){errors.push(symbol+': '+String(error.message||error))}
      if((i+1)%5===0||i===symbols.length-1)renderSymbolList();
    }
    renderSymbolList();const averageScore=scores.length?scores.reduce((sum,value)=>sum+value,0)/scores.length:0;status.textContent='Complete: '+scores.length+' tickers scored · average '+averageScore.toFixed(1)+'% · '+errors.length+' research errors.'+(errors.length?' First errors: '+errors.slice(0,3).join(' | '):'');status.title=errors.join('\n');
  }finally{button.disabled=false;button.textContent='Buffett'}
}
function pageChain(delta){const next=state.chainIndex+delta;if(next<0||next>=state.chainRows.length)return;state.chainIndex=next;renderChainPage()}
function newsDate(value){if(!value)return 'Date unavailable';const raw=String(value),dateOnly=/^\d{4}-\d{2}-\d{2}$/.test(raw),d=dateOnly?new Date(Number(raw.slice(0,4)),Number(raw.slice(5,7))-1,Number(raw.slice(8,10))):new Date(raw);return Number.isNaN(d.getTime())?raw:new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:dateOnly?undefined:'America/Los_Angeles'}).format(d)}
function newsTimestamp(value){if(!value)return 'Time unavailable';const d=new Date(value);return Number.isNaN(d.getTime())?String(value):new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit',timeZone:'America/Los_Angeles',timeZoneName:'short'}).format(d)}
function newsPeakChip(peak){const cls=peak==='AI/I'?'ai':peak==='EFM/I'?'efm':peak==='DS/I'?'defense':peak==='Cross-Peak'?'other':'other';return `<span class="peak-chip ${cls}"><i class="mini-dot"></i>${safe(peak||'Other')}</span>`}
let activeNewsSpeech=null,activeAnalysisSpeech=null;
let analysisPodcastAudioUrl=null,analysisPodcastTextUrl=null,analysisPodcastAudioBlob=null,analysisPodcastValidatedLinks=[];
let activeNewsStory=null,activeAnalysisCitations=[],youtubeReady=false;

function resetAnalysisPodcast(){analysisPodcastValidatedLinks=[];if(analysisPodcastAudioUrl)URL.revokeObjectURL(analysisPodcastAudioUrl);if(analysisPodcastTextUrl)URL.revokeObjectURL(analysisPodcastTextUrl);analysisPodcastAudioUrl=null;analysisPodcastTextUrl=null;analysisPodcastAudioBlob=null;$('#analysis-podcast-result').hidden=true;$('#analysis-podcast-transcript').value='';$('#analysis-podcast-audio').removeAttribute('src');$('#analysis-podcast-audio').load();$('#analysis-download-mp3').hidden=true;$('#analysis-download-transcript').removeAttribute('href');$('#analysis-download-mp3').removeAttribute('href');$('#youtube-publish-section').hidden=true;$('#youtube-review-confirm').checked=false;$('#youtube-publish-btn').disabled=true;$('#youtube-publish-status').textContent='';$('#analysis-podcast-status').textContent='Uses OpenAI API credits to make a YouTube-ready transcript and narrated MP3.'}
function podcastFileSlug(value){return String(value||'analysis').normalize('NFKD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,72)||'analysis'}
async function readApiError(response,fallback){try{const data=await response.json();return data.detail||fallback}catch(error){return fallback}}
async function createAnalysisPodcast(){const button=$('#analysis-mp3-btn'),status=$('#analysis-podcast-status'),title=$('#symbol-analysis-title').textContent.trim(),subtitle=$('#symbol-analysis-subtitle').textContent.trim(),analysis=$('#symbol-analysis-body').innerText.trim();if(!analysis){status.textContent='Wait for the analysis to finish, then try again.';return}resetAnalysisPodcast();button.disabled=true;button.textContent='Creating YouTube transcript + MP3…';status.textContent='Checking source links, then writing the spoken transcript…';try{const links=[...(activeNewsStory?.url?[activeNewsStory.url]:[]),...activeAnalysisCitations.map(item=>item.url).filter(Boolean)];const scriptResponse=await fetch('/options/api/analysis-podcast/transcript',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,subtitle,analysis,links})});if(!scriptResponse.ok)throw Error(await readApiError(scriptResponse,'Transcript generation failed.'));const scriptData=await scriptResponse.json();analysisPodcastValidatedLinks=Array.isArray(scriptData.validated_links)?scriptData.validated_links:[];const transcript=String(scriptData.transcript||'').trim();if(!transcript)throw Error('OpenAI returned an empty transcript.');$('#analysis-podcast-transcript').value=transcript;analysisPodcastTextUrl=URL.createObjectURL(new Blob([transcript],{type:'text/plain;charset=utf-8'}));const slug=podcastFileSlug(title),transcriptLink=$('#analysis-download-transcript');transcriptLink.href=analysisPodcastTextUrl;transcriptLink.download='RHTC_'+slug+'_YouTube_Transcript.txt';$('#analysis-podcast-result').hidden=false;status.textContent='Transcript ready ('+transcript.length.toLocaleString()+' characters). Creating the MP3…';const audioResponse=await fetch('/options/api/analysis-podcast/audio',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,transcript})});if(!audioResponse.ok)throw Error(await readApiError(audioResponse,'MP3 generation failed.'));const mp3=await audioResponse.blob();if(!mp3.size)throw Error('The MP3 file was empty. Try again.');analysisPodcastAudioBlob=mp3;analysisPodcastAudioUrl=URL.createObjectURL(mp3);$('#analysis-podcast-audio').src=analysisPodcastAudioUrl;const mp3Link=$('#analysis-download-mp3');mp3Link.href=analysisPodcastAudioUrl;mp3Link.download='RHTC_'+slug+'_YouTube.mp3';mp3Link.hidden=false;setupYouTubePublish(title,subtitle,transcript);status.textContent='Ready to review or publish. Download the transcript and MP3 below.'}catch(error){status.textContent=error.message||'Could not create the YouTube assets. Try again.'}finally{button.disabled=false;button.textContent='🎙 Create YouTube Transcript + MP3'}}
async function copyAnalysisPodcastTranscript(){const text=$('#analysis-podcast-transcript').value;if(!text)return;try{await navigator.clipboard.writeText(text);toast('YouTube transcript copied.')}catch(error){const field=$('#analysis-podcast-transcript');field.focus();field.select();toast('Select and copy the transcript.')}}
const NEWS_ARTWORK_THEMES=[['ai_infrastructure','AI/I — AI & Infrastructure'],['energy_fuels_infrastructure','EFM/I — Energy, Fuels & Infrastructure'],['defense_space_infrastructure','DS/I — Defense, Space & Infrastructure'],['policy_power_news','Cross-Peak — Policy & Power'],['think_tank_watch','Think-Tank Watch'],['three_peaks_audio_brief','Three Peaks Audio Brief'],['pentagon_contract_watch','Pentagon Contract Watch']];
function preferredYouTubeSeries(story){const combined=(story.title+' '+story.snippet+' '+story.url).toLowerCase();if(/think[ -]?tank|hudson|fdd|heritage|csis|afpi/.test(combined))return'think_tank_watch';if(/pentagon|contract|award|procurement/.test(combined))return'pentagon_contract_watch';return({'AI/I':'ai_infrastructure','EFM/I':'energy_fuels_infrastructure','DS/I':'defense_space_infrastructure','Cross-Peak':'policy_power_news','Other':'policy_power_news'})[story.peak]||'policy_power_news'}
function youtubeDescription(transcript,story,citationList=activeAnalysisCitations,validatedLinks=analysisPodcastValidatedLinks){const valid=new Set(validatedLinks||[]);const citations=citationList.map(item=>item.url).filter(url=>url&&valid.has(url)).slice(0,10);const storyUrl=story.url&&valid.has(story.url)?story.url:'';const parts=[transcript.slice(0,2600).trim(),storyUrl?'Story: '+storyUrl:'',citations.length?'Additional sources:\n'+citations.join('\n'):'','RHTC Three Peaks analysis. Educational and informational content only; not investment advice.'];return parts.filter(Boolean).join('\n\n').slice(0,5000)}
async function refreshYouTubeStatus(){const status=$('#youtube-publish-status');status.textContent='Checking YouTube connection…';try{const response=await fetch('/options/api/youtube/status');const data=await response.json();youtubeReady=Boolean(response.ok&&data.configured);if(youtubeReady){status.textContent='YouTube connected. News publishing requests Public visibility; YouTube may keep API uploads Private until this project passes its audit.'}else{const missing=(data.missing||[]).join(', ');status.textContent=missing?'Add '+missing+' in Railway Variables to enable uploads.':'MP4 conversion is unavailable in this deployment.'}}catch(error){youtubeReady=false;status.textContent='Could not check YouTube upload readiness.'}updateYouTubePublishButton()}
function updateYouTubePublishButton(){const button=$('#youtube-publish-btn');if(button)button.disabled=analysisPublishBusy||!youtubeReady||!analysisPodcastAudioBlob||!$('#youtube-review-confirm').checked}
function youtubeTitleForTheme(title,series){const theme=NEWS_ARTWORK_THEMES.find(([value])=>value===series);const label=(theme?.[1]||'Policy & Power').split(' — ')[0];return ('RHTC '+label+' | '+title).slice(0,100)}
function setupYouTubePublish(title,subtitle,transcript){const section=$('#youtube-publish-section');if(!activeNewsStory){section.hidden=true;return}section.hidden=false;const story=activeNewsStory,artworkCard=[...document.querySelectorAll('.news-item')].find(item=>item.dataset.newsUrl===story.url);$('#youtube-series').value=artworkCard?.dataset.newsArtworkTheme||preferredYouTubeSeries(story);$('#youtube-video-title').value=youtubeTitleForTheme(story.title,$('#youtube-series').value);$('#youtube-video-description').value=youtubeDescription(transcript,story);$('#youtube-review-confirm').checked=false;$('#youtube-publish-status').textContent='Review the complete MP3, title, description, and artwork before uploading.';refreshYouTubeStatus()}
const analysisYouTubeUploads=new Map();
let analysisPublishBusy=false,activeNewsPublishCard=null;
async function publishAnalysisToYouTube(){
  const button=$('#youtube-publish-btn'),status=$('#youtube-publish-status'),story=activeNewsStory;
  if(analysisPublishBusy)return;
  if(!analysisPodcastAudioBlob||!story){status.textContent='Create the analysis MP3 first.';return}
  if(!$('#youtube-review-confirm').checked){status.textContent='Confirm that you reviewed the MP3 and publishing details.';return}
  const sourceUrl=story.url||'';
  const card=[...document.querySelectorAll('.news-item')].find(item=>item.dataset.newsUrl===sourceUrl)||activeNewsPublishCard;
  if(!sourceUrl||!card||card.dataset.newsUrl!==sourceUrl){status.textContent='Reopen this story from the news feed before publishing.';return}
  const feedButton=card.querySelector('.news-publish-btn');
  if(feedButton.disabled&&card.dataset.newsYoutubePublished!=='true'){status.textContent='This story is already being published from the news feed.';return}
  analysisPublishBusy=true;button.disabled=true;feedButton.disabled=true;
  let uploaded=analysisYouTubeUploads.get(sourceUrl);
  try{
    if(!uploaded&&card.dataset.newsYoutubePublished==='true')uploaded={url:card.dataset.newsYoutubeUrl,privacy_status:card.dataset.newsYoutubePrivacy};
    if(!uploaded){
      const form=new FormData();
      form.append('audio',analysisPodcastAudioBlob,'RHTC_news_analysis.mp3');
      form.append('title',$('#youtube-video-title').value.trim());
      form.append('description',$('#youtube-video-description').value.trim());
      form.append('series',$('#youtube-series').value);
      form.append('privacy_status',$('#youtube-privacy').value);
      form.append('story_url',sourceUrl);
      button.textContent='Converting and uploading…';status.textContent='Creating the branded MP4 and uploading it to YouTube…';
      const response=await fetch('/options/api/youtube/publish',{method:'POST',body:form});
      if(!response.ok)throw Error(await readApiError(response,'YouTube upload failed.'));
      uploaded=await response.json();
      if(!uploaded.url||!uploaded.video_id)throw Error('YouTube did not return a confirmed video link.');
      analysisYouTubeUploads.set(sourceUrl,uploaded);
    }
    card.dataset.newsYoutubePublished='true';card.dataset.newsYoutubeUrl=uploaded.url;card.dataset.newsYoutubePrivacy=uploaded.privacy_status||'private';
    updateNewsPublishControl(card);
    if(!['public','unlisted'].includes(String(uploaded.privacy_status).toLowerCase())){
      status.innerHTML='Uploaded to YouTube as '+safe(uploaded.privacy_status||'private')+'. Make the video Public or Unlisted before posting to X. <a href="'+safe(uploaded.url)+'" target="_blank" rel="noopener noreferrer">Open YouTube</a>';
      return;
    }
    button.textContent='Posting to X…';status.textContent='YouTube uploaded. Posting its video link to X…';
    const complete=await publishNewsStoryToX(card,feedButton);
    if(complete){status.innerHTML='Published to YouTube and X. '+card.querySelector('.news-publish-status').innerHTML;toast('Published to YouTube and X.');}
    else status.textContent='YouTube uploaded. '+card.querySelector('.news-publish-status').textContent;
  }catch(error){
    status.textContent=error.message||'Publishing failed.';
    // The upload endpoint saves its confirmed video before responding. Recover
    // that record so retrying the report does not upload the same story again.
    await loadNews({quiet:true});
    activeNewsPublishCard=[...document.querySelectorAll('.news-item')].find(item=>item.dataset.newsUrl===sourceUrl)||card;
  }finally{
    updateNewsPublishControl(card);
    await loadNews({quiet:true});
    analysisPublishBusy=false;button.textContent='▶ Publish to YouTube + X';updateYouTubePublishButton();
  }
}


function updateAnalysisSpeechControls(){const read=$('#analysis-read-btn'),stop=$('#analysis-stop-btn'),supported='speechSynthesis'in window&&'SpeechSynthesisUtterance'in window;if(!read||!stop)return;read.hidden=!supported;read.disabled=!supported;read.textContent=activeAnalysisSpeech?(activeAnalysisSpeech.paused?'▶ Resume':'Ⅱ Pause'):'🔊 Read analysis';stop.hidden=!activeAnalysisSpeech}
let autoReloadTimer=null;
function setAutoReload(value,persist=true){const select=$('#auto-reload');const seconds=Number(value)||0;select.value=String(seconds);if(autoReloadTimer){clearInterval(autoReloadTimer);autoReloadTimer=null}if(seconds>0){autoReloadTimer=setInterval(()=>{if(document.hidden||$('#refresh').disabled)return;loadRows({ai:false,snapshot:false})},seconds*1000)}if(persist){try{localStorage.setItem('rhtc-options-auto-reload',String(seconds))}catch(e){}}}
function stopAnalysisSpeech(refresh=true){const current=activeAnalysisSpeech;activeAnalysisSpeech=null;if(current&&'speechSynthesis'in window)window.speechSynthesis.cancel();if(refresh)updateAnalysisSpeechControls();return current}
function toggleAnalysisSpeech(){if(!('speechSynthesis'in window)||!('SpeechSynthesisUtterance'in window)){toast('Read aloud is not available in this browser.');return}if(activeAnalysisSpeech){if(activeAnalysisSpeech.paused){window.speechSynthesis.resume();activeAnalysisSpeech.paused=false}else{window.speechSynthesis.pause();activeAnalysisSpeech.paused=true}updateAnalysisSpeechControls();return}stopNewsSpeech(false);const text=[$('#symbol-analysis-title').textContent,$('#symbol-analysis-subtitle').textContent,$('#symbol-analysis-body').innerText].filter(Boolean).join('. ');if(!text.trim())return;const utterance=new SpeechSynthesisUtterance(text),speech={utterance,paused:false};activeAnalysisSpeech=speech;const finish=()=>{if(activeAnalysisSpeech===speech){activeAnalysisSpeech=null;updateAnalysisSpeechControls()}};utterance.onend=finish;utterance.onerror=finish;try{window.speechSynthesis.speak(utterance);updateAnalysisSpeechControls();updateNewsSpeechControls()}catch(error){finish();toast('Could not read this analysis aloud.')}}
function stopNewsSpeech(refresh=true){const current=activeNewsSpeech;activeNewsSpeech=null;if(activeAnalysisSpeech){activeAnalysisSpeech=null;updateAnalysisSpeechControls()}if('speechSynthesis'in window)window.speechSynthesis.cancel();if(refresh){updateNewsSpeechControls();updateAnalysisSpeechControls()}return current}
function updateNewsSpeechControls(){const supported='speechSynthesis'in window&&'SpeechSynthesisUtterance'in window;document.querySelectorAll('.news-item').forEach(card=>{const read=card.querySelector('[data-news-action="read"]'),stop=card.querySelector('[data-news-action="stop"]');if(!read||!stop)return;const current=activeNewsSpeech&&activeNewsSpeech.url===card.dataset.newsUrl;read.disabled=!supported;read.textContent=current?(activeNewsSpeech.paused?'▶ Resume':'Ⅱ Pause'):'🔊 Read excerpt';read.setAttribute('aria-label',current?`${activeNewsSpeech.paused?'Resume':'Pause'} reading ${card.querySelector('h3 a')?.textContent||'this story'}`:`Read title and excerpt aloud: ${card.querySelector('h3 a')?.textContent||'story'}`);stop.hidden=!current})}
function toggleNewsSpeech(card){if(!('speechSynthesis'in window)||!('SpeechSynthesisUtterance'in window)){toast('Read aloud is not available in this browser.');return}if(activeNewsSpeech&&activeNewsSpeech.url===card.dataset.newsUrl){if(activeNewsSpeech.paused){window.speechSynthesis.resume();activeNewsSpeech.paused=false}else{window.speechSynthesis.pause();activeNewsSpeech.paused=true}updateNewsSpeechControls();return}stopAnalysisSpeech(false);stopNewsSpeech(false);const title=card.querySelector('h3 a')?.textContent||'';const source=card.querySelector('.news-source')?.textContent||'';const excerpt=card.querySelector('.news-excerpt')?.textContent||'';const utterance=new SpeechSynthesisUtterance([title,source?`Source: ${source}`:'',excerpt].filter(Boolean).join('. '));const speech={url:card.dataset.newsUrl,utterance,paused:false};activeNewsSpeech=speech;const finish=()=>{if(activeNewsSpeech===speech){activeNewsSpeech=null;updateNewsSpeechControls()}};utterance.onend=finish;utterance.onerror=finish;try{window.speechSynthesis.speak(utterance);updateNewsSpeechControls();updateAnalysisSpeechControls()}catch(error){finish();toast('Could not read this excerpt aloud.')}}
async function analyzeNewsStory(card,button){
  const modal=$('#symbol-analysis-modal'),body=$('#symbol-analysis-body'),sources=$('#symbol-analysis-sources'),status=$('#symbol-analysis-status');
  const title=card.dataset.newsTitle||card.querySelector('h3 a')?.textContent||'News story';
  activeNewsPublishCard=card;activeNewsStory={title,url:card.dataset.newsUrl||'',snippet:card.dataset.newsSnippet||'',peak:card.dataset.newsPeak||'Other'};activeAnalysisCitations=[];$('#symbol-analysis-title').textContent='RHTC Policy & Power';
  stopNewsSpeech(false);resetAnalysisPodcast();$('#analysis-read-btn').hidden=true;$('#analysis-mp3-btn').disabled=true;$('#symbol-analysis-subtitle').textContent=`${title} · Watchlist companies, Three Peaks, and thesis`;body.textContent='Checking current sources and mapping potential impacts…';sources.innerHTML='';status.textContent='Uses OpenAI web search. Impacts are analytical assessments, not price targets.';openFullscreenModal(modal,modal.querySelector('.analysis-modal'),$('#analysis-fullscreen-toggle'));button.disabled=true;
  try{
    const response=await fetch('/options/api/news/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,url:card.dataset.newsUrl||'',snippet:card.dataset.newsSnippet||'',published_at:card.dataset.newsPublishedAt||''})});
    const data=await response.json();if(!response.ok)throw Error(data.detail||'News analysis request failed.');
    body.innerHTML=renderAnalysis(data.analysis||'No analysis was returned.');
    activeAnalysisCitations=data.citations||[];sources.innerHTML=activeAnalysisCitations.map(citation=>`<li><a href="${safe(citation.url)}" target="_blank" rel="noopener noreferrer">${safe(citation.title||citation.url)}</a></li>`).join('');
    status.textContent=`Generated by ChatGPT${data.citations?.length?` · ${data.citations.length} cited sources`:''}`;
    updateAnalysisSpeechControls();
    $('#analysis-mp3-btn').disabled=false;
  }catch(error){body.textContent=error.message.includes('OPENAI_API_KEY')?'News analysis is not enabled on the server yet. Add OPENAI_API_KEY to Railway Variables, then redeploy.':error.message;status.textContent='Analysis unavailable'}
  finally{button.disabled=false}
}
const X_PENDING_STORAGE_KEY='rhtc_x_publish_pending_v1';
function readPendingXPosts(){try{return JSON.parse(localStorage.getItem(X_PENDING_STORAGE_KEY)||'{}')}catch{return {}}}
function writePendingXPost(url,pending){try{const entries=readPendingXPosts();entries[url]=pending;localStorage.setItem(X_PENDING_STORAGE_KEY,JSON.stringify(entries));return true}catch{return false}}
function clearPendingXPost(url){try{const entries=readPendingXPosts();delete entries[url];localStorage.setItem(X_PENDING_STORAGE_KEY,JSON.stringify(entries))}catch{}}
function updateNewsPublishControl(card){const youtubePublished=card.dataset.newsYoutubePublished==='true',xPublished=card.dataset.newsXPublished==='true',complete=youtubePublished&&xPublished,blocked=youtubePublished&&(!card.dataset.newsYoutubeUrl||String(card.dataset.newsYoutubePrivacy||'').toLowerCase()==='private'),button=card.querySelector('.news-publish-btn'),check=card.querySelector('.news-workflow-check');if(check){check.textContent=complete?'✓':'□';check.dataset.published=String(complete);check.title=complete?'Published to YouTube and X':'Check appears when YouTube and X publishing are both complete';check.setAttribute('aria-label',complete?'Published to YouTube and X':'Publishing workflow incomplete')}if(button){button.disabled=complete||blocked;button.textContent=complete?'✓ Published':'▶ Publish + X';if(blocked)button.title='Publish the RHTC video publicly or unlisted before posting to X';else button.removeAttribute('title')}}
function markXPostSaved(card,pending){card.dataset.newsXPublished='true';updateNewsPublishControl(card);const status=card.querySelector('.news-publish-status');if(status){const yt=card.dataset.newsYoutubeUrl||'';status.hidden=false;status.innerHTML='Published to YouTube and X: <a href="'+safe(yt)+'" target="_blank" rel="noopener noreferrer">Open YouTube</a> · <a href="'+safe(pending.post_url)+'" target="_blank" rel="noopener noreferrer">Open X post</a>'}}
async function savePendingXPost(card,pending){const status=card.querySelector('.news-publish-status'),button=card.querySelector('.news-publish-btn'),url=card.dataset.newsUrl||'';if(!pending?.post_id||!pending?.post_url)return false;if(button){button.disabled=true;button.textContent='Saving X status…'}if(status){status.hidden=false;status.textContent='The X post exists. Saving its publication record…'}try{const response=await fetch('/options/api/news/x-published',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,post_id:pending.post_id,post_url:pending.post_url})});if(!response.ok)throw Error(await readApiError(response,'The X post exists, but its status could not be saved.'));clearPendingXPost(url);markXPostSaved(card,pending);toast('X publication status saved.');return true}catch(error){if(button){button.disabled=false;button.textContent='↻ Retry save'}if(status){status.hidden=false;status.textContent=(error.message||'The X post exists, but its status could not be saved.')+' Tap Publish to retry saving its status; this will not create another post.'}return false}}
function restorePendingXPost(card){const url=card.dataset.newsUrl||'',published=card.dataset.newsXPublished==='true',pending=readPendingXPosts()[url];if(published){clearPendingXPost(url);updateNewsPublishControl(card);return}if(!pending)return;if(pending.stage==='saved'){void savePendingXPost(card,pending);return}const button=card.querySelector('.news-publish-btn'),status=card.querySelector('.news-publish-status');if(button){button.disabled=true;button.textContent='X result unknown'}if(status){status.hidden=false;status.textContent='A previous X request may or may not have posted. Check your X profile before retrying. ';const recovery=document.createElement('button');recovery.type='button';recovery.dataset.newsAction='retry-x';recovery.textContent='I checked X—allow retry';status.append(recovery)}}
function renderNews(items){if(activeNewsSpeech)stopNewsSpeech(false);const container=$('#news-items');$('#news-count').textContent=items.length?`${items.length} ${items.length===1?'story':'stories'} · all stored stories`:'No matching stories.';$('#count-news').textContent=items.length?String(items.length):'0';if(!items.length){container.innerHTML='<p class="news-empty">No stories match these filters yet. The daily scan runs at 6:00 a.m. Pacific; use Scan for news to search now.</p>';return}container.innerHTML=items.map(item=>{const storedUrl=String(item.url||'');const manualStory=/^https:\/\/manual\.rhtc\.invalid\//i.test(storedUrl);const url=!manualStory&&/^https?:\/\//i.test(storedUrl)?storedUrl:'#';const language=String(item.language||'en').toLowerCase().split('-')[0];const youtubePublished=Boolean(Number(item.youtube_published));const savedYoutubeUrl=String(item.youtube_url||'').trim();const youtubeId=String(item.youtube_video_id||'').trim();const youtubeUrl=/^https?:\/\//i.test(savedYoutubeUrl)?savedYoutubeUrl:(youtubeId?'https://www.youtube.com/watch?v='+encodeURIComponent(youtubeId):'');const youtubePrivacy=String(item.youtube_privacy_status||'').toLowerCase();const xPublished=Boolean(Number(item.x_published));const workflowPublished=youtubePublished&&xPublished;const publishBlocked=youtubePublished&&!xPublished&&(!youtubeUrl||youtubePrivacy==='private');const publishCheck='<span class="news-workflow-check" data-published="'+workflowPublished+'" role="img" aria-label="'+(workflowPublished?'Published to YouTube and X':'Publishing workflow incomplete')+'" title="'+(workflowPublished?'Published to YouTube and X':'Check appears when YouTube and X publishing are both complete')+'">'+(workflowPublished?'✓':'□')+'</span>';const publishButton='<button class="news-publish-btn" type="button" data-news-action="publish"'+(workflowPublished||publishBlocked?' disabled':'')+(publishBlocked?' title="Publish the RHTC video publicly or unlisted before posting to X"':'')+'>▶ Publish + X</button>'+publishCheck;const republishButton=workflowPublished?'<button class="news-publish-btn news-republish-btn" type="button" data-news-action="republish">↻ Republish + X</button>':'';const peakOptions=['AI/I','EFM/I','DS/I','Cross-Peak','Other'].map(peak=>'<option value="'+safe(peak)+'"'+(peak===(item.peak||'Other')?' selected':'')+'>'+safe(peak)+'</option>').join('');const artworkTheme=String(item.youtube_series||'').trim()||preferredYouTubeSeries({title:item.title||'',snippet:item.snippet||'',url:storedUrl,peak:item.peak||'Other'});const artworkOptions=NEWS_ARTWORK_THEMES.map(([value,label])=>'<option value="'+safe(value)+'"'+(value===artworkTheme?' selected':'')+'>'+safe(label)+'</option>').join('');const published= youtubePublished||xPublished;const storyTools='<button class="news-peak-change-btn" type="button" data-news-action="change-peak">◇ Change Peak</button><select class="news-peak-select" data-news-action="save-peak" aria-label="Assign peak" hidden>'+peakOptions+'</select><label class="news-artwork-control">Artwork theme<select class="news-artwork-select" data-news-action="save-artwork-theme" aria-label="Assign artwork theme">'+artworkOptions+'</select></label><button class="news-delete-btn" type="button" data-news-action="delete-story"'+(published?' disabled title="Published stories cannot be deleted"':' title="Delete this unpublished story"')+'>Delete</button>';const translateButton=language!=='en'?'<button class="news-read-btn news-translate-btn" type="button" data-news-action="translate" title="Translate the title and excerpt to English">Translate to English</button>':'';return `<article class="news-item" data-news-url="${safe(storedUrl)}" data-news-youtube-url="${safe(youtubeUrl)}" data-news-youtube-published="${youtubePublished}" data-news-youtube-privacy="${safe(youtubePrivacy)}" data-news-x-published="${xPublished}" data-news-title="${safe(item.title||'')}" data-news-peak="${safe(item.peak||'Other')}" data-news-artwork-theme="${safe(artworkTheme)}" data-news-snippet="${safe(item.snippet||'')}" data-news-published-at="${safe(item.published_at||item.first_seen_at||'')}"><div class="news-item-meta">${newsPeakChip(item.peak)}<span class="news-source">${safe(item.source||'Source')}</span><span>Published ${safe(newsDate(item.published_at))}</span><time class="news-retrieved">Retrieved ${safe(newsTimestamp(item.last_seen_at||item.first_seen_at))}</time></div><h3>${manualStory?safe(item.title):`<a href="${safe(url)}" target="_blank" rel="noopener noreferrer">${safe(item.title)}</a>`}</h3><p class="news-excerpt">${safe(item.snippet||'No source excerpt was returned.')}</p><div class="news-item-actions"><button class="news-read-btn" type="button" data-news-action="read">🔊 Read excerpt</button><button class="news-stop-btn" type="button" data-news-action="stop" aria-label="Stop reading this excerpt" hidden>Stop</button><button class="news-analyze-btn" type="button" data-news-action="analyze">✦ Analyze RHTC impact</button>${publishButton}${republishButton}${storyTools}${translateButton}</div><p class="news-publish-status" role="status" aria-live="polite" hidden></p><p class="news-translation" aria-live="polite" hidden></p></article>`}).join('');container.querySelectorAll('.news-item').forEach(restorePendingXPost);updateNewsSpeechControls()}

async function changeNewsArtworkTheme(card,select){
  const status=card.querySelector('.news-publish-status');
  const artworkTheme=select.value;
  select.disabled=true;
  try{
    const response=await fetch('/options/api/news/artwork',{method:'PATCH',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:card.dataset.newsUrl,artwork_theme:artworkTheme})});
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Could not save the artwork theme.');
    card.dataset.newsArtworkTheme=data.artwork_theme;
    const choice=NEWS_ARTWORK_THEMES.find(([value])=>value===data.artwork_theme);
    toast('Artwork theme saved: '+(choice?.[1]||data.artwork_theme)+'.');
  }catch(error){
    select.value=card.dataset.newsArtworkTheme||preferredYouTubeSeries({title:card.dataset.newsTitle||'',snippet:card.dataset.newsSnippet||'',url:card.dataset.newsUrl||'',peak:card.dataset.newsPeak||'Other'});
    status.hidden=false;
    status.textContent=error.message||'Could not save the artwork theme.';
    toast(status.textContent);
  }finally{select.disabled=false}
}

async function changeNewsPeak(card,select){
  const status=card.querySelector('.news-publish-status');
  const peak=select.value;
  select.disabled=true;
  try{
    const response=await fetch('/options/api/news/peak',{method:'PATCH',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:card.dataset.newsUrl,peak})});
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Could not change this story’s peak.');
    card.dataset.newsPeak=data.peak;
    const chip=card.querySelector('.news-item-meta .peak-chip');
    if(chip)chip.outerHTML=newsPeakChip(data.peak);
    toast('Peak changed to '+data.peak+'.');
  }catch(error){
    select.value=card.dataset.newsPeak||'Other';
    status.hidden=false;
    status.textContent=error.message||'Could not change this story’s peak.';
    toast(status.textContent);
  }finally{
    select.disabled=false;
    select.hidden=true;
  }
}

async function deleteNewsStory(card,button){
  if(button.disabled)return;
  if(!window.confirm('Delete this unpublished story from the stored news feed? This cannot be undone.'))return;
  const status=card.querySelector('.news-publish-status');
  const original=button.textContent;
  button.disabled=true;
  button.textContent='Deleting…';
  try{
    const response=await fetch('/options/api/news/delete',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:card.dataset.newsUrl})});
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Could not delete this story.');
    clearPendingXPost(card.dataset.newsUrl);
    card.remove();
    await loadNews({quiet:true});
    toast('Unpublished story deleted.');
  }catch(error){
    status.hidden=false;
    status.textContent=error.message||'Could not delete this story.';
    button.disabled=false;
    button.textContent=original;
    toast(status.textContent);
  }
}

function unlockXRetry(card){const sourceUrl=card.dataset.newsUrl||'';if(!sourceUrl||!window.confirm('Check your X profile first. If this story is not there, clear the duplicate block and allow a retry with the RHTC YouTube link.'))return;clearPendingXPost(sourceUrl);updateNewsPublishControl(card);const status=card.querySelector('.news-publish-status');if(status){status.hidden=false;status.textContent=card.dataset.newsYoutubeUrl?'Retry is unlocked. Publish will post the RHTC YouTube link.':'No saved YouTube link is available yet; publish the video before retrying.'}}

async function publishNewsStoryToX(card,button){
  const status=card.querySelector('.news-publish-status');
  const sourceUrl=card.dataset.newsUrl||'',youtubeUrl=card.dataset.newsYoutubeUrl||'';
  const story={title:card.dataset.newsTitle||card.querySelector('h3 a')?.textContent||'News story',url:youtubeUrl,peak:card.dataset.newsPeak||'Other',story_url:sourceUrl,artwork_theme:card.dataset.newsArtworkTheme||'policy_power_news'};
  if(!sourceUrl||sourceUrl==='#'){toast('This story has no valid source link.');return false}
  if(card.dataset.newsXPublished==='true'){updateNewsPublishControl(card);return true}
  if(!/^https?:\/\//i.test(youtubeUrl)||String(card.dataset.newsYoutubePrivacy||'').toLowerCase()==='private'){status.hidden=false;status.textContent='Publish this story publicly or unlisted to YouTube first so X can link to the RHTC video.';return false}
  const pending=readPendingXPosts()[sourceUrl];if(pending?.stage==='saved'){return await savePendingXPost(card,pending)}if(pending){restorePendingXPost(card);return false}
  if(!writePendingXPost(sourceUrl,{stage:'posting',started_at:new Date().toISOString()})){status.hidden=false;status.textContent='Browser storage is unavailable, so this post cannot be started safely.';return false}
  button.disabled=true;button.textContent='Posting to X…';status.hidden=false;status.textContent='YouTube is published. Posting its RHTC video link to X…';
  try{
    const response=await fetch('/options/api/x/publish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(story)});
    if(!response.ok){const message=await readApiError(response,'X publishing failed.');if(response.status<500){clearPendingXPost(sourceUrl);button.disabled=false;button.textContent='▶ Publish + X';status.hidden=false;status.textContent=message+' No X post was created. Tap Publish + X to retry after correcting the issue.';return false}throw Error(message)}
    const data=await response.json();
    const confirmed={stage:'saved',post_id:data.post_id,post_url:data.url};if(!writePendingXPost(sourceUrl,confirmed)){button.disabled=true;button.textContent='X result unknown';status.textContent='X returned a Post ID, but this browser could not save it. Check your X profile before retrying.';return false}
    return await savePendingXPost(card,confirmed);
  }catch(error){
    // The server now persists X's confirmed Post ID before replying. Refresh
    // the feed after a browser/network error so that saved result is recovered.
    try{
      await loadNews({quiet:true});
      const refreshed=[...document.querySelectorAll('.news-item')].find(item=>item.dataset.newsUrl===sourceUrl);
      if(refreshed?.dataset.newsXPublished==='true'){
        clearPendingXPost(sourceUrl);
        updateNewsPublishControl(refreshed);
        toast('X post confirmed and saved.');
        return true;
      }
    }catch{}
    button.disabled=true;button.textContent='X result unknown';status.textContent=(error.message||'X publishing did not return a confirmed result.')+' Check your X profile before retrying; this story is blocked to prevent a duplicate.';return false
  }
}
async function republishNewsStory(card,button){
  if(button.disabled)return;
  const confirmed=window.confirm('Have you manually deleted both the previous YouTube episode and its X post? This clears their saved IDs and starts a new YouTube upload and X post.');
  if(!confirmed)return;
  const status=card.querySelector('.news-publish-status');
  button.disabled=true;
  button.textContent='Resetting publication…';
  try{
    const response=await fetch('/options/api/news/republish-reset',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:card.dataset.newsUrl})});
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Could not prepare this story for republishing.');
    card.dataset.newsYoutubePublished='false';
    card.dataset.newsYoutubeUrl='';
    card.dataset.newsYoutubePrivacy='';
    card.dataset.newsXPublished='false';
    clearPendingXPost(card.dataset.newsUrl);
    const republish=card.querySelector('[data-news-action="republish"]');
    if(republish)republish.hidden=true;
    const deleteButton=card.querySelector('.news-delete-btn');
    if(deleteButton){deleteButton.disabled=false;deleteButton.title='Delete this unpublished story'}
    updateNewsPublishControl(card);
    const publishButton=card.querySelector('[data-news-action="publish"]');
    await publishNewsStory(card,publishButton);
  }catch(error){
    button.disabled=false;
    button.textContent='↻ Republish + X';
    status.hidden=false;
    status.textContent=error.message||'Could not prepare this story for republishing.';
  }
}

async function publishNewsStory(card,button){
  const status=card.querySelector('.news-publish-status');
  const story={
    title:card.dataset.newsTitle||card.querySelector('h3 a')?.textContent||'News story',
    url:card.dataset.newsUrl||'',
    snippet:card.dataset.newsSnippet||'',
    peak:card.dataset.newsPeak||'Other',
    artwork_theme:card.dataset.newsArtworkTheme||preferredYouTubeSeries({title:card.dataset.newsTitle||'',snippet:card.dataset.newsSnippet||'',url:card.dataset.newsUrl||'',peak:card.dataset.newsPeak||'Other'}),
    published_at:card.dataset.newsPublishedAt||'',
    source:card.querySelector('.news-source')?.textContent||'',
  };
  if(!story.url||story.url==='#'){toast('This story has no valid source link.');return}
  if(card.dataset.newsYoutubePublished==='true'){await publishNewsStoryToX(card,button);return}
  let stage='News analysis';
  let uploadSucceeded=false;
  button.disabled=true;
  status.hidden=false;
  status.textContent='Analyzing RHTC impact…';
  try{
    const analysisResponse=await fetch('/options/api/news/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(story)});
    if(!analysisResponse.ok)throw Error(await readApiError(analysisResponse,'News analysis failed.'));
    const analysisData=await analysisResponse.json();
    const analysis=String(analysisData.analysis||'').trim();
    if(!analysis)throw Error('No analysis was returned.');

    const videoTitle=youtubeTitleForTheme(story.title,story.artwork_theme);
    const subtitle=story.peak+' · '+(story.published_at?'Published '+story.published_at:'Current news')+' · '+story.source;
    stage='Transcript creation';
    status.textContent='Checking story and citation links, then creating the spoken transcript…';
    const citationLinks=(analysisData.citations||[]).map(item=>item.url).filter(Boolean);
    const scriptResponse=await fetch('/options/api/analysis-podcast/transcript',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:videoTitle,subtitle,analysis,links:[story.url,...citationLinks]})});
    if(!scriptResponse.ok)throw Error(await readApiError(scriptResponse,'Transcript generation failed.'));
    const scriptData=await scriptResponse.json();
    const transcript=String(scriptData.transcript||'').trim();
    if(!transcript)throw Error('The transcript was empty.');

    stage='MP3 creation';
    status.textContent='Transcript ready. Creating the narrated MP3…';
    const audioResponse=await fetch('/options/api/analysis-podcast/audio',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:videoTitle,transcript})});
    if(!audioResponse.ok)throw Error(await readApiError(audioResponse,'MP3 generation failed.'));
    const mp3=await audioResponse.blob();
    if(!mp3.size)throw Error('The MP3 file was empty.');

    stage='MP4 creation and YouTube upload';
    status.textContent='MP3 ready. Creating the themed MP4 and uploading to YouTube as Public…';
    const form=new FormData();
    form.append('audio',mp3,'RHTC_'+podcastFileSlug(story.title)+'_YouTube.mp3');
    form.append('title',videoTitle);
    form.append('description',youtubeDescription(transcript,story,analysisData.citations||[],scriptData.validated_links||[]));
    form.append('series',story.artwork_theme);
    form.append('privacy_status','public');
    form.append('story_url',story.url);
    const uploadResponse=await fetch('/options/api/youtube/publish',{method:'POST',body:form});
    if(!uploadResponse.ok)throw Error(await readApiError(uploadResponse,'YouTube upload failed.'));
    const uploadData=await uploadResponse.json();
    if(!uploadData.url||!uploadData.video_id)throw Error('YouTube did not return a confirmed video link.');
    uploadSucceeded=true;
    stage='Save YouTube publication status';
    const publishedResponse=await fetch('/options/api/news/published',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:story.url,video_id:uploadData.video_id,video_url:uploadData.url,privacy_status:uploadData.privacy_status||'private'})});
    if(!publishedResponse.ok)throw Error(await readApiError(publishedResponse,'The upload succeeded, but its status could not be saved to the feed.'));
    const actualPrivacy=String(uploadData.privacy_status||'private').toLowerCase();
    const check=card.querySelector('.news-workflow-check');
    card.dataset.newsYoutubePublished='true';card.dataset.newsYoutubeUrl=uploadData.url;card.dataset.newsYoutubePrivacy=actualPrivacy;updateNewsPublishControl(card);
    if(actualPrivacy==='public'||actualPrivacy==='unlisted'){
      status.hidden=false;status.textContent='YouTube upload complete. Posting the RHTC video link to X…';
      await publishNewsStoryToX(card,button);
      if(card.dataset.newsXPublished==='true')toast('Published to YouTube and X.');
    }else{
      status.innerHTML='YouTube upload completed as '+safe(actualPrivacy)+'. Change the video to Public or Unlisted before X can link to it. <a href="'+safe(uploadData.url)+'" target="_blank" rel="noopener noreferrer">Open on YouTube</a>';
      status.hidden=false;updateNewsPublishControl(card);
    }
  }catch(error){
    if(stage==='MP4 creation and YouTube upload'||stage==='Save YouTube publication status'){
      // The upload route records its video ID server-side before responding.
      // Re-read that record before offering another upload; if it exists,
      // resume the X step using the refreshed card instead of uploading twice.
      try{
        await loadNews({quiet:true});
        const refreshed=[...document.querySelectorAll('.news-item')].find(item=>item.dataset.newsUrl===story.url);
        if(refreshed?.dataset.newsYoutubePublished==='true'){
          const refreshedButton=refreshed.querySelector('.news-publish-btn');
          if(refreshed.dataset.newsXPublished!=='true'&&refreshedButton&&!refreshedButton.disabled){
            await publishNewsStoryToX(refreshed,refreshedButton);
          }else if(refreshed.dataset.newsXPublished==='true'){
            toast('YouTube and X publication records confirmed.');
          }
          return;
        }
      }catch{}
    }
    status.textContent=stage+' failed: '+(error.message||'Try again.');
    if(stage==='MP4 creation and YouTube upload')status.textContent+=' Check YouTube Studio before retrying if the upload result is unclear.';
    status.hidden=false;
    button.disabled=uploadSucceeded;
    button.textContent=uploadSucceeded?'▶ Publish':'↻ Retry Publish';
    if(uploadSucceeded)status.textContent='YouTube upload succeeded, but the feed could not save its published checkmark. Check YouTube Studio before retrying.';
  }
}

async function translateNewsStory(card,button){
  const panel=card.querySelector(".news-translation");
  if(!panel)return;
  if(!panel.hidden){panel.hidden=true;button.textContent="Translate to English";return}
  if(panel.textContent){panel.hidden=false;button.textContent="Hide translation";return}
  const original=button.textContent;
  button.disabled=true;button.textContent="Translating…";
  try{
    const response=await fetch("/options/api/news/translate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title:card.dataset.newsTitle||"",snippet:card.dataset.newsSnippet||""})});
    const data=await response.json();if(!response.ok)throw Error(data.detail||"Translation failed.");
    panel.textContent=data.translation||"No translation was returned.";panel.hidden=false;button.textContent="Hide translation";
  }catch(error){toast(error.message);button.textContent=original}
  finally{button.disabled=false}
}
async function loadNews({quiet=false}={}){try{const params=new URLSearchParams({peak:$('#news-peak').value,publication:$('#news-publication').value,q:$('#news-search').value.trim()});const response=await fetch(`/options/api/news?${params}`);if(!response.ok)throw Error('News feed is unavailable.');const data=await response.json();renderNews(data.items||[]);const stamp=data.last_scan_at?new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'}).format(new Date(data.last_scan_at))+' PT':'Not scanned yet';$('#news-last-scanned').textContent=data.configured?`LAST SCAN · ${stamp}`:'PERPLEXITY KEY NOT CONFIGURED';if(!data.configured)$('#news-count').textContent='Add PERPLEXITY_API_KEY in Railway Variables to enable scanning.'}catch(error){if(!quiet){$('#news-items').innerHTML=`<p class="news-empty">${safe(error.message)}</p>`;toast('Could not load the RHTC news feed.')}}}
async function scanNews(query=''){const button=$('#scan-news'),submit=$('#news-search-submit');button.disabled=true;if(submit)submit.disabled=true;button.querySelector('.refresh-icon').classList.add('spin');try{const params=new URLSearchParams();if(query)params.set('q',query);const response=await fetch(`/options/api/news/scan${params.size?'?'+params.toString():''}`,{method:'POST'});const data=await response.json();if(!response.ok)throw Error(data.detail||'News scan failed.');await loadNews({quiet:true});toast(`${data.added||0} new · ${data.retrieved||0} retrieved · ${data.total||0} stories stored.`)}catch(error){toast(error.message)}finally{button.disabled=false;if(submit)submit.disabled=false;button.querySelector('.refresh-icon').classList.remove('spin')}}
function openPasteNewsModal(){
  const form=$('#paste-news-form');
  form.reset();
  $('#paste-news-status').textContent='';
  const backdrop=$('#paste-news-modal');
  openFullscreenModal(backdrop,backdrop.querySelector('.paste-news-modal'));
  setTimeout(()=>$('#pasted-news-content').focus(),0);
}
function closePasteNewsModal(){
  const backdrop=$('#paste-news-modal');
  resetFullscreenModal(backdrop,backdrop.querySelector('.paste-news-modal'));
}
window.closePasteNewsModal=closePasteNewsModal;
async function submitPastedNews(event){
  event.preventDefault();
  const content=$('#pasted-news-content').value.trim();
  if(content.length<20){$('#paste-news-status').textContent='Paste at least 20 characters of story content.';return}
  const button=$('#submit-pasted-news');
  const status=$('#paste-news-status');
  button.disabled=true;
  button.textContent='Adding…';
  status.textContent='Reading and categorizing the story…';
  try{
    const response=await fetch('/options/api/news/add-content',{
      method:'POST',
      credentials:'same-origin',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        content,
        title:$('#pasted-news-title').value.trim(),
        source:$('#pasted-news-source').value.trim(),
        published_at:$('#pasted-news-date').value,
        url:$('#pasted-news-url').value.trim()
      })
    });
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Could not add the pasted story.');
    $('#news-peak').value='All';
    $('#news-publication').value='All';
    $('#news-search').value='';
    closePasteNewsModal();
    await loadNews({quiet:true});
    toast(data.added?'Pasted story added to the feed.':'This pasted story already existed and was refreshed.');
  }catch(error){status.textContent=error.message||'Could not add the pasted story.'}
  finally{button.disabled=false;button.textContent='Add story to feed'}
}
async function addNewsUrl(){
  const value=window.prompt('Paste the full news story URL:','');
  if(value===null)return;
  const url=value.trim();
  if(!/^https?:\/\//i.test(url)){toast('Paste a complete http:// or https:// news URL.');return}
  const button=$('#add-news-url');
  const label=button.textContent;
  button.disabled=true;
  button.textContent='Adding…';
  try{
    const response=await fetch('/options/api/news/add-url',{
      method:'POST',
      credentials:'same-origin',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({url})
    });
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Could not add the news story.');
    $('#news-peak').value='All';
    $('#news-publication').value='All';
    $('#news-search').value='';
    await loadNews({quiet:true});
    toast(data.added?'News story added to the feed.':'Story already existed and was refreshed.');
  }catch(error){toast(error.message||'Could not add the news story.')}
  finally{button.disabled=false;button.textContent=label}
}
async function deduplicateNews(){
  const button=$('#dedupe-news');
  if(!window.confirm('Remove duplicate stories from all saved news? Stories are duplicates only when their normalized headlines and publication dates match. The copy with the most complete excerpt will be kept.'))return;
  button.disabled=true;
  const label=button.textContent;
  button.textContent='Removing…';
  try{
    const response=await fetch('/options/api/news/deduplicate',{method:'POST',credentials:'same-origin'});
    const data=await response.json();
    if(!response.ok)throw Error(data.detail||'Could not remove duplicate stories.');
    await loadNews({quiet:true});
    toast(data.removed?'Removed '+data.removed+' duplicate '+(data.removed===1?'story':'stories')+'; '+data.remaining+' stories remain.':'No duplicate stories found.');
  }catch(error){toast(error.message||'Could not remove duplicate stories.')}
  finally{button.disabled=false;button.textContent=label}
}
function setMode(mode){state.mode=mode;const isNews=mode==='news';document.body.classList.toggle('news-mode',isNews);if(!isNews)stopNewsSpeech();$('#options-view').hidden=isNews;$('#news-view').hidden=!isNews;$('#options-toolbar-filters').hidden=isNews;$('#main-pager').hidden=mode==='history';document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.filter===mode||(!n.dataset.filter&&mode==='overview')));if(isNews){loadNews()}else if(mode==='history'){renderRows();toast('Snapshots are saved in this browser.')}else if(mode==='holdings'){state.selectedOnly=true;state.peak='All Peaks';document.querySelectorAll('.peak-item').forEach(n=>n.classList.toggle('selected',n.dataset.peak==='All Peaks'));loadRows({ai:false,snapshot:false})}else{state.selectedOnly=false;renderRows()}}
function pageMain(delta){const next=state.expirationSet+delta;if(next<1||next>11)return;state.expirationSet=next;$('#main-page').textContent=DTE_WINDOWS[next-1];$('#main-prev').disabled=next===1;$('#main-next').disabled=next===11;loadRows({ai:false,snapshot:false})}
async function saveServerWatchlist(rows){if(!state.editingEnabled)throw Error('Shared editing is not enabled yet. Configure the Railway Volume shown above.');const response=await fetch('/options/api/watchlist',{method:'PUT',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({rows})});if(!response.ok){let detail='Could not save the shared symbol list.';try{detail=(await response.json()).detail||detail}catch(e){}throw Error(detail)}return (await response.json()).rows}
async function saveSymbolList(rows){setSymbolError('Saving to the shared RHTC list…');try{state.watchlist=await saveServerWatchlist(rows);state.migrationOpen=false;state.legacyWatchlist=null;localStorage.removeItem(WATCHLIST_KEY);updateWatchlistCounts();updateStorageNote();renderSymbolList();renderRows();setSymbolError('Saved for every browser.');loadRows({ai:false,snapshot:false});return true}catch(e){setSymbolError(e.message);return false}}
function validTicker(symbol){return /^[A-Z][A-Z0-9.-]{0,9}$/.test(symbol)}
function clearNewSymbolForm(){['#new-symbol','#new-share-price','#new-quantity','#new-lt-call','#new-lt-expy','#new-lt-qty','#new-lt-premium','#new-pg'].forEach(selector=>$(selector).value='');$('#new-peak').value='';$('#new-account').value='';setSymbolError();$('#new-symbol').focus()}
async function addSymbol(){const symbol=$('#new-symbol').value.trim().toUpperCase();const peak=$('#new-peak').value;const account=$('#new-account').value||null;if(!validTicker(symbol)){setSymbolError('Enter a valid ticker (letters, numbers, dots, or dashes).');return}if(state.watchlist.some(r=>r.symbol===symbol&&(r.account||'')===(account||''))){setSymbolError(`${symbol} is already on the list for this account.`);return}const lt_qty=optionalInteger($('#new-lt-qty'));if(Number.isNaN(lt_qty)){setSymbolError('LT-Qty must be a non-negative whole number.');return}const added={symbol,peak,share_price:optionalNumber($('#new-share-price')),quantity:optionalNumber($('#new-quantity')),account,lt_call:$('#new-lt-call').value.trim(),lt_expy:$('#new-lt-expy').value.trim(),lt_qty,lt_premium:optionalNumber($('#new-lt-premium')),pg:$('#new-pg').value.trim()};if(await saveSymbolList([added,...state.watchlist])){$('#new-symbol').value='';$('#new-share-price').value='';$('#new-quantity').value='';$('#new-account').value='';$('#new-lt-call').value='';$('#new-lt-expy').value='';$('#new-lt-qty').value='';$('#new-lt-premium').value='';$('#new-pg').value='';$('#new-peak').value='';renderSymbolList()}}
async function saveEditedSymbol(row){const oldSymbol=row.dataset.symbol;const oldAccount=row.dataset.account||'';const symbol=row.querySelector('.symbol-edit-ticker').value.trim().toUpperCase();const peak=row.querySelector('.symbol-edit-peak').value;const account=row.querySelector('.symbol-edit-account').value||null;if(!validTicker(symbol)){setSymbolError('Enter a valid ticker (letters, numbers, dots, or dashes).');return}if(state.watchlist.some(r=>!(r.symbol===oldSymbol&&(r.account||'')===oldAccount)&&r.symbol===symbol&&(r.account||'')===(account||''))){setSymbolError(`${symbol} is already on the list for this account.`);return}const share_price=optionalNumber(row.querySelector('.symbol-edit-price'));const quantity=optionalNumber(row.querySelector('.symbol-edit-quantity'));const lt_call=row.querySelector('.symbol-edit-lt-call').value.trim();const lt_expy=row.querySelector('.symbol-edit-lt-expy').value.trim();const lt_qty=optionalInteger(row.querySelector('.symbol-edit-lt-qty'));if(Number.isNaN(lt_qty)){setSymbolError('LT-Qty must be a non-negative whole number.');return}const lt_premium=optionalNumber(row.querySelector('.symbol-edit-lt-premium'));const pg=row.querySelector('.symbol-edit-pg').value.trim();const updated=state.watchlist.map(r=>r.symbol===oldSymbol&&(r.account||'')===oldAccount?{symbol,peak,share_price,quantity,account,lt_call,lt_expy,lt_qty,lt_premium,pg}:r);if(await saveSymbolList(updated)){state.editingSymbol=null;renderSymbolList()}}
window.showSettings=()=>{const backdrop=$('#settings-modal');openFullscreenModal(backdrop,backdrop.querySelector('.modal'))};window.hideSettings=()=>{const backdrop=$('#settings-modal');resetFullscreenModal(backdrop,backdrop.querySelector('.modal'))};window.hideDetail=()=>{const backdrop=$('#detail-modal'),modal=backdrop.querySelector('.detail-modal'),button=$('#detail-fullscreen-toggle');resetFullscreenModal(backdrop,modal,button)};window.hideSymbols=()=>{const backdrop=$('#symbols-modal');resetFullscreenModal(backdrop,backdrop.querySelector('.modal'))};window.hideSymbolAnalysis=()=>{const backdrop=$('#symbol-analysis-modal'),modal=backdrop.querySelector('.analysis-modal'),button=$('#analysis-fullscreen-toggle');stopAnalysisSpeech();resetFullscreenModal(backdrop,modal,button)};window.viewChain=viewChain;window.analyzeSymbol=analyzeSymbol;
$('#analysis-fullscreen-toggle').addEventListener('click',()=>{const backdrop=$('#symbol-analysis-modal'),modal=backdrop.querySelector('.analysis-modal'),button=$('#analysis-fullscreen-toggle'),active=!modal.classList.contains('is-fullscreen');modal.classList.toggle('is-fullscreen',active);backdrop.classList.toggle('is-fullscreen',active);button.setAttribute('aria-label',active?'Exit full screen':'Enter full screen');button.title=active?'Exit full screen':'Enter full screen';button.setAttribute('aria-pressed',String(active))});$('#detail-fullscreen-toggle').addEventListener('click',()=>{const backdrop=$('#detail-modal'),modal=backdrop.querySelector('.detail-modal'),button=$('#detail-fullscreen-toggle'),active=!modal.classList.contains('is-fullscreen');modal.classList.toggle('is-fullscreen',active);backdrop.classList.toggle('is-fullscreen',active);button.setAttribute('aria-label',active?'Exit full screen':'Enter full screen');button.title=active?'Exit full screen':'Enter full screen';button.setAttribute('aria-pressed',String(active))});$('#manage-symbols').addEventListener('click',openSymbols);$('#buffett-screen-btn').addEventListener('click',runBuffettScreen);$('#buffett-purge-btn').addEventListener('click',purgeAllBuffettReports);$('#ceo-risk-screen-btn').addEventListener('click',runCeoRiskScreen);$('#ceo-risk-purge-btn').addEventListener('click',purgeAllCeoRiskReports);$('#clear-symbol-form').addEventListener('click',clearNewSymbolForm);$('#add-symbol').addEventListener('click',addSymbol);$('#new-symbol').addEventListener('keydown',e=>{if(e.key==='Enter')addSymbol()});$('#symbol-filter').addEventListener('input',renderSymbolList);$('#symbol-peak-filter').addEventListener('change',renderSymbolList);$('#symbol-order-by').addEventListener('change',renderSymbolList);$('#import-browser-list').addEventListener('click',()=>{if(state.legacyWatchlist)saveSymbolList(state.legacyWatchlist)});
$('#symbol-list').addEventListener('click',async e=>{const button=e.target.closest('button[data-action]');if(!button)return;const row=button.closest('.symbol-entry');if(!row)return;const action=button.dataset.action;setSymbolError();if(action==='stock-report'){viewStockReports(row.dataset.symbol);return}else if(action==='buffett-report'){viewBuffettReports(row.dataset.symbol);return}else if(action==='ceo-risk-report'){viewCeoRiskReports(row.dataset.symbol);return}else if(action==='edit'){state.editingSymbol=symbolAccountKey(row.dataset.symbol,row.dataset.account);renderSymbolList()}else if(action==='cancel'){state.editingSymbol=null;renderSymbolList()}else if(action==='save'){saveEditedSymbol(row)}else if(action==='delete'){const accountLabel=row.dataset.account?` (${row.dataset.account})`:'';if(!window.confirm(`Delete ${row.dataset.symbol}${accountLabel} from the watchlist?`))return;const updated=state.watchlist.filter(r=>!(r.symbol===row.dataset.symbol&&(r.account||'')===(row.dataset.account||'')));if(await saveSymbolList(updated)){state.editingSymbol=null;renderSymbolList()}}});

const infrastructureProducts=[
  {group:'Hosting & delivery',name:'Railway',sub:'Application hosting, deployment, variables, persistent volume',api:'Railway platform / GitHub-connected deploy',version:'Production service · app runtime checked live',credentials:[],optional:true,owner:'Railway operates the platform; the Railway project owner manages billing and service settings.',cost:'Free trial: $5 credit for 30 days; Free: $1/month credit; Hobby: $5 minimum with $5 usage included. Usage above included credits is billed.',risk:'Usage can exceed included credits. Verify volume backups and service plan in Railway billing.',links:[['Pricing & trial','https://railway.com/pricing'],['Trial details','https://docs.railway.com/pricing/free-trial']]},
  {group:'Hosting & delivery',name:'GitHub',sub:'Source repository and deployment trigger',api:'GitHub repository + Railway integration',version:'henremurr/rhtc-research · main branch',credentials:[],owner:'GitHub repository owner controls source access; Railway deploys connected commits.',cost:'No separate app charge identified. Repository and account plan are not visible to the app.',risk:'Deployment depends on the GitHub connection and main-branch build. No GitHub Actions workflow was found in the reviewed app.',links:[['Repository','https://github.com/henremurr/rhtc-research'],['Plans','https://github.com/pricing']]},
  {group:'Hosting & delivery',name:'Python application stack',sub:'Web framework and runtime dependencies',api:'FastAPI · Uvicorn · HTTPX · Pydantic · ReportLab · OpenAI SDK · langdetect · imageio-ffmpeg · python-multipart',version:'Python 3.11+ expected; exact production runtime and installed package versions are checked live above.',credentials:[],owner:'RHTC maintains application code and dependency pins; Railway supplies the production runtime.',cost:'Open-source packages; no package subscription identified.',risk:'Requirements pin several packages, but Python minor version is not pinned. Review dependency updates and test before upgrading.',links:[['Requirements file','https://github.com/henremurr/rhtc-research/blob/main/requirements.txt']]},
  {group:'Hosting & delivery',name:'SQLite',sub:'Watchlist and application data storage',api:'Python standard-library sqlite3',version:'Database file under configured RHTC data directory / Railway volume',credentials:[],owner:'RHTC app writes the database; Railway hosts the persistent volume.',cost:'No separate database subscription. Storage and backup are part of hosting operations.',risk:'Recovery depends on the Railway volume and backups. This is a single-file database, not a managed database cluster.',links:[]},
  {group:'Market data',name:'Tradier',sub:'Quotes, option expirations, option chains',api:'Brokerage API v1',version:'Sandbox default; current base URL is checked live above',credentials:['TRADIER_API_TOKEN'],owner:'Tradier issues production and sandbox tokens; the brokerage account owner manages them.',cost:'Sandbox is for development/paper trading and delayed quotes. Account-linked data access; check Tradier account terms for exact costs.',risk:'Current default points to sandbox, with delayed data and lower request limits. Production requires the live token and production base URL; this dashboard does not place orders.',links:[['API guide','https://docs.tradier.com/docs/getting-started'],['Environments','https://docs.tradier.com/docs/endpoints'],['Rate limits','https://docs.tradier.com/docs/rate-limiting']]},
  {group:'Market data',name:'Finnhub',sub:'Optional company profile and fundamentals',api:'REST endpoints: profile2, metric, profile, insider-sentiment',version:'REST API; optional integration',credentials:['FINNHUB_API_KEY'],owner:'Finnhub account owner manages API key and plan.',cost:'Free and paid plans are offered; exact plan, quota, and billing are account-specific and not visible to the app.',risk:'Optional fields are unavailable when the key is absent or a plan/rate limit blocks the endpoint.',links:[['Plans','https://finnhub.io/pricing'],['API docs','https://finnhub.io/docs/api']]},
  {group:'AI & research',name:'OpenAI API',sub:'Research notes, ticker analysis, podcast scripts, speech',api:'OpenAI API · Python SDK',version:'SDK version checked live; defaults: gpt-5-mini and gpt-4o-mini-tts',credentials:['OPENAI_API_KEY'],owner:'OpenAI Platform project owner manages API key, limits, and billing.',cost:'Usage-based API billing, separate from ChatGPT. At the Oct. 4, 2026 check: GPT-5 Mini $0.25/M input and $2/M output tokens; GPT-4o Mini TTS $0.60/M text input and $12/M audio output tokens.',risk:'High: OpenAI currently marks GPT-5 Mini and GPT-4o Mini TTS deprecated. The dated GPT-5 Mini snapshot is scheduled for removal Dec. 11, 2026, and dated GPT-4o Mini TTS snapshots Jan. 6, 2027. Confirm active aliases and migrate/test before removal.',links:[['API pricing','https://developers.openai.com/api/docs/pricing'],['Model deprecations','https://developers.openai.com/api/docs/deprecations']]},
  {group:'AI & research',name:'Perplexity API',sub:'Current-news search and cited analysis',api:'Search API POST /search · Sonar POST /v1/sonar',version:'Fast Search · sonar / sonar-pro model names',credentials:['PERPLEXITY_API_KEY'],owner:'Perplexity API project owner manages API credits, key, and usage tier.',cost:'API billed separately from consumer plans. Fast Search: $1 per 1,000 successful requests; regular Search: $5 per 1,000. Sonar analysis is usage/model-priced.',risk:'Search request billing is per request (up to five queries per request); model and endpoint lifecycle can change. No official retirement notice for /v1/sonar was found in the current changelog check.',links:[['API pricing','https://docs.perplexity.ai/docs/getting-started/pricing'],['API changelog','https://docs.perplexity.ai/docs/resources/changelog']]},
  {group:'Publishing',name:'Google Cloud OAuth + YouTube',sub:'Uploads generated episodes to the RHTC YouTube channel',api:'YouTube Data API v3 · OAuth 2.0 web application · resumable video upload',version:'YouTube quota and upload API; Google OAuth refresh flow',credentials:['YOUTUBE_CLIENT_ID','YOUTUBE_CLIENT_SECRET','YOUTUBE_REFRESH_TOKEN'],owner:'Google Cloud project owner controls OAuth consent/API quota; channel owner controls publishing.',cost:'Default quota includes 100 video uploads/day and 10,000 units/day for other API calls. No separate app fee identified; quota may be extended after review.',risk:'High: OAuth external app left in Testing can issue refresh tokens that expire after 7 days. Tokens can also be revoked or invalidated. Unverified projects may be restricted to private uploads.',links:[['YouTube API quota','https://developers.google.com/youtube/v3/getting-started'],['OAuth token expiration','https://developers.google.com/identity/protocols/oauth2']]},
  {group:'Publishing',name:'X Developer Platform',sub:'Publishes selected RHTC news articles as Posts on X',api:'X API v2 · POST /2/tweets · OAuth 1.0a user context',version:'Pay-per-use X Developer Platform',credentials:['X_API_KEY','X_API_SECRET','X_ACCESS_TOKEN','X_ACCESS_TOKEN_SECRET'],owner:'The RHTC X account owner controls the X Developer app, API credits, and write authorization.',cost:'Pay per use. Charges draw from credits funded in the X Developer Console.',risk:'Medium: write access or funded credits can be removed; changing app permissions requires regenerating the access token and secret.',links:[['X Developer Console','https://developer.x.com/'],['Create a Post','https://docs.x.com/x-api/posts/manage-tweets/quickstart']]},
  {group:'Browser assets',name:'Google Fonts',sub:'DM Mono, DM Sans, and Manrope typography',api:'Google Fonts CSS and font delivery',version:'Browser-loaded web fonts',credentials:[],owner:'Google serves fonts; RHTC controls the font references in the page.',cost:'No separate app subscription identified.',risk:'If the external font service is unavailable, the browser falls back to local font families.',links:[['Google Fonts','https://fonts.google.com/']]}
];
function infraCredentialLabel(names,data){
  if(!names.length)return 'No secret required';
  if(!data)return 'Not checked · '+names.join(', ');
  const status=data?.credential_status||{};
  const present=names.filter(name=>status[name]).length;
  const missing=names.filter(name=>!status[name]);
  if(present===names.length)return 'Configured · '+names.join(', ');
  if(present===0)return 'Not detected · '+names.join(', ');
  return 'Partially configured · present: '+names.filter(name=>status[name]).join(', ')+' · missing: '+missing.join(', ');
}
function infraPackageVersion(data,name){
  return data?.packages?.[name]||'not reported';
}
function infraProductState(item,data){
  if(item.optional&&!item.credentials.length)return {label:'Available',cls:''};
  if(!item.credentials.length)return {label:'Inventory',cls:''};
  if(!data)return {label:'Unverified',cls:'partial'};
  const status=data?.credential_status||{};
  const configured=item.credentials.filter(name=>status[name]).length;
  if(configured===item.credentials.length)return {label:'Configured',cls:'ready'};
  if(configured>0)return {label:'Partial',cls:'partial'};
  return {label:'Not detected',cls:''};
}
function renderInfraSnippet(source){
  const clean=String(source||'')
    .replace(/\r/g,'')
    .replace(/\\n/g,'\n')
    .replace(/<\/?[a-z][^>]*>/gi,' ')
    .replace(/[ \t]+/g,' ')
    .trim();
  if(!clean)return '';
  const lines=clean.split('\n').map(line=>line.trim()).filter(Boolean);
  const inline=value=>analysisInline(value)
    .replace(/(^|\s)_([^_]+)_(?=$|\s)/g,'$1<em>$2</em>');
  const out=[];
  for(let i=0;i<lines.length;){
    const line=lines[i];
    if(line.includes('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1])){
      const cells=value=>value.replace(/^\s*\|/,'').replace(/\|\s*$/,'').split('|').map(cell=>cell.trim());
      const headers=cells(line);
      i+=2;
      const rows=[];
      while(i<lines.length&&lines[i].includes('|')){rows.push(cells(lines[i]));i++}
      out.push('<div class="infra-table-wrap"><table class="infra-source-table"><thead><tr>'+headers.map(cell=>'<th>'+inline(cell)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+headers.map((_,index)=>'<td>'+inline(row[index]||'')+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>');
      continue;
    }
    const heading=line.match(/^#{1,4}\s+(.+)$/);
    if(heading){out.push('<h4>'+inline(heading[1].replace(/#+$/,'').trim())+'</h4>');i++;continue}
    if(/^[-*]\s+/.test(line)){
      const items=[];
      while(i<lines.length&&/^[-*]\s+/.test(lines[i]))items.push('<li>'+inline(lines[i++].replace(/^[-*]\s+/,''))+'</li>');
      out.push('<ul>'+items.join('')+'</ul>');continue;
    }
    const paragraph=[line];i++;
    while(i<lines.length&&!/^#{1,4}\s+/.test(lines[i])&&!/^[-*]\s+/.test(lines[i])&&!(lines[i].includes('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1])))paragraph.push(lines[i++]);
    out.push('<p>'+paragraph.map(inline).join(' ')+'</p>');
  }
  return out.join('');
}
function infrastructureInventoryMarkup(data){
  const credentials=data?.credential_status||{};
  const credentialNames=Object.keys(credentials);
  const present=credentialNames.filter(name=>credentials[name]).length;
  const runtime=data?.python_version||'Not reported';
  const generated=data?.generated_at?new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',dateStyle:'medium',timeStyle:'short'}).format(new Date(data.generated_at))+' PT':'Not checked';
  const source=data?.data_source==='tradier_sandbox'?'Tradier sandbox':data?.data_source==='tradier'?'Tradier production':'Demo / no Tradier token';
  const packageRows=[
    ['FastAPI','FastAPI'],['Uvicorn','Uvicorn'],['HTTPX','HTTPX'],['Pydantic','Pydantic'],['ReportLab','ReportLab'],['OpenAI SDK','OpenAI Python SDK'],['langdetect','langdetect'],['imageio-ffmpeg','imageio-ffmpeg'],['python-multipart','python-multipart']
  ].map(([label,key])=>'<span>'+safe(label)+' <b>'+safe(infraPackageVersion(data,key))+'</b></span>').join('');
  const groups=[...new Set(infrastructureProducts.map(item=>item.group))];
  const products=groups.map(group=>{
    const cards=infrastructureProducts.filter(item=>item.group===group).map(item=>{
      const status=infraProductState(item,data);
      let version=item.version;
      if(item.name==='Python application stack')version='Python '+runtime+' · installed packages below';
      if(item.name==='Tradier')version='Base URL: '+(data?.tradier_base_url||'https://sandbox.tradier.com/v1');
      if(item.name==='OpenAI API'){
        const models=data?.models||{};
        version='SDK '+infraPackageVersion(data,'OpenAI Python SDK')+' · '+(models.OPENAI_MODEL||'gpt-5-mini')+' · '+(models.OPENAI_TTS_MODEL||'gpt-4o-mini-tts');
      }
      const links=item.links.map(([label,url])=>'<a href="'+safe(url)+'" target="_blank" rel="noopener noreferrer">'+safe(label)+' ↗</a>').join('');
      const extras=item.name==='Python application stack'?'<div class="infra-package-list">'+packageRows+'</div>':'';
      return '<article class="infra-product"><div class="infra-product-head"><div><div class="infra-product-name">'+safe(item.name)+'</div><div class="infra-product-sub">'+safe(item.sub)+'</div></div><span class="infra-state '+status.cls+'">'+safe(status.label)+'</span></div><div class="infra-details"><div class="infra-detail"><b>API / version</b> · '+safe(item.api)+'<br><code>'+safe(version)+'</code></div><div class="infra-detail"><b>Credentials</b> · '+safe(infraCredentialLabel(item.credentials,data))+'</div><div class="infra-detail"><b>Managed by</b> · '+safe(item.owner)+'</div><div class="infra-detail"><b>Plan / cost</b> · '+safe(item.cost)+'</div><div class="infra-detail"><b>Lifecycle risk</b> · '+safe(item.risk)+'</div></div>'+extras+(links?'<div class="infra-links">'+links+'</div>':'')+'</article>';
    }).join('');
    return '<section class="infra-group"><h3 class="infra-group-title">'+safe(group)+'</h3><div class="infra-product-grid">'+cards+'</div></section>';
  }).join('');
  const location=data?.data_dir||data?.railway_volume_mount_path||'Not reported';
  const checks=data?.source_checks||{status:'not_requested',results:[]};
  const freshSources=(checks.results||[]).map(item=>'<article class="infra-source"><a href="'+safe(item.url)+'" target="_blank" rel="noopener noreferrer">'+safe(item.title)+' ↗</a>'+(item.date?'<time>'+safe(item.date)+'</time>':'')+(item.snippet?'<div class="infra-source-snippet">'+renderInfraSnippet(item.snippet)+'</div>':'')+'</article>').join('');
  const sourceSection='<section class="infra-fresh-checks"><div class="infra-results-head"><h3>Fresh provider documentation check</h3><span>'+(checks.status==='complete'?(checks.results||[]).length+' sources returned':checks.status==='not_configured'?'Perplexity key not detected':checks.status==='unavailable'?'Search temporarily unavailable':'Not run')+'</span></div><p>Each audit sends five current pricing, API, quota, and deprecation queries in one Perplexity Fast Search request. Current listed rate: about $0.001 per successful audit request; no token fee.</p>'+(freshSources||'<div class="infra-source-empty">No current source results are available. Use the official documentation links in each product card.</div>')+'</section>';
  return '<div class="infra-stats"><article class="infra-stat"><div class="infra-stat-label">Products inventoried</div><div class="infra-stat-value">'+infrastructureProducts.length+'</div><div class="infra-stat-note">Application and external services</div></article><article class="infra-stat"><div class="infra-stat-label">Core credentials</div><div class="infra-stat-value">'+present+' / '+credentialNames.length+'</div><div class="infra-stat-note">Presence only · secret values never returned</div></article><article class="infra-stat"><div class="infra-stat-label">Production runtime</div><div class="infra-stat-value">Python '+safe(runtime)+'</div><div class="infra-stat-note">'+safe(source)+'</div></article><article class="infra-stat"><div class="infra-stat-label">Last inventory check</div><div class="infra-stat-value">'+safe(generated)+'</div><div class="infra-stat-note">Storage: '+safe(location)+'</div></article></div>'+products+sourceSection+'<div class="infra-note"><b>Account and billing visibility:</b> the app can confirm runtime versions and whether named secrets exist, but it cannot read provider account owners, billing plans, trial status, balances, or invoices. Pricing and lifecycle notes above were reviewed October 4, 2026; use the linked official product pages to confirm later changes. <b>API tokens are never displayed.</b></div>';
}
async function runInfrastructureInventory(){
  const button=$('#infra-refresh');
  const status=$('#infra-status');
  const results=$('#infra-inventory-results');
  button.disabled=true;button.textContent='↻ Checking…';
  status.dataset.kind='';status.textContent='Inspecting the deployed runtime and configured variable names. Secret values are not read or returned.';
  try{
    const response=await fetch('/options/api/infrastructure-inventory?include_sources=true',{credentials:'same-origin',cache:'no-store'});
    const payload=await response.json();
    if(!response.ok)throw new Error(payload.detail||'Inventory check failed ('+response.status+').');
    results.innerHTML=infrastructureInventoryMarkup(payload);
    status.dataset.kind='ok';
    status.textContent='Deployment and documentation check completed '+new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',dateStyle:'medium',timeStyle:'short'}).format(new Date(payload.generated_at))+' PT. '+(payload.source_checks?.status==='complete'?'Fresh official-source search completed; estimated search charge ≈ $0.001.':'Live source search was not completed; see report status.');
  }catch(error){
    results.innerHTML=infrastructureInventoryMarkup(null);
    status.dataset.kind='warn';
    status.textContent='Live deployment check unavailable: '+(error?.message||'request failed')+' The product reference inventory is still shown below.';
  }finally{
    button.disabled=false;button.textContent='↻ Recheck deployment';
  }
}
function showInfrastructureInventory(){
  $('#infra-modal').classList.add('open');
  runInfrastructureInventory();
}
function hideInfrastructureInventory(){
  $('#infra-modal').classList.remove('open');
}

$('#infra-audit-btn').addEventListener('click',showInfrastructureInventory);$('#infra-refresh').addEventListener('click',runInfrastructureInventory);
$('#theme-toggle').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'));
$('#chain-prev').addEventListener('click',()=>pageChain(-1));$('#chain-next').addEventListener('click',()=>pageChain(1));$('#analyze-displayed-btn').addEventListener('click',analyzeDisplayedSymbols);$('#analyze-displayed-stocks-btn').addEventListener('click',analyzeDisplayedStocks);
$('#main-prev').addEventListener('click',()=>pageMain(-1));$('#main-next').addEventListener('click',()=>pageMain(1));$('#main-prev').disabled=true;
document.querySelectorAll('.peak-item').forEach(el=>el.addEventListener('click',()=>{const holdings=el.dataset.peak==='Holdings';state.costOnly=holdings;state.accountFilter='all';state.peak=holdings?'All Peaks':el.dataset.peak;$('#peak-filter').value=holdings?'Holdings':state.peak;state.mode='overview';state.selectedOnly=false;document.querySelectorAll('.peak-item').forEach(n=>n.classList.toggle('selected',n===el));setMode('overview');loadRows({ai:false,snapshot:false})}));
$('#peak-filter').addEventListener('change',e=>{const selection=e.target.value,accountSelection=selection.startsWith('account:'),holdings=selection==='Holdings';state.accountFilter=accountSelection?selection.slice(8):'all';state.costOnly=holdings;state.peak=holdings||accountSelection?'All Peaks':selection;state.mode='overview';state.selectedOnly=false;setMode('overview');loadRows({ai:false,snapshot:false})});
function updateScoreMissingFilters(){state.stockScoreFilter=$('#stock-score-filter').value;state.callScoreFilter=$('#call-score-filter').value;state.mode='overview';state.selectedOnly=false;setMode('overview');loadRows({ai:false,snapshot:false})}
$('#stock-score-filter').addEventListener('change',updateScoreMissingFilters);$('#call-score-filter').addEventListener('change',updateScoreMissingFilters);
document.querySelectorAll('.nav-item').forEach(el=>el.addEventListener('click',()=>{const wasCostOnly=state.costOnly;state.costOnly=false;setMode(el.dataset.filter||'overview');if(wasCostOnly)loadRows({ai:false,snapshot:false})}));
$('#scan-news').addEventListener('click',()=>scanNews());$('#add-news-url').addEventListener('click',addNewsUrl);$('#paste-news-content').addEventListener('click',openPasteNewsModal);$('#paste-news-form').addEventListener('submit',submitPastedNews);$('#dedupe-news').addEventListener('click',deduplicateNews);$('#news-search-form').addEventListener('submit',event=>{event.preventDefault();scanNews($('#news-search').value.trim())});$('#news-peak').addEventListener('change',()=>loadNews());$('#news-publication').addEventListener('change',()=>loadNews());let newsSearchTimer;$('#news-search').addEventListener('input',()=>{clearTimeout(newsSearchTimer);newsSearchTimer=setTimeout(()=>loadNews({quiet:true}),220)});
$('#analysis-read-btn').addEventListener('click',toggleAnalysisSpeech);$('#analysis-stop-btn').addEventListener('click',()=>stopAnalysisSpeech());
$('#analysis-mp3-btn').addEventListener('click',createAnalysisPodcast);$('#analysis-copy-transcript').addEventListener('click',copyAnalysisPodcastTranscript);$('#youtube-publish-btn').addEventListener('click',publishAnalysisToYouTube);$('#youtube-series').addEventListener('change',()=>{if(!activeNewsStory)return;const field=$('#youtube-video-title'),current=field.value,separator=current.indexOf(' | '),headline=separator>=0?current.slice(separator+3).trim():activeNewsStory.title;field.value=youtubeTitleForTheme(headline,$('#youtube-series').value)});$('#youtube-review-confirm').addEventListener('change',updateYouTubePublishButton);
$('#news-items').addEventListener('click',event=>{const button=event.target.closest('[data-news-action]');if(!button)return;const card=button.closest('.news-item');if(!card)return;if(button.dataset.newsAction==='read')toggleNewsSpeech(card);else if(button.dataset.newsAction==='stop')stopNewsSpeech();else if(button.dataset.newsAction==='analyze')analyzeNewsStory(card,button);else if(button.dataset.newsAction==='publish')publishNewsStory(card,button);else if(button.dataset.newsAction==='republish')republishNewsStory(card,button);else if(button.dataset.newsAction==='retry-x')unlockXRetry(card);else if(button.dataset.newsAction==='translate')translateNewsStory(card,button);else if(button.dataset.newsAction==='change-peak'){const select=card.querySelector('.news-peak-select');select.hidden=!select.hidden;if(!select.hidden)select.focus()}else if(button.dataset.newsAction==='delete-story')deleteNewsStory(card,button)});
$('#news-items').addEventListener('change',event=>{const artwork=event.target.closest('.news-artwork-select');if(artwork){changeNewsArtworkTheme(artwork.closest('.news-item'),artwork);return}const select=event.target.closest('.news-peak-select');if(select)changeNewsPeak(select.closest('.news-item'),select)});$('#auto-reload').addEventListener('change',e=>setAutoReload(e.target.value));try{setAutoReload(localStorage.getItem('rhtc-options-auto-reload')||'0',false)}catch(e){setAutoReload('0',false)};$('#refresh').addEventListener('click',()=>loadRows({ai:true,snapshot:true}));$('#review-limit').addEventListener('change',e=>{state.displayLimit=Number(e.target.value)||300;renderRows()});$('#max-spend').addEventListener('change',e=>{const spend=parseMaxSpend(e.target.value);if(Number.isFinite(spend))e.target.value=formatMaxSpend(spend);loadRows({ai:false,snapshot:false})});$('#sort').addEventListener('change',e=>{state.sort=e.target.value;loadRows({ai:false,snapshot:false})});let searchTimer;$('#search').addEventListener('input',e=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.query=e.target.value.trim();loadRows({ai:false,snapshot:false})},220)});
$('#market-clock').textContent=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date())+' ET';
initializeWatchlist();
loadNews({quiet:true});
$('#dashboard-logout').addEventListener('click',async()=>{try{await fetch('/options/auth/logout',{method:'POST',credentials:'same-origin'})}finally{location.replace('/options/login')}});


// Keep the guide menu fully inside the current viewport, including on narrow phones.
(()=>{const toggle=document.getElementById('guide-menu-toggle'),menu=document.getElementById('guide-menu'),guideToggle=document.getElementById('guide-submenu-toggle'),submenu=document.getElementById('guide-submenu');if(!toggle||!menu||!guideToggle||!submenu)return;const place=()=>{const rect=toggle.getBoundingClientRect(),width=menu.getBoundingClientRect().width,gap=12;const left=Math.max(gap,Math.min(rect.right-width,window.innerWidth-width-gap));const top=Math.max(gap,Math.min(rect.bottom+8,window.innerHeight-menu.offsetHeight-gap));menu.style.left=left+'px';menu.style.top=top+'px';menu.style.right='auto'};const collapseGuide=()=>{submenu.hidden=true;guideToggle.setAttribute('aria-expanded','false')};const close=()=>{menu.hidden=true;toggle.setAttribute('aria-expanded','false');collapseGuide()};toggle.addEventListener('click',event=>{event.stopPropagation();const opening=menu.hidden;menu.hidden=!opening;toggle.setAttribute('aria-expanded',String(opening));if(opening){collapseGuide();requestAnimationFrame(place)}});guideToggle.addEventListener('click',event=>{event.stopPropagation();submenu.hidden=!submenu.hidden;guideToggle.setAttribute('aria-expanded',String(!submenu.hidden));requestAnimationFrame(place)});menu.addEventListener('click',event=>{if(event.target.closest('a')||event.target.closest('#infra-audit-btn'))close()});document.addEventListener('click',event=>{if(!event.target.closest('.guide-menu-wrap'))close()});document.addEventListener('keydown',event=>{if(event.key==='Escape'){close();toggle.focus()}});window.addEventListener('resize',()=>{if(!menu.hidden)place()})})();

if(new URLSearchParams(location.search).get("youtube")==="connected"){const notice=document.createElement("div");notice.setAttribute("role","status");notice.style.cssText="padding:16px;background:#174b35;color:white;text-align:center";notice.textContent="YouTube connected. You can now publish a reviewed video from the dashboard.";document.body.prepend(notice);const u=new URL(location.href);u.searchParams.delete("youtube");history.replaceState(null,"",u.pathname+u.search+u.hash);}
